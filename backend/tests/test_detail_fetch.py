import importlib
import json
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.server import Server
from app.models.switch import Switch  # noqa: F401 - registers the association table


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_detail_fetch_batches_successes_and_isolates_ssh_errors():
    detail_fetch = importlib.import_module("app.core.detail_fetch")
    db = _session()
    db.add_all([
        Server(ip="10.0.0.1", port=22, ssh_username="root", is_online=True),
        Server(ip="10.0.0.2", port=22, ssh_username="root", is_online=True),
    ])
    db.commit()

    commits = 0
    real_commit = db.commit

    def count_commit():
        nonlocal commits
        commits += 1
        real_commit()

    db.commit = count_commit

    def fetcher(ip, **_kwargs):
        if ip == "10.0.0.2":
            return SimpleNamespace(error="auth failed")
        return SimpleNamespace(
            error=None,
            hostname="node-1",
            os_type="linux",
            os_version="Test Linux",
            cpu_model="Test CPU",
            cpu_count=8,
            memory_total=16384,
            interfaces=[],
        )

    result = detail_fetch.fetch_server_details(
        db,
        fetcher=fetcher,
        log_writer=lambda *_args, **_kwargs: None,
        max_workers=2,
    )

    rows = {row.ip: row for row in db.query(Server).all()}
    assert result == {"fetched": 1, "errors": 1, "total": 2}
    assert json.loads(rows["10.0.0.1"].cached_info)["hostname"] == "node-1"
    assert rows["10.0.0.1"].cached_at is not None
    assert rows["10.0.0.2"].cached_info is None
    assert commits == 1
    db.close()
