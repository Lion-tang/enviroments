import json
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.switch import Switch
from app.models.server import Server
from app.api.v1.schemas import (
    SwitchCreate, SwitchUpdate, SwitchResponse,
    SwitchListResponse, ServerSwitchAssocRequest, ServerIdsRequest,
    SwitchDetailResponse, SwitchStatusResponse,
)
from infrastructure.ssh_client import get_switch_info_via_ssh, check_online, SwitchInfo
from app.core.audit_log import LOG_DIR as _LOG_DIR, append_json_log

router = APIRouter(prefix="/switches", tags=["switches"], dependencies=[Depends(get_current_user)])


def _write_log(switch_id: int, payload: dict):
    payload = dict(payload)
    payload["time"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    append_json_log(f"{_LOG_DIR}/switch_{switch_id}.log", payload)


def _server_cached_hostname(server: Server) -> Optional[str]:
    if not server.cached_info:
        return None
    try:
        cached = json.loads(server.cached_info)
        return cached.get("hostname")
    except Exception:
        return None


@router.get("", response_model=SwitchListResponse)
def list_switches(db: Session = Depends(get_db)):
    switches = db.query(Switch).order_by(Switch.name).all()
    return SwitchListResponse(
        total=len(switches),
        switches=[_to_response(s) for s in switches]
    )


@router.get("/{switch_id}", response_model=SwitchResponse)
def get_switch(switch_id: int, db: Session = Depends(get_db)):
    switch = db.query(Switch).filter(Switch.id == switch_id).first()
    if not switch:
        raise HTTPException(status_code=404, detail="Switch not found")
    return _to_response(switch)


@router.post("", response_model=SwitchResponse, status_code=201)
def create_switch(data: SwitchCreate, db: Session = Depends(get_db)):
    existing = db.query(Switch).filter(Switch.ip == data.ip).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"IP {data.ip} already registered")

    switch = Switch(
        name=data.name,
        ip=data.ip,
        port=data.port,
        username=data.username,
        password=data.password,
        description=data.description,
        tags=data.tags,
    )
    db.add(switch)
    db.commit()
    db.refresh(switch)
    return _to_response(switch)


