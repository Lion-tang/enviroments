from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.topology_discovery as discovery
from app.api.v1.routers.topology import _link_to_dict
from app.core.database import Base
from app.models.network_link import NetworkLink
from app.models.server import Server
from app.models.switch import Switch


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_discovery_batches_updates_and_removes_stale_links(monkeypatch):
    db = _session()
    server = Server(ip="10.0.0.1", port=22, ssh_username="root")
    switch = Switch(name="sw1", ip="10.0.0.2", port=22, username="admin")
    server.switches = [switch]
    db.add_all([server, switch])
    db.commit()

    monkeypatch.setattr(
        discovery,
        "_scan_server",
        lambda _config: {
            "interfaces": [{
                "name": "eth0",
                "ip": "10.0.0.1",
                "mac": "aa:bb:cc:dd:ee:ff",
                "_ping_error": None,
            }],
            "error": None,
        },
    )
    monkeypatch.setattr(
        discovery,
        "_scan_switch",
        lambda _config: {
            "mac_map": {
                "aa:bb:cc:dd:ee:ff": {
                    "interface": "GE1/0/1",
                    "vlan": "10",
                }
            },
            "raw_output": "large raw table",
            "error": None,
        },
    )

    result = discovery.discover_topology_records(db)
    assert result["stats"]["found"] == 1
    link = db.query(NetworkLink).one()
    assert link.switch_interface == "GE1/0/1"
    assert link.raw_output is None
    assert _link_to_dict(link)["raw_output"] is None

    monkeypatch.setattr(
        discovery,
        "_scan_server",
        lambda _config: {"interfaces": [], "error": None},
    )
    discovery.discover_topology_records(db)
    assert db.query(NetworkLink).count() == 0
    db.close()


def test_discovery_rejects_overlapping_runs():
    db = _session()
    discovery.DISCOVERY_LOCK.acquire()
    try:
        try:
            discovery.discover_topology_records(db)
        except discovery.DiscoveryBusyError:
            pass
        else:
            raise AssertionError("overlapping discovery should be rejected")
    finally:
        discovery.DISCOVERY_LOCK.release()
        db.close()


def test_incomplete_server_scan_preserves_existing_links(monkeypatch):
    """Regression: a failed remote `ip` command must not look like an empty snapshot."""
    db = _session()
    server = Server(ip="10.0.0.10", port=22, ssh_username="root")
    switch = Switch(name="sw-safe", ip="10.0.0.20", port=22, username="admin")
    server.switches = [switch]
    db.add_all([server, switch])
    db.flush()
    db.add(NetworkLink(
        server_id=server.id,
        switch_id=switch.id,
        server_interface="eth0",
        server_mac="aa:bb:cc:dd:ee:ff",
        status="found",
    ))
    db.commit()

    monkeypatch.setattr(
        discovery,
        "_scan_server",
        lambda _config: {
            "interfaces": [],
            "error": None,
            "scan_complete": False,
        },
    )
    monkeypatch.setattr(
        discovery,
        "_scan_switch",
        lambda _config: {"mac_map": {}, "error": None},
    )

    result = discovery.discover_topology_records(db)

    assert result["stats"]["errors"] == 1
    assert db.query(NetworkLink).count() == 1
    db.close()


def test_empty_server_selection_does_not_scan_every_server(monkeypatch):
    db = _session()
    server = Server(ip="10.0.0.30", port=22, ssh_username="root")
    switch = Switch(name="sw-empty", ip="10.0.0.40", port=22, username="admin")
    server.switches = [switch]
    db.add_all([server, switch])
    db.commit()

    monkeypatch.setattr(
        discovery,
        "_scan_server",
        lambda _config: (_ for _ in ()).throw(AssertionError("must not scan")),
    )

    result = discovery.discover_topology_records(db, server_ids=[])

    assert result["stats"]["total_servers"] == 0
    assert result["servers"] == []
    db.close()
