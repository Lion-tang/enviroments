import json
import os
import re
from collections import deque
from datetime import datetime, timezone
from threading import Lock
from typing import Any


LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "log")
MAX_LOG_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 5
_LOG_LOCK = Lock()


def server_log_filename(ip: str) -> str:
    """Return a stable log filename for a server IP address."""
    safe_ip = re.sub(r'[\\/:*?"<>|]', "_", ip or "unknown")
    return f"{safe_ip}.log"


def server_log_path(ip: str) -> str:
    return os.path.join(LOG_DIR, server_log_filename(ip))


def write_server_log(ip: str, payload: dict[str, Any]) -> None:
    """Append a JSON line to backend/log/{ip}.log using local deployment time."""
    os.makedirs(LOG_DIR, exist_ok=True)
    payload = dict(payload)
    payload["ip"] = ip
    payload["time"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    append_json_log(server_log_path(ip), payload)


def append_json_log(
    path: str,
    payload: dict[str, Any],
    max_bytes: int = MAX_LOG_BYTES,
    backup_count: int = LOG_BACKUP_COUNT,
) -> None:
    """Append one JSON line and rotate bounded backups before exceeding max_bytes."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    encoded_size = len(line.encode("utf-8"))

    with _LOG_LOCK:
        current_size = os.path.getsize(path) if os.path.exists(path) else 0
        if current_size and current_size + encoded_size > max_bytes:
            if backup_count > 0:
                oldest = f"{path}.{backup_count}"
                if os.path.exists(oldest):
                    os.remove(oldest)
                for index in range(backup_count - 1, 0, -1):
                    source = f"{path}.{index}"
                    if os.path.exists(source):
                        os.replace(source, f"{path}.{index + 1}")
                os.replace(path, f"{path}.1")
            else:
                os.remove(path)

        with open(path, "a", encoding="utf-8") as file_handle:
            file_handle.write(line)


def clear_log(path: str, backup_count: int = LOG_BACKUP_COUNT) -> None:
    """Remove the active log and its managed backups under the writer lock."""
    with _LOG_LOCK:
        for candidate in [path, *(f"{path}.{index}" for index in range(1, backup_count + 1))]:
            if os.path.exists(candidate):
                os.remove(candidate)


def read_json_lines(path: str, limit: int = 200) -> dict[str, Any]:
    if not os.path.exists(path):
        return {"total": 0, "logs": []}

    recent_lines = deque(maxlen=limit)
    total = 0
    with open(path, "r", encoding="utf-8") as file_handle:
        for line in file_handle:
            total += 1
            recent_lines.append(line)

    recent = reversed(recent_lines)
    logs = []
    for raw in recent:
        raw = raw.strip()
        if raw:
            try:
                logs.append(json.loads(raw))
            except Exception:
                logs.append({"raw": raw})

    return {"total": total, "logs": logs}
