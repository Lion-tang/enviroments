import json
import httpx
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.audit_log import write_server_log
from app.models.server import Server
from app.models.server_favorite import ServerFavorite
from app.api.v1.schemas import (
    ServerCreate, ServerUpdate, ServerResponse,
    ServerListResponse, StatusCheckResponse, ServerDetailResponse,
    BatchStatusRequest,
)
from app.core.status_checks import check_server_statuses
from infrastructure.ssh_client import get_server_info_via_ssh, check_online, ServerInfo

router = APIRouter(prefix="/servers", tags=["servers"], dependencies=[Depends(get_current_user)])


SENSITIVE_FIELDS = {"ssh_password", "bmc_password", "ssh_key_file"}


def _actor_name(current_user) -> str:
    return getattr(current_user, "username", None) or getattr(current_user, "email", None) or str(getattr(current_user, "id", "unknown"))


def _audit_value(field: str, value):
    if field in SENSITIVE_FIELDS:
        return "<set>" if value else None
    return value


def _server_snapshot(server: Server) -> dict:
    return {
        "server_id": server.id,
        "ip": server.ip,
        "port": server.port,
        "os_type": server.os_type,
        "ssh_username": server.ssh_username,
        "has_ssh_password": bool(server.ssh_password),
        "has_ssh_key_file": bool(server.ssh_key_file),
        "description": server.description,
        "detail_note": server.detail_note,
        "tags": server.tags,
        "bmc_ip": server.bmc_ip,
        "bmc_username": server.bmc_username,
        "has_bmc_password": bool(server.bmc_password),
        "dpu": server.dpu,
        "occupied_by": server.occupied_by,
        "occupied_at": server.occupied_at.isoformat() if server.occupied_at else None,
    }


def _update_server_fields(db: Session, server_id: int, values: dict) -> bool:
    updated = db.query(Server).filter(Server.id == server_id).update(
        values,
        synchronize_session=False,
    )
    db.commit()
    return updated == 1


