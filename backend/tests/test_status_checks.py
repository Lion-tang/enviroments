import importlib

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


def test_bounded_status_check_persists_successes_and_isolates_failures():
    status_checks = importlib.import_module("app.core.status_checks")
    db = _session()
    db.add_all([
        Server(ip="10.0.0.1", port=22, ssh_username="root", is_online=False),
        Server(ip="10.0.0.2", port=22, ssh_username="root", is_online=True),
        Server(ip="10.0.0.3", port=22, ssh_username="root", is_online=False),
    ])
    db.commit()

    commits = 0
    real_commit = db.commit

    def count_commit():
        nonlocal commits
        commits += 1
        real_commit()

    db.commit = count_commit

    def checker(ip, port):
        if ip == "10.0.0.2":
            raise TimeoutError("probe timed out")
        return ip == "10.0.0.1"

    result = status_checks.check_server_statuses(
        db,
        checker=checker,
        log_writer=lambda *_args, **_kwargs: None,
        max_workers=2,
    )

    rows = {row.ip: row for row in db.query(Server).all()}
    assert result["total"] == 3
    assert result["online"] == 1
    assert result["results"] == [
        {"server_id": rows["10.0.0.1"].id, "ip": "10.0.0.1", "online": True, "error": None},
        {"server_id": rows["10.0.0.2"].id, "ip": "10.0.0.2", "online": None, "error": "probe timed out"},
        {"server_id": rows["10.0.0.3"].id, "ip": "10.0.0.3", "online": False, "error": None},
    ]
    assert rows["10.0.0.1"].is_online is True
    assert rows["10.0.0.2"].is_online is True
    assert rows["10.0.0.2"].online_checked_at is None
    assert rows["10.0.0.3"].is_online is False
    assert commits == 1
    db.close()
