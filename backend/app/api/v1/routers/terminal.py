"""
SSH Web Terminal API - WebSocket based (webssh pattern)
POST /api/v1/terminal/connect  -> 创建 session，返回 worker_id
WebSocket /api/v1/terminal/ws  -> 交互数据
"""

import asyncio
import json
import logging
import re
import socket
import secrets
from typing import Optional

import paramiko

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.server import Server
from app.models.switch import Switch
from infrastructure.ssh_worker import SSHWorker, TerminalManager, BUF_SIZE
from infrastructure.ssh_client import check_online

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/terminal", tags=["terminal"])

# ─── Helpers ────────────────────────────────────────────────────────────────

def is_valid_encoding(encoding: str) -> bool:
    try:
        "test".encode(encoding)
        return True
    except (LookupError, ValueError):
        return False


def get_default_encoding(ssh) -> str:
    commands = [
        '$SHELL -ilc "locale charmap"',
        '$SHELL -ic "locale charmap"'
    ]
    for cmd in commands:
        try:
            _, stdout, _ = ssh.exec_command(cmd, get_pty=True, timeout=1)
        except Exception:
            continue
        try:
            data = stdout.read()
        except socket.timeout:
            continue
        if data:
            try:
                encoding = data.strip().decode('ascii')
                if is_valid_encoding(encoding):
                    return encoding
            except Exception:
                pass
    return 'utf-8'


def is_valid_ip(ip: str) -> bool:
    import ipaddress
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


def is_valid_hostname(hostname: str) -> bool:
    if len(hostname) > 253:
        return False
    allowed = re.compile(r'(?!-)[a-z0-9-]{1,63}(?<!-)$', re.IGNORECASE)
    labels = hostname.split('.')
    return all(allowed.match(label) for label in labels)


def is_valid_port(port: int) -> bool:
    return 0 < port < 65536


def parse_private_key(privatekey: str, passphrase: str) -> Optional[paramiko.PKey]:
    from io import StringIO
    try:
        key_io = StringIO(privatekey.strip())
        line = privatekey.strip().split('\n')[0]
        if 'RSA' in line:
            name = 'RSA'
        elif 'DSA' in line:
            name = 'DSS'
        elif 'EC' in line:
            name = 'ECDSA'
        elif 'OPENSSH' in line:
            name = 'Ed25519'
        else:
            name = None

        pkey = None
        if name:
            try:
                pkey_cls = getattr(paramiko, name + 'Key')
                pkey = pkey_cls.from_private_key(key_io, password=passphrase)
            except paramiko.SSHException:
                pass

        if not pkey and name == 'Ed25519':
            for n in ['RSA', 'ECDSA', 'DSS']:
                try:
                    pkey_cls = getattr(paramiko, n + 'Key')
                    key_io.seek(0)
                    pkey = pkey_cls.from_private_key(key_io, password=passphrase)
                    break
                except Exception:
                    continue
        return pkey
    except Exception as e:
        logger.warning(f"Failed to parse private key: {e}")
        return None


# ─── POST /connect ──────────────────────────────────────────────────────────

@router.post("/connect")
async def terminal_connect(
    host: str,
    port: int = 22,
    username: str = None,
    password: str = None,
    privatekey: str = None,
    passphrase: str = None,
    totp: str = None,
    term: str = "xterm",
    encoding: str = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    if not (is_valid_hostname(host) or is_valid_ip(host)):
        raise HTTPException(status_code=400, detail="Invalid hostname")
    if not is_valid_port(port):
        raise HTTPException(status_code=400, detail="Invalid port")
    if not username:
        raise HTTPException(status_code=400, detail="Username required")

    if not check_online(host, port=port, timeout=5):
        raise HTTPException(status_code=503, detail=f"Cannot reach {host}:{port}")

    pkey = None
    if privatekey:
        pkey = parse_private_key(privatekey, passphrase)

    if not encoding:
        encoding = 'utf-8'
    elif not is_valid_encoding(encoding):
        encoding = 'utf-8'

    loop = asyncio.get_event_loop()
    try:
        worker: SSHWorker = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                _sync_ssh_connect,
                host, port, username, password, pkey, term, encoding
            ),
            timeout=30.0
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="SSH connection timeout")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"SSH connect error: {e}")
        raise HTTPException(status_code=500, detail="SSH connection failed")

    asyncio.create_task(recycle_worker(worker, delay=30.0))

    return {"id": worker.id, "encoding": worker.encoding}


