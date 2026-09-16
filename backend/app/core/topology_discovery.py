"""Shared, bounded topology discovery service."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from threading import Lock
from typing import Optional

from sqlalchemy.orm import Session, load_only, noload, selectinload

from app.models.network_link import NetworkLink
from app.models.server import Server
from app.models.switch import Switch
from infrastructure.ssh_client import (
    fetch_all_macs_from_switch_via_ssh,
    fetch_and_stimulate_server_interfaces_via_ssh,
)


DISCOVERY_LOCK = Lock()
SERVER_WORKERS = 8
SWITCH_WORKERS = 4


class DiscoveryBusyError(RuntimeError):
    pass


def _run_parallel(items: list[dict], worker, max_workers: int) -> dict[int, object]:
    if not items:
        return {}
    results = {}
    with ThreadPoolExecutor(max_workers=min(max_workers, len(items))) as executor:
        future_map = {executor.submit(worker, item): item["id"] for item in items}
        for future in as_completed(future_map):
            item_id = future_map[future]
            try:
                results[item_id] = future.result()
            except Exception as exc:
                results[item_id] = {"error": str(exc)}
    return results


def _scan_server(config: dict) -> dict:
    interfaces, error = fetch_and_stimulate_server_interfaces_via_ssh(
        ip=config["ip"],
        username=config["username"],
        password=config["password"],
        key_file=config["key_file"],
        port=config["port"],
    )
    return {
        "interfaces": interfaces if not error else [],
        "error": error,
        "scan_complete": error is None,
    }


def _scan_switch(config: dict) -> dict:
    result = fetch_all_macs_from_switch_via_ssh(
        ip=config["ip"],
        username=config["username"],
        password=config["password"],
        port=config["port"],
    )
    return {
        "mac_map": result.get("mac_map", {}),
        "error": result.get("error"),
    }


def discover_topology_records(
    db: Session,
    server_ids: Optional[list[int]] = None,
) -> dict:
    """Discover topology with bounded SSH concurrency and one DB transaction."""
    if not DISCOVERY_LOCK.acquire(blocking=False):
        raise DiscoveryBusyError("拓扑发现任务正在运行，请稍后再试")

    try:
        query = (
            db.query(Server)
            .options(
                load_only(
                    Server.id,
                    Server.ip,
                    Server.port,
                    Server.ssh_username,
                    Server.ssh_password,
                    Server.ssh_key_file,
                ),
                selectinload(Server.switches).load_only(
                    Switch.id,
                    Switch.name,
                    Switch.ip,
                    Switch.port,
                    Switch.username,
                    Switch.password,
                ),
            )
            .order_by(Server.ip)
        )
        if server_ids is not None:
            query = query.filter(Server.id.in_(server_ids))
        selected_servers = query.all()

        active_servers = [server for server in selected_servers if server.switches]
        server_configs = [
            {
                "id": server.id,
                "ip": server.ip,
                "username": server.ssh_username,
                "password": server.ssh_password,
                "key_file": server.ssh_key_file,
                "port": server.port,
                "switch_ids": [switch.id for switch in server.switches],
            }
            for server in active_servers
        ]
        selected_server_ids = [server.id for server in selected_servers]
        servers_without_switch_ids = {
            server.id for server in selected_servers if not server.switches
        }
        switch_snapshots = {
            switch.id: {
                "id": switch.id,
                "name": switch.name,
                "ip": switch.ip,
                "port": switch.port,
                "username": switch.username,
                "password": switch.password,
            }
            for server in active_servers
            for switch in server.switches
        }
        switch_configs = [
            snapshot.copy() for snapshot in switch_snapshots.values()
        ]

        # Release the read transaction and pooled connection before slow SSH work.
        db.rollback()
        server_scans = _run_parallel(server_configs, _scan_server, SERVER_WORKERS)
        switch_scans = _run_parallel(switch_configs, _scan_switch, SWITCH_WORKERS)

        existing_rows = (
            db.query(NetworkLink)
            .options(
                load_only(
                    NetworkLink.id,
                    NetworkLink.server_id,
                    NetworkLink.switch_id,
                    NetworkLink.server_interface,
                    NetworkLink.server_ip,
                    NetworkLink.server_mac,
                    NetworkLink.switch_interface,
                    NetworkLink.vlan,
                    NetworkLink.status,
                    NetworkLink.error,
                    NetworkLink.discovered_at,
                ),
                noload(NetworkLink.server),
                noload(NetworkLink.switch),
            )
            .filter(NetworkLink.server_id.in_(selected_server_ids))
            .all()
            if selected_server_ids
            else []
        )
        existing = {
            (
                row.server_id,
                row.switch_id,
                row.server_interface,
                row.server_mac,
            ): row
            for row in existing_rows
        }

        now = datetime.utcnow()
        current_keys = set()
        cleanup_server_ids = set(servers_without_switch_ids)
        results = []
        stats = {
            "total_servers": 0,
            "total_interfaces": 0,
            "found": 0,
            "not_found": 0,
            "errors": 0,
        }

        for config in server_configs:
            scan = server_scans.get(config["id"], {})
            error = scan.get("error")
            interfaces = scan.get("interfaces", [])
            scan_complete = scan.get("scan_complete", error is None)
            if not scan_complete and not error:
                error = "interface scan did not complete"
            server_result = {
                "server_id": config["id"],
                "server_ip": config["ip"],
                "interfaces": [],
                "error": error,
            }
            if error:
                stats["errors"] += 1
                results.append(server_result)
                continue

            cleanup_server_ids.add(config["id"])
            stats["total_servers"] += 1
            for iface in interfaces:
                stats["total_interfaces"] += 1
                iface_result = {
                    "name": iface["name"],
                    "ip": iface.get("ip"),
                    "mac": iface["mac"],
                    "ping_error": iface.get("_ping_error"),
                    "switches": [],
                }
                for switch_id in config["switch_ids"]:
                    switch = switch_snapshots.get(switch_id)
                    if not switch:
                        continue
                    switch_scan = switch_scans.get(switch_id, {})
                    switch_error = switch_scan.get("error")
                    found_entry = switch_scan.get("mac_map", {}).get(iface["mac"])
                    if found_entry:
                        status = "found"
                        switch_interface = found_entry.get("interface")
                        vlan = found_entry.get("vlan")
                        link_error = None
                        stats["found"] += 1
                    elif switch_error:
                        status = "error"
                        switch_interface = None
                        vlan = None
                        link_error = switch_error
                        stats["errors"] += 1
                    else:
                        status = "not_found"
                        switch_interface = None
                        vlan = None
                        link_error = None
                        stats["not_found"] += 1

                    key = (config["id"], switch_id, iface["name"], iface["mac"])
                    current_keys.add(key)
                    link = existing.get(key)
                    if not link:
                        link = NetworkLink(
                            server_id=config["id"],
                            switch_id=switch_id,
                            server_interface=iface["name"],
                            server_mac=iface["mac"],
                        )
                        db.add(link)
                        existing[key] = link

                    link.server_ip = iface.get("ip")
                    link.switch_interface = switch_interface
                    link.vlan = vlan
                    link.status = status
                    link.raw_output = None
                    link.error = link_error
                    link.discovered_at = now

                    iface_result["switches"].append({
                        "switch_id": switch_id,
                        "switch_name": switch["name"],
                        "status": status,
                        "switch_interface": switch_interface,
                        "vlan": vlan,
                        "error": link_error,
                    })
                server_result["interfaces"].append(iface_result)
            results.append(server_result)

        for key, link in existing.items():
            if link.server_id in cleanup_server_ids and key not in current_keys:
                db.delete(link)

        db.commit()
        return {"servers": results, "stats": stats}
    except Exception:
        db.rollback()
        raise
    finally:
        DISCOVERY_LOCK.release()