@router.put("/{switch_id}", response_model=SwitchResponse)
def update_switch(switch_id: int, data: SwitchUpdate, db: Session = Depends(get_db)):
    switch = db.query(Switch).filter(Switch.id == switch_id).first()
    if not switch:
        raise HTTPException(status_code=404, detail="Switch not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(switch, field, value)

    db.commit()
    db.refresh(switch)
    return _to_response(switch)


@router.delete("/{switch_id}", status_code=204)
def delete_switch(switch_id: int, db: Session = Depends(get_db)):
    switch = db.query(Switch).filter(Switch.id == switch_id).first()
    if not switch:
        raise HTTPException(status_code=404, detail="Switch not found")
    db.delete(switch)
    db.commit()


@router.get("/{switch_id}/detail", response_model=SwitchDetailResponse)
def fetch_switch_detail(switch_id: int, db: Session = Depends(get_db)):
    """通过 SSH 采集交换机详细信息"""
    switch = db.query(Switch).filter(Switch.id == switch_id).first()
    if not switch:
        raise HTTPException(status_code=404, detail="Switch not found")

    info: SwitchInfo = get_switch_info_via_ssh(
        ip=switch.ip,
        username=switch.username,
        password=switch.password,
        port=switch.port,
    )

    now = datetime.utcnow()
    if info.error:
        _write_log(switch_id, {
            "type": "detail_fetch",
            "online": False,
            "error": info.error,
        })
        raise HTTPException(status_code=502, detail=f"SSH error: {info.error}")

    snapshot = {
        "type": "detail_fetch",
        "online": True,
        "os_type": info.os_type,
        "os_version": info.os_version,
        "board_type": info.board_type,
        "hostname": info.hostname,
        "uptime": info.uptime,
        "patch_version": info.patch_version,
        "interfaces": [],
    }
    _write_log(switch_id, snapshot)

    switch.cached_info = json.dumps(snapshot, ensure_ascii=False)
    switch.cached_at = now
    switch.is_online = True
    db.commit()

    return SwitchDetailResponse(
        id=switch.id,
        name=switch.name,
        ip=switch.ip,
        port=switch.port,
        username=switch.username,
        password=switch.password,
        description=switch.description,
        tags=switch.tags,
        is_online=True,
        os_type=info.os_type,
        os_version=info.os_version,
        hostname=info.hostname,
        board_type=info.board_type,
        uptime=info.uptime,
        patch_version=info.patch_version,
        cpu=None,
        mem=None,
        interfaces=[],
        cached_at=switch.cached_at,
        created_at=switch.created_at,
        updated_at=switch.updated_at,
    )


@router.get("/{switch_id}/status", response_model=SwitchStatusResponse)
def check_switch_status(switch_id: int, db: Session = Depends(get_db)):
    switch = db.query(Switch).filter(Switch.id == switch_id).first()
    if not switch:
        raise HTTPException(status_code=404, detail="Switch not found")

    online = check_online(switch.ip, port=switch.port)
    was_online = switch.is_online
    switch.is_online = online
    switch.online_checked_at = datetime.utcnow()
    db.commit()

    _write_log(switch_id, {
        "type": "status_check",
        "online": online,
        "changed": was_online != online,
    })

    return SwitchStatusResponse(
        name=switch.name,
        ip=switch.ip,
        online=online,
        ssh_open=online,
        message=None if online else "Switch is unreachable",
    )


# ── Assoc ────────────────────────────────────────────────────────────────────────

@router.get("/{switch_id}/servers")
def get_switch_servers(switch_id: int, db: Session = Depends(get_db)):
    """获取关联到此交换机的服务器列表（返回基本信息）"""
    switch = db.query(Switch).filter(Switch.id == switch_id).first()
    if not switch:
        raise HTTPException(status_code=404, detail="Switch not found")
    return [
        {"id": s.id, "ip": s.ip, "hostname": _server_cached_hostname(s), "os_type": s.os_type}
        for s in switch.servers
    ]


@router.post("/server/{server_id}/switches", status_code=204)
def set_server_switches(server_id: int, data: ServerSwitchAssocRequest, db: Session = Depends(get_db)):
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    switches = db.query(Switch).filter(Switch.id.in_(data.switch_ids)).all()
    server.switches = switches
    db.commit()


@router.get("/server/{server_id}/switches", response_model=SwitchListResponse)
def get_server_switches(server_id: int, db: Session = Depends(get_db)):
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    return SwitchListResponse(
        total=len(server.switches),
        switches=[_to_response(s) for s in server.switches]
    )


@router.post("/{switch_id}/servers", status_code=204)
def set_switch_servers(switch_id: int, data: ServerIdsRequest, db: Session = Depends(get_db)):
    """设置交换机关联的服务器列表（多台）"""
    switch = db.query(Switch).filter(Switch.id == switch_id).first()
    if not switch:
        raise HTTPException(status_code=404, detail="Switch not found")
    servers = db.query(Server).filter(Server.id.in_(data.server_ids)).all()
    switch.servers = servers
    db.commit()


def _to_response(switch: Switch) -> SwitchResponse:
    board_type = None
    if switch.cached_info:
        try:
            cached = json.loads(switch.cached_info)
            board_type = cached.get("board_type")
        except Exception:
            pass

    return SwitchResponse(
        id=switch.id,
        name=switch.name,
        ip=switch.ip,
        board_type=board_type,
        port=switch.port,
        username=switch.username,
        password=switch.password,
        description=switch.description,
        tags=switch.tags,
        created_at=switch.created_at,
        updated_at=switch.updated_at,
        assoc_server_count=len(switch.servers) if switch.servers else 0,
    )