@router.get("", response_model=ServerListResponse)
def list_servers(
    compact: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    servers = db.query(Server).order_by(Server.ip).all()
    favorite_ids = _favorite_server_ids(db, current_user.id)
    return ServerListResponse(
        total=len(servers),
        servers=[
            _to_response(s, s.id in favorite_ids, compact=compact)
            for s in servers
        ]
    )


@router.post("/status/batch")
def check_status_batch(payload: BatchStatusRequest, db: Session = Depends(get_db)):
    return check_server_statuses(db, payload.server_ids)


@router.post("/{server_id}/occupy", response_model=ServerResponse)
def occupy_server(server_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """占用服务器；如果已被他人占用，则由当前用户强制接管。"""
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    previous = server.occupied_by
    previous_at = server.occupied_at
    server.occupied_by = current_user.username
    server.occupied_at = datetime.now()
    db.commit()
    db.refresh(server)
    write_server_log(server.ip, {
        "type": "server_update",
        "action": "occupy",
        "actor": _actor_name(current_user),
        "server_id": server.id,
        "changes": {
            "occupied_by": {
                "old": previous,
                "new": server.occupied_by,
            },
            "occupied_at": {
                "old": previous_at.isoformat() if previous_at else None,
                "new": server.occupied_at.isoformat() if server.occupied_at else None,
            },
        },
    })
    return _to_response(server)


@router.post("/{server_id}/release", response_model=ServerResponse)
def release_server(server_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """閲婃斁鏈嶅姟鍣紙鍙湁鏈汉鎴栫鐞嗗憳鍙噴鏀撅級"""
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    if server.occupied_by and server.occupied_by != current_user.username:
        raise HTTPException(status_code=403, detail="鍙兘鏈汉鎴栫鐞嗗憳閲婃斁")
    previous = server.occupied_by
    previous_at = server.occupied_at
    server.occupied_by = None
    server.occupied_at = None
    db.commit()
    db.refresh(server)
    write_server_log(server.ip, {
        "type": "server_update",
        "action": "release",
        "actor": _actor_name(current_user),
        "server_id": server.id,
        "changes": {
            "occupied_by": {
                "old": previous,
                "new": None,
            },
            "occupied_at": {
                "old": previous_at.isoformat() if previous_at else None,
                "new": None,
            },
        },
    })
    return _to_response(server)


@router.get("/{server_id}", response_model=ServerResponse)
def get_server(server_id: int, db: Session = Depends(get_db)):
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    return _to_response(server)


@router.post("/{server_id}/favorite", response_model=ServerResponse)
def favorite_server(server_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    existing = db.query(ServerFavorite).filter(
        ServerFavorite.user_id == current_user.id,
        ServerFavorite.server_id == server_id,
    ).first()
    if not existing:
        db.add(ServerFavorite(user_id=current_user.id, server_id=server_id))
        db.commit()

    return _to_response(server, is_favorite=True)


@router.delete("/{server_id}/favorite", response_model=ServerResponse)
def unfavorite_server(server_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    favorite = db.query(ServerFavorite).filter(
        ServerFavorite.user_id == current_user.id,
        ServerFavorite.server_id == server_id,
    ).first()
    if favorite:
        db.delete(favorite)
        db.commit()

    return _to_response(server, is_favorite=False)


@router.post("", response_model=ServerResponse, status_code=201)
def create_server(data: ServerCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    existing = db.query(Server).filter(Server.ip == data.ip).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"IP {data.ip} already registered")

    server = Server(
        ip=data.ip,
        port=data.port,
        os_type=data.os_type,
        ssh_username=data.ssh_username,
        ssh_password=data.ssh_password,
        ssh_key_file=data.ssh_key_file,
        description=data.description,
        detail_note=data.detail_note,
        tags=data.tags,
        bmc_ip=data.bmc_ip,
        bmc_username=data.bmc_username,
        bmc_password=data.bmc_password,
        dpu=data.dpu,
    )
    db.add(server)
    db.commit()
    db.refresh(server)
    write_server_log(server.ip, {
        "type": "server_create",
        "action": "create",
        "actor": _actor_name(current_user),
        "server": _server_snapshot(server),
    })
    return _to_response(server)


@router.put("/{server_id}", response_model=ServerResponse)
def update_server(server_id: int, data: ServerUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    old_ip = server.ip
    changes = {}
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        old_value = getattr(server, field)
        if old_value != value:
            changes[field] = {
                "old": _audit_value(field, old_value),
                "new": _audit_value(field, value),
            }
        setattr(server, field, value)

    db.commit()
    db.refresh(server)
    if changes:
        payload = {
            "type": "server_update",
            "action": "update",
            "actor": _actor_name(current_user),
            "server_id": server.id,
            "changes": changes,
        }
        write_server_log(old_ip, payload)
        if server.ip != old_ip:
            moved_payload = dict(payload)
            moved_payload["moved_from_ip"] = old_ip
            write_server_log(server.ip, moved_payload)
    return _to_response(server)


@router.delete("/{server_id}", status_code=204)
def delete_server(server_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    log_ip = server.ip
    snapshot = _server_snapshot(server)
    db.query(ServerFavorite).filter(ServerFavorite.server_id == server_id).delete()
    db.delete(server)
    db.commit()
    write_server_log(log_ip, {
        "type": "server_delete",
        "action": "delete",
        "actor": _actor_name(current_user),
        "server": snapshot,
    })


@router.get("/{server_id}/status", response_model=StatusCheckResponse)
def check_status(server_id: int, db: Session = Depends(get_db)):
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    online = check_online(server.ip, port=server.port)
    was_online = server.is_online
    if not _update_server_fields(db, server_id, {
        "is_online": online,
        "online_checked_at": datetime.utcnow(),
    }):
        raise HTTPException(status_code=404, detail="Server not found")

    write_server_log(server.ip, {
        "type": "status_check",
        "online": online,
        "changed": was_online != online,
    })

    return StatusCheckResponse(
        ip=server.ip,
        online=online,
        ssh_open=online,
        message=None if online else "Server is unreachable"
    )


@router.get("/{server_id}/open-bmc")
def open_bmc(server_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """
    打了 BMC Web 界面，自动用 BMC 账号密码登录（Redfish Session）。
    返回 BMC URL，前端在新标签页打开。
    """
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    if not server.bmc_ip:
        raise HTTPException(status_code=400, detail="该服务器未配置 BMC IP")

    bmc_url = f"https://{server.bmc_ip}"
    username = server.bmc_username or ""
    password = server.bmc_password or ""

    headers = {"Content-Type": "application/json"}
    payload = {"UserName": username, "Password": password}

    try:
        with httpx.Client(verify=False, timeout=10.0) as client:
            resp = client.post(
                f"{bmc_url}/redfish/v1/SessionService/Sessions/",
                headers=headers,
                json=payload,
            )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"BMC 连接失败: {e}")

    if resp.status_code in (200, 201):
        token = resp.headers.get("X-Auth-Token", "")
        location = resp.headers.get("Location", "")
        # 返回 BMC URL，token 放在 URL 参数里（部分 BMC 支持）
        return {"bmc_url": bmc_url, "token": token, "location": location}
    elif resp.status_code == 401:
        raise HTTPException(status_code=401, detail="BMC 账号或密码错误")
    else:
        raise HTTPException(status_code=502, detail=f"BMC 登录失败: HTTP {resp.status_code} - {resp.text[:200]}")


@router.get("/{server_id}/detail", response_model=ServerDetailResponse)
def fetch_detail(server_id: int, refresh: bool = False, db: Session = Depends(get_db)):
    """
    鑾峰彇鏈嶅姟鍣ㄨ鎯呫€?
    - refresh=false锛堥粯璁わ級锛氫紭鍏堜粠 cached_info 杩斿洖锛屾绉掔骇鍝嶅簲
    - refresh=true锛氬己鍒?SSH 閲嶆柊閲囬泦锛?閲嶆柊閲囬泦"鎸夐挳浣跨敤锛?
    """
    server = db.query(Server).filter(Server.id == server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    # 涓嶅己鍒跺埛鏂版椂锛屼紭鍏堣繑鍥炵紦瀛?
    if not refresh and server.cached_info:
        try:
            cached = json.loads(server.cached_info)
            return ServerDetailResponse(
                id=server_id,
                ip=server.ip,
                os_type=cached.get("os_type", server.os_type),
                os_version=cached.get("os_version"),
                cpu_model=cached.get("cpu_model"),
                cpu=cached.get("cpu"),
                mem=cached.get("mem"),
                interfaces=cached.get("interfaces") or [],
                is_online=server.is_online,
                description=server.description,
                detail_note=server.detail_note,
                tags=server.tags,
                cached_at=server.cached_at,
            )
        except Exception:
            pass  # 缂撳瓨鎹熷潖锛岄檷绾у埌 SSH 閲囬泦

    # SSH 閲嶆柊閲囬泦
    detail_context = {
        "ip": server.ip,
        "username": server.ssh_username,
        "password": server.ssh_password,
        "key_file": server.ssh_key_file,
        "port": server.port,
        "description": server.description,
        "detail_note": server.detail_note,
        "tags": server.tags,
    }

    info: ServerInfo = get_server_info_via_ssh(
        ip=detail_context["ip"],
        username=detail_context["username"],
        password=detail_context["password"],
        key_file=detail_context["key_file"],
        port=detail_context["port"],
    )

    now = datetime.utcnow()
    if info.error:
        write_server_log(detail_context["ip"], {
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
        "cpu_model": info.cpu_model,
        "cpu": info.cpu_count,
        "mem": info.memory_total,
        "interfaces": info.interfaces or [],
        "hostname": info.hostname,
    }
    write_server_log(detail_context["ip"], snapshot)

    if not _update_server_fields(db, server.id, {
        "cached_info": json.dumps(snapshot, ensure_ascii=False),
        "cached_at": now,
        "is_online": True,
    }):
        raise HTTPException(status_code=404, detail="Server not found")

    return ServerDetailResponse(
        id=server_id,
        ip=detail_context["ip"],
        os_type=info.os_type,
        os_version=info.os_version,
        cpu_model=info.cpu_model,
        cpu=info.cpu_count,
        mem=info.memory_total,
        interfaces=info.interfaces or [],
        is_online=True,
        description=detail_context["description"],
        detail_note=detail_context["detail_note"],
        tags=detail_context["tags"],
        cached_at=now,
    )


def _favorite_server_ids(db: Session, user_id: int) -> set[int]:
    rows = db.query(ServerFavorite.server_id).filter(ServerFavorite.user_id == user_id).all()
    return {server_id for (server_id,) in rows}


def _to_response(
    server: Server,
    is_favorite: bool = False,
    compact: bool = False,
) -> ServerResponse:
    cached_info = None
    cached_os_version = None
    cached_cpu_model = None
    cached_hostname = None
    cached_mem = None
    cached_interfaces = None
    if server.cached_info:
        try:
            cached_info = json.loads(server.cached_info)
            cached_os_version = cached_info.get("os_version") if cached_info else None
            cached_cpu_model = cached_info.get("cpu_model") if cached_info else None
            cached_hostname = cached_info.get("hostname") if cached_info else None
            cached_mem = cached_info.get("mem") if cached_info else None
            cached_interfaces = cached_info.get("interfaces") if cached_info else None
        except Exception:
            pass

    return ServerResponse(
        id=server.id,
        ip=server.ip,
        port=server.port,
        os_type=server.os_type,
        ssh_username=server.ssh_username,
        ssh_password=server.ssh_password,
        ssh_key_file=server.ssh_key_file,
        description=server.description,
        detail_note=server.detail_note,
        tags=server.tags,
        bmc_ip=server.bmc_ip,
        bmc_username=server.bmc_username,
        bmc_password=server.bmc_password,
        dpu=server.dpu,
        is_online=server.is_online,
        online_checked_at=server.online_checked_at,
        cached_info=None if compact else cached_info,
        cached_at=server.cached_at,
        created_at=server.created_at,
        updated_at=server.updated_at,
        cached_os_version=cached_os_version,
        cached_cpu_model=cached_cpu_model,
        cached_hostname=cached_hostname,
        cached_mem=cached_mem,
        cached_interfaces=None if compact else cached_interfaces,
        occupied_by=server.occupied_by,
        occupied_at=server.occupied_at,
        assoc_switch_count=len(server.switches) if server.switches else 0,
        is_favorite=is_favorite,
    )
