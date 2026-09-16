from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class ServerBase(BaseModel):
    ip: str
    port: int = 22
    os_type: str = "linux"
    ssh_username: str
    ssh_password: Optional[str] = None
    ssh_key_file: Optional[str] = None
    description: Optional[str] = None
    detail_note: Optional[str] = None
    tags: str = ""
    bmc_ip: Optional[str] = None
    bmc_username: Optional[str] = None
    bmc_password: Optional[str] = None
    dpu: Optional[str] = None


class ServerCreate(ServerBase):
    pass


class ServerUpdate(BaseModel):
    ip: Optional[str] = None
    port: Optional[int] = None
    os_type: Optional[str] = None
    ssh_username: Optional[str] = None
    ssh_password: Optional[str] = None
    ssh_key_file: Optional[str] = None
    description: Optional[str] = None
    detail_note: Optional[str] = None
    tags: Optional[str] = None
    bmc_ip: Optional[str] = None
    bmc_username: Optional[str] = None
    bmc_password: Optional[str] = None
    dpu: Optional[str] = None


class ServerResponse(BaseModel):
    id: int
    ip: str
    port: int
    os_type: str
    ssh_username: str
    ssh_password: Optional[str] = None
    ssh_key_file: Optional[str] = None
    description: Optional[str] = None
    detail_note: Optional[str] = None
    tags: str
    bmc_ip: Optional[str] = None
    bmc_username: Optional[str] = None
    bmc_password: Optional[str] = None
    dpu: Optional[str] = None
    is_online: bool
    online_checked_at: Optional[datetime] = None
    cached_info: Optional[dict] = None   # JSON object
    cached_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    cached_os_version: Optional[str] = None  # extracted from cached_info
    cached_cpu_model: Optional[str] = None   # extracted from cached_info
    cached_hostname: Optional[str] = None    # extracted from cached_info
    cached_mem: Optional[int] = None         # extracted from cached_info (MB)
    cached_interfaces: Optional[list] = None # extracted from cached_info (list, light)
    occupied_by: Optional[str] = None
    occupied_at: Optional[datetime] = None
    assoc_switch_count: Optional[int] = None
    is_favorite: bool = False

    class Config:
        from_attributes = True


class ServerListResponse(BaseModel):
    total: int
    servers: list[ServerResponse]


class StatusCheckResponse(BaseModel):
    ip: str
    online: bool
    ssh_open: bool
    message: Optional[str] = None


class BatchStatusRequest(BaseModel):
    server_ids: Optional[list[int]] = None


class ServerDetailResponse(BaseModel):
    id: int
    ip: str
    os_type: str
    os_version: Optional[str] = None
    cpu_model: Optional[str] = None
    cpu: Optional[int] = None
    mem: Optional[int] = None
    interfaces: Optional[list] = None
    is_online: bool
    description: Optional[str] = None
    detail_note: Optional[str] = None
    tags: str
    cached_at: Optional[datetime] = None


# ─── Switch ────────────────────────────────────────────────────────────────────

class SwitchBase(BaseModel):
    name: str
    ip: str
    port: int = 22
    username: str
    password: Optional[str] = None
    description: Optional[str] = None
    tags: str = ""


class SwitchCreate(SwitchBase):
    pass


class SwitchUpdate(BaseModel):
    name: Optional[str] = None
    ip: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[str] = None


class SwitchResponse(BaseModel):
    id: int
    name: str
    ip: str
    board_type: Optional[str] = None
    port: int
    username: str
    password: Optional[str] = None
    description: Optional[str] = None
    tags: str
    created_at: datetime
    updated_at: datetime
    assoc_server_count: Optional[int] = None

    class Config:
        from_attributes = True


class SwitchListResponse(BaseModel):
    total: int
    switches: list[SwitchResponse]


class ServerSwitchAssocRequest(BaseModel):
    switch_ids: list[int]


class ServerIdsRequest(BaseModel):
    server_ids: list[int]


class SwitchDetailResponse(BaseModel):
    id: int
    name: str
    ip: str
    port: int
    username: str
    password: Optional[str] = None
    description: Optional[str] = None
    tags: str
    is_online: bool
    os_type: Optional[str] = None     # e.g. "H3C Comware", "Huawei VRP"
    os_version: Optional[str] = None
    hostname: Optional[str] = None
    board_type: Optional[str] = None   # e.g. "S5560-28C-PWR-EI"
    uptime: Optional[str] = None
    patch_version: Optional[str] = None
    cpu: Optional[int] = None          # CPU usage %
    mem: Optional[int] = None          # Memory usage %
    interfaces: Optional[list] = None
    cached_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SwitchStatusResponse(BaseModel):
    name: str
    ip: str
    online: bool
    ssh_open: bool
    message: Optional[str] = None
