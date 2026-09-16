import os
import sys
import asyncio
import warnings

# Suppress paramiko cryptography deprecation warnings
warnings.filterwarnings("ignore", message="TripleDES has been moved")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="paramiko")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="cryptography")

from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import FileResponse
from app.core.database import init_db
from app.core.request_limits import UploadBodyLimitMiddleware
from app.api.v1.routers import servers, files, switches, terminal, topology
from app.api.v1.routers import logs as logs_router
from app.api.v1.routers.logs import switch_logs_router
from app.api.v1.routers import auth


def get_frontend_dist():
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, "frontend", "dist")
    else:
        return os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "frontend", "dist"
        )


FRONTEND_DIST = get_frontend_dist()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Start background scheduler after database init
    from app.core.scheduler import create_scheduler
    scheduler = create_scheduler(app)
    scheduler.start()
    print("[Enviroments] Background scheduler started")
    yield
    scheduler.shutdown()
    print("[Enviroments] Background scheduler stopped")


app = FastAPI(title="Enviroments", version="1.0.0", lifespan=lifespan)
app.add_middleware(UploadBodyLimitMiddleware)

app.include_router(servers.router, prefix="/api/v1")
app.include_router(files.router, prefix="/api/v1")
app.include_router(logs_router.router, prefix="/api/v1")
app.include_router(switches.router, prefix="/api/v1")
app.include_router(switch_logs_router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(terminal.router, prefix="/api/v1")
app.include_router(topology.router, prefix="/api/v1")

@app.get("/")
def root():
    return FileResponse(
        os.path.join(FRONTEND_DIST, "index.html"),
        headers={"Cache-Control": "no-store"},
    )

@app.get("/assets/{filename}")
def assets(filename: str):
    return FileResponse(
        os.path.join(FRONTEND_DIST, "assets", filename),
        headers={"Cache-Control": "no-store"},
    )


@app.websocket("/ws/ssh")
async def websocket_ssh_compat(
    websocket: WebSocket,
    token: str = Query(...),
    target_type: str = Query(...),
    target_id: int = Query(...),
):
    """Compatibility stub — redirects to new terminal system."""
    await websocket.close(code=1010, reason="Use /api/v1/terminal/connect")


if getattr(sys, 'frozen', False):
    import uvicorn
    print(f"[Enviroments] FRONTEND_DIST = {FRONTEND_DIST}")
    print(f"[Enviroments] Exists: {os.path.exists(FRONTEND_DIST)}")

    _host = os.environ.get("APP_HOST", "0.0.0.0")
    _port = int(os.environ.get("APP_PORT", "8000"))
    print(f"[Enviroments] Listening on {_host}:{_port}")

    config = uvicorn.Config(app=app, host=_host, port=_port, log_level="info")
    server = uvicorn.Server(config)
    asyncio.run(server.serve())
