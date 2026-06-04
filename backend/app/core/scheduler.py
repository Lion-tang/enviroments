"""Background scheduler for periodic server status and detail checks."""

import json
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm.exc import StaleDataError

from app.core.database import SessionLocal
from app.core.audit_log import write_server_log
from app.models.server import Server
from app.models.switch import Switch
from app.models.network_link import NetworkLink
from infrastructure.ssh_client import (
    check_online,
    get_server_info_via_ssh,
    fetch_up_server_interfaces_via_ssh,
    fetch_all_macs_from_switch_via_ssh,
    stimulate_mac_learning_via_ssh,
)

logger = logging.getLogger("scheduler")


def _update_server_by_id(db, server_id: int, values: dict) -> bool:
    """Update by primary key without relying on a potentially stale ORM instance."""
    try:
        updated = db.query(Server).filter(Server.id == server_id).update(
            values,
            synchronize_session=False,
        )
        db.commit()
        return updated == 1
    except StaleDataError:
        db.rollback()
        logger.warning("[Scheduler] Server %s changed before update; skipped", server_id)
        return False
    except Exception:
        db.rollback()
        raise


def status_check_task(app):
    """Ping all servers, update online status, write JSON log lines."""
    db = SessionLocal()
    try:
        servers = db.query(
            Server.id,
            Server.ip,
            Server.port,
            Server.is_online,
            Server.online_checked_at,
            Server.status_check_interval,
        ).all()
        now = datetime.utcnow()
        checked = 0
        for server in servers:
            # Rate limit: skip if checked recently per interval
            if server.online_checked_at:
                elapsed = (now - server.online_checked_at).total_seconds() / 60
                if elapsed < (server.status_check_interval or 5):
                    continue

            online = check_online(server.ip, port=server.port)
            _update_server_by_id(db, server.id, {
                "is_online": online,
                "online_checked_at": now,
            })
            checked += 1

            write_server_log(server.ip, {
                "type": "status_check",
                "online": online,
                "changed": server.is_online != online,
            })

        logger.info("[Scheduler] Status check done for %s/%s servers", checked, len(servers))
    except Exception as e:
        logger.error(f"[Scheduler] Status check error: {e}")
        db.rollback()
    finally:
        db.close()


def detail_fetch_task(app):
    """SSH fetch full server info, cache and write JSON log lines."""
    db = SessionLocal()
    try:
        servers = db.query(
            Server.id,
            Server.ip,
            Server.port,
            Server.ssh_username,
            Server.ssh_password,
            Server.ssh_key_file,
            Server.is_online,
            Server.cached_at,
            Server.detail_fetch_interval,
        ).all()
        now = datetime.utcnow()
        fetched = 0
        for server in servers:
            # Rate limit: skip if fetched recently per interval
            if server.cached_at:
                elapsed = (now - server.cached_at).total_seconds() / 60
                if elapsed < (server.detail_fetch_interval or 30):
                    continue

            info = get_server_info_via_ssh(
                ip=server.ip,
                username=server.ssh_username,
                password=server.ssh_password,
                key_file=server.ssh_key_file,
                port=server.port,
            )

            if info.error:
                write_server_log(server.ip, {
                    "type": "detail_fetch",
                    "online": server.is_online,
                    "error": info.error,
                })
            else:
                snapshot = {
                    "type": "detail_fetch",
                    "online": server.is_online,
                    "os_type": info.os_type,
                    "os_version": info.os_version,
                    "cpu_model": info.cpu_model,
                    "cpu": info.cpu_count,
                    "mem": info.memory_total,
                    "interfaces": info.interfaces or [],
                    "hostname": info.hostname,
                }
                write_server_log(server.ip, snapshot)

                _update_server_by_id(db, server.id, {
                    "cached_info": json.dumps(snapshot, ensure_ascii=False),
                    "cached_at": now,
                    "is_online": True,
                })
                fetched += 1

        logger.info("[Scheduler] Detail fetch done for %s/%s servers", fetched, len(servers))
    except Exception as e:
        logger.error(f"[Scheduler] Detail fetch error: {e}")
        db.rollback()
    finally:
        db.close()


def _topo_upsert_link(
    db,
    server_id: int,
    switch_id: int,
    iface: dict,
    status: str,
    switch_interface=None,
    vlan=None,
    raw_output=None,
    error=None,
):
    link = db.query(NetworkLink).filter(
        NetworkLink.server_id == server_id,
        NetworkLink.switch_id == switch_id,
        NetworkLink.server_interface == iface["name"],
        NetworkLink.server_mac == iface["mac"],
    ).first()
    if not link:
        link = NetworkLink(
            server_id=server_id,
            switch_id=switch_id,
            server_interface=iface["name"],
            server_mac=iface["mac"],
        )
        db.add(link)
    link.server_ip = iface.get("ip")
    link.switch_interface = switch_interface
    link.vlan = vlan
    link.status = status
    link.raw_output = raw_output
    link.error = error
    link.discovered_at = datetime.utcnow()
    db.commit()
    db.refresh(link)
    return link


