import io

import pytest

from infrastructure import sftp_client


class FakeRemoteFile:
    def __init__(self):
        self.writes = []

    def write(self, data):
        self.writes.append(data)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class FakeSFTP:
    def __init__(self):
        self.closed = False
        self.remote_file = FakeRemoteFile()

    def close(self):
        self.closed = True

    def open(self, _path, _mode):
        return self.remote_file

    def stat(self, _path):
        return type("Stat", (), {"st_size": sum(map(len, self.remote_file.writes))})()

    def rename(self, _source, _destination):
        pass

    def posix_rename(self, _source, _destination):
        pass


class FakeSSHClient:
    def __init__(self):
        self.closed = False
        self.sftp = FakeSFTP()
        self.connect_kwargs = None

    def set_missing_host_key_policy(self, _policy):
        pass

    def connect(self, *args, **kwargs):
        self.connect_kwargs = (args, kwargs)

    def open_sftp(self):
        return self.sftp

    def close(self):
        self.closed = True


@pytest.fixture
def fake_ssh(monkeypatch):
    client = FakeSSHClient()
    monkeypatch.setattr(sftp_client.paramiko, "SSHClient", lambda: client)
    return client


def test_sftp_connection_closes_channel_and_ssh_on_error(fake_ssh):
    with pytest.raises(RuntimeError):
        with sftp_client.sftp_connection(
            "10.0.0.1", 22, "root", "secret", "/tmp/key"
        ):
            raise RuntimeError("consumer failed")

    assert fake_ssh.sftp.closed is True
    assert fake_ssh.closed is True
    assert fake_ssh.connect_kwargs[1]["key_filename"] == "/tmp/key"
    assert fake_ssh.connect_kwargs[1]["banner_timeout"] == 10
    assert fake_ssh.connect_kwargs[1]["auth_timeout"] == 10


def test_upload_stream_reads_and_writes_fixed_size_chunks(fake_ssh):
    result = sftp_client.upload_stream(
        ip="10.0.0.1",
        port=22,
        username="root",
        password="secret",
        key_file=None,
        remote_path="file.bin",
        source=io.BytesIO(b"abcdefghij"),
        chunk_size=4,
    )

    assert fake_ssh.sftp.remote_file.writes == [b"abcd", b"efgh", b"ij"]
    assert result == {"path": "file.bin", "size": 10, "success": True}
    assert fake_ssh.sftp.closed is True
    assert fake_ssh.closed is True


def test_failed_upload_preserves_existing_destination(monkeypatch):
    class Writer:
        def __init__(self, files, path):
            self.files = files
            self.path = path
            self.files[path] = b""

        def write(self, data):
            self.files[self.path] += data

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

    class ExistingFileSFTP(FakeSFTP):
        def __init__(self):
            super().__init__()
            self.files = {"file.bin": b"old-content"}

        def open(self, path, _mode):
            return Writer(self.files, path)

        def remove(self, path):
            self.files.pop(path, None)

        def stat(self, path):
            if path not in self.files:
                raise FileNotFoundError(path)
            return type("Stat", (), {"st_size": len(self.files[path])})()

        def rename(self, source, destination):
            self.files[destination] = self.files.pop(source)

    class ExistingFileSSH(FakeSSHClient):
        def __init__(self):
            super().__init__()
            self.sftp = ExistingFileSFTP()

    class FailingSource:
        def __init__(self):
            self.calls = 0

        def read(self, _size):
            self.calls += 1
            if self.calls == 1:
                return b"new-content"
            raise OSError("local read failed")

    ssh = ExistingFileSSH()
    monkeypatch.setattr(sftp_client.paramiko, "SSHClient", lambda: ssh)

    with pytest.raises(OSError, match="local read failed"):
        sftp_client.upload_stream(
            ip="10.0.0.1",
            port=22,
            username="root",
            password="secret",
            key_file=None,
            remote_path="file.bin",
            source=FailingSource(),
            chunk_size=4,
        )

    assert ssh.sftp.files.get("file.bin") == b"old-content"
    assert set(ssh.sftp.files) == {"file.bin"}


def test_non_atomic_server_rejects_overwrite_and_keeps_destination():
    class NonAtomicSFTP:
        posix_rename = None

        def __init__(self):
            self.files = {"temp": b"new", "destination": b"old"}

        def stat(self, path):
            if path not in self.files:
                raise FileNotFoundError(path)
            return type("Stat", (), {"st_size": len(self.files[path])})()

        def rename(self, source, destination):
            self.files[destination] = self.files.pop(source)

    client = NonAtomicSFTP()

    with pytest.raises(RuntimeError, match="atomic replacement"):
        sftp_client._replace_remote_file(client, "temp", "destination")

    assert client.files == {"temp": b"new", "destination": b"old"}
