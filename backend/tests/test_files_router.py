from app.api.v1.routers import files


def test_get_server_connection_closes_database_session(monkeypatch):
    server = type("ServerRow", (), {
        "ip": "10.0.0.1",
        "port": 22,
        "ssh_username": "root",
        "ssh_password": "secret",
        "ssh_key_file": None,
    })()

    class FakeQuery:
        def filter(self, *_args):
            return self

        def first(self):
            return server

    class FakeSession:
        def __init__(self):
            self.closed = False

        def query(self, *_args):
            return FakeQuery()

        def close(self):
            self.closed = True

    session = FakeSession()
    monkeypatch.setattr(files, "SessionLocal", lambda: session)

    result = files._get_server_connection(7)

    assert result == {
        "ip": "10.0.0.1",
        "port": 22,
        "username": "root",
        "password": "secret",
        "key_file": None,
    }
    assert session.closed is True