def topology_discovery_task(app):
    """SSH discover network topology: match server interfaces to switch MAC tables."""
    db = SessionLocal()
    try:
        logger.info("[Scheduler] Topology discovery started")

        # Only servers that have associated switches
        servers = db.query(Server).filter(Server.switches.any()).all()
        if not servers:
            logger.info("[Scheduler] No servers with switches, skipping topology")
            return

        # ── Step 1: collect server interfaces ──
        server_ifaces = []
        for server in servers:
            interfaces, error = fetch_up_server_interfaces_via_ssh(
                ip=server.ip,
                username=server.ssh_username,
                password=server.ssh_password,
                key_file=server.ssh_key_file,
                port=server.port,
            )
            server_ifaces.append({
                "server": server,
                "interfaces": interfaces if not error else [],
                "error": error,
            })

        # ── Step 2: ping broadcasts on each interface to trigger switch MAC learning ──
        all_macs = {}
        for entry in server_ifaces:
            server = entry["server"]
            for iface in entry["interfaces"]:
                try:
                    stimulate_mac_learning_via_ssh(
                        ip=server.ip,
                        username=server.ssh_username,
                        password=server.ssh_password,
                        key_file=server.ssh_key_file,
                        port=server.port,
                        iface=iface["name"],
                    )
                except Exception:
                    pass
                mac = iface["mac"]
                if mac not in all_macs:
                    all_macs[mac] = {"server": server, "iface": iface}

        # ── Step 3: fetch MAC tables from all involved switches ──
        switch_ids = set()
        for entry in server_ifaces:
            for sw in entry["server"].switches:
                switch_ids.add(sw.id)
        involved_switches = db.query(Switch).filter(Switch.id.in_(switch_ids)).all()

        switch_mac_maps = {}
        for switch in involved_switches:
            try:
                result = fetch_all_macs_from_switch_via_ssh(
                    ip=switch.ip,
                    username=switch.username,
                    password=switch.password,
                    port=switch.port,
                )
                switch_mac_maps[switch.id] = result
            except Exception as e:
                switch_mac_maps[switch.id] = {
                    "error": str(e),
                    "mac_map": {},
                    "raw_output": None,
                }

        # ── Step 4: match and upsert ──
        stats = {"total_servers": 0, "total_interfaces": 0, "found": 0, "not_found": 0, "errors": 0}
        for entry in server_ifaces:
            server = entry["server"]
            if entry.get("error"):
                stats["errors"] += 1
                continue
            stats["total_servers"] += 1

            for iface in entry["interfaces"]:
                stats["total_interfaces"] += 1
                for switch in server.switches:
                    sw_result = switch_mac_maps.get(switch.id, {})
                    sw_error = sw_result.get("error")
                    mac_map = sw_result.get("mac_map", {})

                    found_entry = mac_map.get(iface["mac"])
                    if found_entry:
                        _topo_upsert_link(
                            db, server.id, switch.id, iface,
                            status="found",
                            switch_interface=found_entry["interface"],
                            vlan=found_entry.get("vlan"),
                            raw_output=sw_result.get("raw_output"),
                        )
                        stats["found"] += 1
                    elif sw_error:
                        _topo_upsert_link(
                            db, server.id, switch.id, iface,
                            status="error", error=sw_error,
                        )
                        stats["errors"] += 1
                    else:
                        _topo_upsert_link(
                            db, server.id, switch.id, iface,
                            status="not_found",
                            raw_output=sw_result.get("raw_output"),
                        )
                        stats["not_found"] += 1

        logger.info(
            "[Scheduler] Topology discovery done: %d servers, %d interfaces, "
            "%d found, %d not_found, %d errors",
            stats["total_servers"], stats["total_interfaces"],
            stats["found"], stats["not_found"], stats["errors"],
        )
    except Exception as e:
        logger.error(f"[Scheduler] Topology discovery error: {e}")
        db.rollback()
    finally:
        db.close()


def create_scheduler(app) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        status_check_task,
        trigger=IntervalTrigger(minutes=5),
        args=[app],
        id="status_check",
        name="Server Status Check (every 5 min)",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        detail_fetch_task,
        trigger=IntervalTrigger(minutes=30),
        args=[app],
        id="detail_fetch",
        name="Server Detail Fetch (every 30 min)",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        topology_discovery_task,
        trigger=IntervalTrigger(minutes=30),
        args=[app],
        id="topology_discovery",
        name="Topology Discovery (every 30 min)",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    return scheduler