def _sync_ssh_connect(host, port, username, password, pkey, term, encoding) -> SSHWorker:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(
            host, port=port, username=username, password=password, pkey=pkey,
            timeout=10, banner_timeout=10, auth_timeout=10,
            look_for_keys=False, allow_agent=False,
        )
    except socket.error as e:
        raise ValueError(f"Unable to connect to {host}:{port}: {e}")
    except paramiko.BadAuthenticationType:
        raise ValueError("Bad authentication type")
    except paramiko.AuthenticationException:
        raise ValueError("Authentication failed")
    except paramiko.BadHostKeyException:
        raise ValueError("Bad host key")

    detected_encoding = encoding
    if not encoding or encoding == 'utf-8':
        try:
            detected_encoding = get_default_encoding(ssh)
        except Exception:
            detected_encoding = 'utf-8'

    chan = ssh.invoke_shell(term=term)
    chan.setblocking(0)

    worker = SSHWorker(
        ssh_client=ssh,
        channel=chan,
        dst_addr=(host, port),
        encoding=detected_encoding,
    )
    worker.id = secrets.token_urlsafe(32)
    TerminalManager.add_worker(host, worker)

    logger.info(f"[TerminalManager] Created worker {worker.id} for {host}:{port}")
    return worker


async def recycle_worker(worker: SSHWorker, delay: float = 30.0):
    await asyncio.sleep(delay)
    if not worker.handler:
        logger.warning(f"[TerminalManager] Recycling worker {worker.id} (no handler)")
        await worker.close(reason="worker recycled")
        TerminalManager.remove_worker(worker.dst_addr[0], worker.id)


# ─── WebSocket /ws ─────────────────────────────────────────────────────────

@router.websocket("/ws")
async def terminal_websocket(websocket: WebSocket):
    await websocket.accept()

    worker_id = websocket.query_params.get("id")
    if not worker_id:
        await websocket.close(code=4000, reason="Missing worker id")
        return

    worker: Optional[SSHWorker] = None
    for ip_workers in TerminalManager.clients.values():
        w = ip_workers.get(worker_id)
        if w and not w.handler:
            worker = w
            break

    if not worker:
        await websocket.close(code=4001, reason="Worker not found or already connected")
        return

    worker.set_handler(websocket)

    reader_task = None
    try:
        reader_task = asyncio.create_task(_ssh_reader(worker))

        while True:
            msg = await websocket.receive_text()
            await handle_ws_message(worker, msg)

    except WebSocketDisconnect:
        logger.info(f"[TerminalManager] WebSocket disconnected for worker {worker.id}")
    except RuntimeError as e:
        logger.info(f"[TerminalManager] WebSocket closed for worker {worker.id}: {e}")
    except Exception as e:
        import traceback
        logger.error(f"[TerminalManager] WebSocket error for worker {worker.id}: {e}\n{traceback.format_exc()}")
    finally:
        if reader_task:
            reader_task.cancel()
        await worker.close(reason="WebSocket closed")
        for ip, workers in list(TerminalManager.clients.items()):
            if worker_id in workers:
                TerminalManager.remove_worker(ip, worker_id)
                break


async def handle_ws_message(worker: SSHWorker, message: str):
    try:
        msg = json.loads(message)
    except json.JSONDecodeError:
        return

    if not isinstance(msg, dict):
        return

    resize = msg.get("resize")
    if resize and isinstance(resize, list) and len(resize) == 2:
        try:
            worker.chan.resize_pty(int(resize[0]), int(resize[1]))
        except Exception as e:
            logger.warning(f"[handle_ws] resize error: {e}")

    data = msg.get("data")
    if data and isinstance(data, str):
        try:
            data_bytes = data.encode(worker.encoding)
            worker.chan.send(data_bytes)
        except OSError as e:
            logger.warning(f"[handle_ws] OSError on send: {e}")
            await worker.close(reason="channel write error")


CHANNEL_IDLE = object()


def _poll_channel(channel):
    """Read a nonblocking channel while preserving idle, EOF, and error states."""
    if not channel.recv_ready():
        if getattr(channel, "closed", False) or channel.exit_status_ready():
            return b""
        return CHANNEL_IDLE
    try:
        return channel.recv(BUF_SIZE)
    except Exception:
        return None


async def _ssh_reader(worker: SSHWorker):
    idle_delay = 0.05

    try:
        while not worker.closed:
            data = _poll_channel(worker.chan)

            if worker.closed:
                break

            if data is CHANNEL_IDLE:
                await asyncio.sleep(idle_delay)
                idle_delay = min(0.5, idle_delay * 1.5)
                continue

            idle_delay = 0.05
            if data is None:
                await worker.close(reason="chan recv error")
                break

            if data == b"":
                await worker.close(reason="channel closed")
                break

            # Forward to WebSocket
            if worker.handler and not worker.closed:
                try:
                    await worker.handler.send_bytes(data)
                except Exception as e:
                    await worker.close(reason="websocket closed")
                    break

    except Exception as e:
        import traceback
        logger.error(f"[_ssh_reader] worker {worker.id}: {e}\n{traceback.format_exc()}")
