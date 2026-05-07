import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.network_link import NetworkLink
from app.models.server import Server
from app.models.switch import Switch
from infrastructure.ssh_client import (
    fetch_up_server_interfaces_via_ssh,
    find_mac_on_switch_via_ssh,
    stimulate_mac_learning_via_ssh,
)

router = APIRouter(prefix="/topology", tags=["topology"], dependencies=[Depends(get_current_user)])


class TopologyDiscoverRequest(BaseModel):
    server_ids: Optional[list[int]] = None


def _server_label(server: Server) -> str:
    if server.cached_info:
        try:
            cached = json.loads(server.cached_info)
            return cached.get("hostname") or server.ip
        except Exception:
            pass
    return server.ip


def _link_to_dict(link: NetworkLink) -> dict:
    return {
        "id": link.id,
        "server_id": link.server_id,
        "switch_id": link.switch_id,
        "server_interface": link.server_interface,
        "server_ip": link.server_ip,
        "server_mac": link.server_mac,
        "switch_interface": link.switch_interface,
        "vlan": link.vlan,
        "status": link.status,
        "raw_output": link.raw_output,
        "error": link.error,
        "discovered_at": link.discovered_at,
    }


def _upsert_link(
    db: Session,
    server: Server,
    switch: Switch,
    iface: dict,
    status: str,
    switch_interface: Optional[str] = None,
    vlan: Optional[str] = None,
    raw_output: Optional[str] = None,
    error: Optional[str] = None,
) -> NetworkLink:
    link = db.query(NetworkLink).filter(
        NetworkLink.server_id == server.id,
        NetworkLink.switch_id == switch.id,
        NetworkLink.server_interface == iface["name"],
        NetworkLink.server_mac == iface["mac"],
    ).first()
    if not link:
        link = NetworkLink(
            server_id=server.id,
            switch_id=switch.id,
            server_interface=iface["name"],
            server_mac=iface["mac"],
        )
        db.add(link)

    link.server_ip = iface.get("ip")
    link.switch_interface = switch_interface
    link.vlan = vlan
    link.status = status
    link.raw_output = raw_output
    link.error = error
    link.discovered_at = datetime.utcnow()
    db.commit()
    db.refresh(link)
    return link


@router.get("")
def get_topology(db: Session = Depends(get_db)):
    servers = db.query(Server).order_by(Server.ip).all()
    switches = db.query(Switch).order_by(Switch.name).all()
    associated_pairs = {
        (server.id, switch.id)
        for server in servers
        for switch in server.switches
    }
    links = [
        link for link in db.query(NetworkLink).all()
        if (link.server_id, link.switch_id) in associated_pairs
    ]

    nodes = []
    for switch in switches:
        nodes.append({
            "id": f"switch-{switch.id}",
            "type": "switch",
            "entity_id": switch.id,
            "label": switch.name,
            "ip": switch.ip,
            "online": switch.is_online,
            "tags": switch.tags,
            "assoc_count": len(switch.servers) if switch.servers else 0,
        })

    for server in servers:
        nodes.append({
            "id": f"server-{server.id}",
            "type": "server",
            "entity_id": server.id,
            "label": _server_label(server),
            "ip": server.ip,
            "online": server.is_online,
            "tags": server.tags,
            "occupied_by": server.occupied_by,
            "assoc_count": len(server.switches) if server.switches else 0,
        })

    discovered = [
        {
            "id": f"link-{link.id}",
            "source": f"switch-{link.switch_id}",
            "target": f"server-{link.server_id}",
            "kind": "discovered",
            "status": link.status,
            "server_interface": link.server_interface,
            "server_ip": link.server_ip,
            "server_mac": link.server_mac,
            "switch_interface": link.switch_interface,
            "vlan": link.vlan,
            "discovered_at": link.discovered_at,
        }
        for link in links
    ]

    discovered_pairs = {
        (link.server_id, link.switch_id)
        for link in links
        if link.status == "found"
    }
    assoc_edges = []
    for server in servers:
        for switch in server.switches:
            if (server.id, switch.id) in discovered_pairs:
                continue
            assoc_edges.append({
                "id": f"assoc-{switch.id}-{server.id}",
                "source": f"switch-{switch.id}",
                "target": f"server-{server.id}",
                "kind": "association",
                "status": "associated",
            })

    return {
        "nodes": nodes,
        "edges": discovered + assoc_edges,
        "links": [_link_to_dict(link) for link in links],
    }


@router.post("/discover")
def discover_topology(payload: TopologyDiscoverRequest, db: Session = Depends(get_db)):
    query = db.query(Server).order_by(Server.ip)
    if payload.server_ids:
        query = query.filter(Server.id.in_(payload.server_ids))
    servers = query.all()

    results = []
    for server in servers:
        server_result = {
            "server_id": server.id,
            "server_ip": server.ip,
            "interfaces": [],
            "error": None,
        }
        if not server.switches:
            server_result["error"] = "未关联交换机"
            results.append(server_result)
            continue

        interfaces, error = fetch_up_server_interfaces_via_ssh(
            ip=server.ip,
            username=server.ssh_username,
            password=server.ssh_password,
            key_file=server.ssh_key_file,
            port=server.port,
        )
        if error:
            server_result["error"] = error
            results.append(server_result)
            continue

        for iface in interfaces:
            ping_error = stimulate_mac_learning_via_ssh(
                ip=server.ip,
                username=server.ssh_username,
                password=server.ssh_password,
                key_file=server.ssh_key_file,
                port=server.port,
                iface=iface["name"],
                iface_ip=iface["ip"],
                prefixlen=iface.get("prefixlen"),
            )
            iface_result = {
                "name": iface["name"],
                "ip": iface["ip"],
                "mac": iface["mac"],
                "ping_error": ping_error,
                "switches": [],
            }
            for switch in server.switches:
                found = find_mac_on_switch_via_ssh(
                    ip=switch.ip,
                    port=switch.port,
                    username=switch.username,
                    password=switch.password,
                    mac=iface["mac"],
                )
                status = "found" if found.get("found") else "not_found"
                if found.get("error"):
                    status = "error"
                link = _upsert_link(
                    db=db,
                    server=server,
                    switch=switch,
                    iface=iface,
                    status=status,
                    switch_interface=found.get("interface"),
                    vlan=found.get("vlan"),
                    raw_output=found.get("raw_output"),
                    error=found.get("error"),
                )
                iface_result["switches"].append({
                    "switch_id": switch.id,
                    "switch_name": switch.name,
                    "status": status,
                    "switch_interface": link.switch_interface,
                    "vlan": link.vlan,
                    "error": link.error,
                })
            server_result["interfaces"].append(iface_result)
        results.append(server_result)

    return {"servers": results}
