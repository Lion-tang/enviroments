from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.audit_log import LOG_DIR, clear_log, read_json_lines, server_log_path
from app.models.server import Server
import os

router = APIRouter(prefix="/servers/{server_id}/logs", tags=["logs"], dependencies=[Depends(get_current_user)])


@router.get("")
def get_logs(server_id: int, limit: int = Query(200, ge=1, le=2000), db: Session = Depends(get_db)):
    """Read JSON log lines from backend/log/{server_ip}.log."""
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    return read_json_lines(server_log_path(server.ip), limit)


@router.delete("/clear", status_code=204)
def clear_logs(server_id: int, db: Session = Depends(get_db)):
    """Clear the server's IP-based log file."""
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    path = server_log_path(server.ip)
    clear_log(path)


# ─── Switch logs ────────────────────────────────────────────────────────────────

switch_logs_router = APIRouter(prefix="/switches/{switch_id}/logs", tags=["switch_logs"], dependencies=[Depends(get_current_user)])


@switch_logs_router.get("")
def get_switch_logs(switch_id: int, limit: int = Query(200, ge=1, le=2000)):
    """Read JSON log lines from backend/log/switch_{switch_id}.log"""
    path = os.path.join(LOG_DIR, f"switch_{switch_id}.log")
    return read_json_lines(path, limit)


@switch_logs_router.delete("/clear", status_code=204)
def clear_switch_logs(switch_id: int):
    """Clear the switch's log file."""
    path = os.path.join(LOG_DIR, f"switch_{switch_id}.log")
    clear_log(path)
