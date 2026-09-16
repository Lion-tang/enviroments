"""Bounded server status probing shared by API and scheduler."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.core.audit_log import write_server_log
from app.models.server import Server
from infrastructure.ssh_client import check_online


STATUS_WORKERS = 10


def check_server_statuses(
    db: Session,
    server_ids: Optional[list[int]] = None,
    *,
    checker: Callable[[str, int], bool] = check_online,
    log_writer: Callable = write_server_log,
    max_workers: int = STATUS_WORKERS,
) -> dict:
    """Probe servers concurrently, isolate failures, and persist in one transaction."""
    query = db.query(
        Server.id,
        Server.ip,
        Server.port,
        Server.is_online,
    ).order_by(Server.ip)
    if server_ids is not None:
        if not server_ids:
            return {"results": [], "online": 0, "total": 0}
        query = query.filter(Server.id.in_(server_ids))

    configs = [
        {
            "id": row.id,
            "ip": row.ip,
            "port": row.port,
            "was_online": row.is_online,
        }
        for row in query.all()
    ]
    db.rollback()

    results_by_id = {}
    if configs:
        with ThreadPoolExecutor(max_workers=min(max_workers, len(configs))) as executor:
            futures = {
                executor.submit(checker, config["ip"], config["port"]): config
                for config in configs
            }
            for future in as_completed(futures):
                config = futures[future]
                try:
                    results_by_id[config["id"]] = {
                        "server_id": config["id"],
                        "ip": config["ip"],
                        "online": bool(future.result()),
                        "error": None,
                    }
                except Exception as exc:
                    results_by_id[config["id"]] = {
                        "server_id": config["id"],
                        "ip": config["ip"],
                        "online": None,
                        "error": str(exc),
                    }

    now = datetime.utcnow()
    updates = [
        {
            "id": result["server_id"],
            "is_online": result["online"],
            "online_checked_at": now,
        }
        for result in results_by_id.values()
        if result["error"] is None
    ]
    try:
        if updates:
            db.bulk_update_mappings(Server, updates)
        db.commit()
    except Exception:
        db.rollback()
        raise

    config_by_id = {config["id"]: config for config in configs}
    ordered_results = [results_by_id[config["id"]] for config in configs]
    for result in ordered_results:
        config = config_by_id[result["server_id"]]
        payload = {
            "type": "status_check",
            "online": result["online"],
            "changed": (
                result["online"] is not None
                and config["was_online"] != result["online"]
            ),
        }
        if result["error"]:
            payload["error"] = result["error"]
        log_writer(result["ip"], payload)

    return {
        "results": ordered_results,
        "online": sum(result["online"] is True for result in ordered_results),
        "total": len(ordered_results),
    }
