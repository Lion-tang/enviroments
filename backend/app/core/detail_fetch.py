"""Bounded server detail collection shared by background jobs."""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.core.audit_log import write_server_log
from app.models.server import Server
from infrastructure.ssh_client import get_server_info_via_ssh


DETAIL_WORKERS = 5


def fetch_server_details(
    db: Session,
    server_ids: Optional[list[int]] = None,
    *,
    fetcher: Callable = get_server_info_via_ssh,
    log_writer: Callable = write_server_log,
    max_workers: int = DETAIL_WORKERS,
) -> dict:
    """Collect SSH details concurrently and persist successful snapshots once."""
    query = db.query(
        Server.id,
        Server.ip,
        Server.port,
        Server.ssh_username,
        Server.ssh_password,
        Server.ssh_key_file,
        Server.is_online,
    ).order_by(Server.ip)
    if server_ids is not None:
        if not server_ids:
            return {"fetched": 0, "errors": 0, "total": 0}
        query = query.filter(Server.id.in_(server_ids))

    configs = [
        {
            "id": row.id,
            "ip": row.ip,
            "port": row.port,
            "username": row.ssh_username,
            "password": row.ssh_password,
            "key_file": row.ssh_key_file,
            "is_online": row.is_online,
        }
        for row in query.all()
    ]
    db.rollback()

    outcomes = {}
    if configs:
        with ThreadPoolExecutor(max_workers=min(max_workers, len(configs))) as executor:
            futures = {
                executor.submit(
                    fetcher,
                    ip=config["ip"],
                    username=config["username"],
                    password=config["password"],
                    key_file=config["key_file"],
                    port=config["port"],
                ): config
                for config in configs
            }
            for future in as_completed(futures):
                config = futures[future]
                try:
                    info = future.result()
                    error = getattr(info, "error", None)
                    outcomes[config["id"]] = (info, error)
                except Exception as exc:
                    outcomes[config["id"]] = (None, str(exc))

    now = datetime.utcnow()
    updates = []
    snapshots = {}
    for config in configs:
        info, error = outcomes[config["id"]]
        if error:
            continue
        snapshot = {
            "type": "detail_fetch",
            "online": True,
            "os_type": info.os_type,
            "os_version": info.os_version,
            "cpu_model": info.cpu_model,
            "cpu": info.cpu_count,
            "mem": info.memory_total,
            "interfaces": info.interfaces or [],
            "hostname": info.hostname,
        }
        snapshots[config["id"]] = snapshot
        updates.append({
            "id": config["id"],
            "cached_info": json.dumps(snapshot, ensure_ascii=False),
            "cached_at": now,
            "is_online": True,
        })

    try:
        if updates:
            db.bulk_update_mappings(Server, updates)
        db.commit()
    except Exception:
        db.rollback()
        raise

    errors = 0
    for config in configs:
        _info, error = outcomes[config["id"]]
        if error:
            errors += 1
            log_writer(config["ip"], {
                "type": "detail_fetch",
                "online": config["is_online"],
                "error": error,
            })
        else:
            log_writer(config["ip"], snapshots[config["id"]])

    return {
        "fetched": len(updates),
        "errors": errors,
        "total": len(configs),
    }
