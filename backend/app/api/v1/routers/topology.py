from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, defer, noload

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.topology_discovery import DiscoveryBusyError, discover_topology_records
from app.models.network_link import NetworkLink
from app.models.server import Server
from app.models.switch import Switch

router = APIRouter(prefix="/topology", tags=["topology"], dependencies=[Depends(get_current_user)])


class TopologyDiscoverRequest(BaseModel):
    server_ids: Optional[list[int]] = None

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
        "raw_output": None,
        "error": link.error,
        "discovered_at": link.discovered_at,
    }


@router.get("")
def get_topology(db: Session = Depends(get_db)):
    # 只显示有关联交换机的服务器
    servers = [
        s for s in db.query(Server).order_by(Server.ip).all()
        if s.switches
    ]
    switches = db.query(Switch).order_by(Switch.name).all()
    associated_pairs = {
        (server.id, switch.id)
        for server in servers
        for switch in server.switches
    }
    server_ids = [server.id for server in servers]
    switch_ids = [switch.id for switch in switches]
    candidate_links = (
        db.query(NetworkLink)
        .options(
            defer(NetworkLink.raw_output),
            noload(NetworkLink.server),
            noload(NetworkLink.switch),
        )
        .filter(
            NetworkLink.server_id.in_(server_ids),
            NetworkLink.switch_id.in_(switch_ids),
        )
        .all()
        if server_ids and switch_ids
        else []
    )
    links = [
        link for link in candidate_links
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
            "label": server.ip,
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
    try:
        return discover_topology_records(db, payload.server_ids)
    except DiscoveryBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
