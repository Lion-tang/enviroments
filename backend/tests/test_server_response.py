import json
from datetime import datetime

from app.api.v1.routers.servers import _to_response
from app.models.server import Server
from app.models.switch import Switch  # noqa: F401 - registers the association table


def test_compact_server_response_keeps_summary_without_large_cached_payload():
    server = Server(
        id=1,
        ip="10.0.0.1",
        port=22,
        os_type="linux",
        ssh_username="root",
        tags="",
        is_online=True,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )
    server.cached_info = json.dumps({
        "os_version": "Test Linux",
        "cpu_model": "Test CPU",
        "hostname": "node-1",
        "mem": 16384,
        "interfaces": [{"name": "eth0"}] * 100,
    })

    response = _to_response(server, compact=True)

    assert response.cached_info is None
    assert response.cached_interfaces is None
    assert response.cached_os_version == "Test Linux"
    assert response.cached_cpu_model == "Test CPU"
    assert response.cached_hostname == "node-1"
    assert response.cached_mem == 16384
