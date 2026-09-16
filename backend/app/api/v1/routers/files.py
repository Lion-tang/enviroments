import base64
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from app.core.auth import get_current_user
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.core.database import SessionLocal
from app.core.request_limits import MAX_UPLOAD_BYTES
from app.models.server import Server
from infrastructure.sftp_client import (
    create_directory,
    list_directory,
    stream_file,
    upload_file,
    upload_stream,
)

router = APIRouter(prefix="/servers/{server_id}/files", tags=["files"], dependencies=[Depends(get_current_user)])


# ── Request/Response models ────────────────────────────────────────────────────

class FileListResponse(BaseModel):
    path: str
    entries: list


class UploadRequest(BaseModel):
    path: str        # remote destination path (including filename)
    content: str     # base64 encoded


class MkdirRequest(BaseModel):
    path: str


# ── GET  /servers/:id/files?path=... ──────────────────────────────────────────

@router.get("")
def list_files(server_id: int, path: str = "."):
    connection = _get_server_connection(server_id)

    try:
        entries = list_directory(
            **connection,
            remote_path=path,
        )
        return {
            "path": path,
            "entries": [e.__dict__ for e in entries],
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"SFTP error: {e}")


# ── GET  /servers/:id/files/download?path=... ──────────────────────────────────

@router.get("/download")
def download(server_id: int, path: str):
    connection = _get_server_connection(server_id)

    try:
        chunks = stream_file(
            **connection,
            remote_path=path,
        )
        filename = path.split("/")[-1]
        return StreamingResponse(
            chunks,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": (
                    f"attachment; filename*=UTF-8''{quote(filename)}"
                )
            },
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Download error: {e}")


# ── POST  /servers/:id/files/upload ────────────────────────────────────────────

@router.post("")
def upload(server_id: int, payload: UploadRequest):
    connection = _get_server_connection(server_id)

    try:
        if len(payload.content) > ((MAX_UPLOAD_BYTES + 2) // 3) * 4:
            raise HTTPException(status_code=413, detail="File is too large")
        content = base64.b64decode(payload.content, validate=True)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File is too large")
        result = upload_file(
            **connection,
            remote_path=payload.path,
            content=content,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Upload error: {e}")


@router.post("/upload")
def upload_multipart(
    server_id: int,
    path: str = Form(...),
    file: UploadFile = File(...),
):
    """Stream a multipart upload to SFTP with bounded memory usage."""
    connection = _get_server_connection(server_id)
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is too large")
    try:
        return upload_stream(
            **connection,
            remote_path=path,
            source=file.file,
            max_bytes=MAX_UPLOAD_BYTES,
        )
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Upload error: {exc}")
    finally:
        file.file.close()


@router.post("/mkdir")
def mkdir(server_id: int, payload: MkdirRequest):
    connection = _get_server_connection(server_id)

    try:
        result = create_directory(
            **connection,
            remote_path=payload.path,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Mkdir error: {e}")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_server_connection(server_id: int) -> dict:
    """Read credentials into plain data and release the DB session immediately."""
    db = SessionLocal()
    try:
        server = db.query(Server).filter(Server.id == server_id).first()
        if not server:
            raise HTTPException(status_code=404, detail="Server not found")
        return {
            "ip": server.ip,
            "port": server.port,
            "username": server.ssh_username,
            "password": server.ssh_password,
            "key_file": server.ssh_key_file,
        }
    finally:
        db.close()
