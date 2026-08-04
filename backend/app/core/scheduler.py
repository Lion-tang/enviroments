"""Background scheduler for periodic server status and detail checks."""

import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.database import SessionLocal
from app.core.status_checks import check_server_statuses
from app.core.detail_fetch import fetch_server_details
from app.core.topology_discovery import DiscoveryBusyError, discover_topology_records
from app.models.server import Server

logger = logging.getLogger("scheduler")


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
        due_ids = []
        for server in servers:
            # Rate limit: skip if checked recently per interval
            if server.online_checked_at:
                elapsed = (now - server.online_checked_at).total_seconds() / 60
                if elapsed < (server.status_check_interval or 5):
                    continue

            due_ids.append(server.id)

        result = check_server_statuses(db, due_ids)
        logger.info(
            "[Scheduler] Status check done for %s/%s servers",
            result["total"],
            len(servers),
        )
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
        due_ids = []
        for server in servers:
            if not server.is_online:
                continue
            # Rate limit: skip if fetched recently per interval
            if server.cached_at:
                elapsed = (now - server.cached_at).total_seconds() / 60
                if elapsed < (server.detail_fetch_interval or 30):
                    continue

            due_ids.append(server.id)

        result = fetch_server_details(db, due_ids)
        logger.info(
            "[Scheduler] Detail fetch done for %s/%s servers (%s errors)",
            result["fetched"],
            len(servers),
            result["errors"],
        )
    except Exception as e:
        logger.error(f"[Scheduler] Detail fetch error: {e}")
        db.rollback()
    finally:
        db.close()


def topology_discovery_task(app):
    """SSH discover network topology: match server interfaces to switch MAC tables."""
    db = SessionLocal()
    try:
        logger.info("[Scheduler] Topology discovery started")
        result = discover_topology_records(db)
        stats = result["stats"]
        logger.info(
            "[Scheduler] Topology discovery done: %d servers, %d interfaces, "
            "%d found, %d not_found, %d errors",
            stats["total_servers"], stats["total_interfaces"],
            stats["found"], stats["not_found"], stats["errors"],
        )
    except DiscoveryBusyError:
        logger.info("[Scheduler] Topology discovery already running; skipped")
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
