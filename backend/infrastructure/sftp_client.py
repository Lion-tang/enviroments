"""
Infrastructure Layer - SFTP File Operations
Pure functions, no FastAPI dependency
"""

import os
import io
import paramiko
import secrets
from contextlib import contextmanager
from dataclasses import dataclass
from typing import BinaryIO, Iterator, Optional


@dataclass
class FileEntry:
    name: str
    path: str
    type: str        # "file" or "directory"
    size: Optional[int] = None   # bytes
    modified: Optional[str] = None


@contextmanager
def sftp_connection(
    ip: str,
    port: int,
    username: str,
    password: Optional[str],
    key_file: Optional[str],
):
    """Own an SSH client and its SFTP channel as one deterministic resource."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    sftp = None
    try:
        ssh.connect(
            ip,
            port=port,
            username=username,
            password=password,
            key_filename=key_file,
            timeout=10,
            banner_timeout=10,
            auth_timeout=10,
            look_for_keys=False,
            allow_agent=False,
        )
        sftp = ssh.open_sftp()
        yield sftp
    finally:
        if sftp is not None:
            sftp.close()
        ssh.close()


def list_directory(
    ip: str,
    port: int,
    username: str,
    password: Optional[str],
    key_file: Optional[str],
    remote_path: str = ".",
) -> list[FileEntry]:
    """
    List directory contents via SFTP.
    Returns list of FileEntry sorted: directories first, then files, alphabetically.
    Normalizes all paths to forward slashes.
    """
    entries = []
    with sftp_connection(ip, port, username, password, key_file) as client:
        # Normalize remote_path to forward slashes
        normalized = remote_path.replace("\\", "/")
        # Keep "/" as root; strip trailing "/" for other paths
        if normalized == "/":
            remote_path = "/"
        elif normalized == "." or normalized == "":
            remote_path = "."
        else:
            remote_path = normalized.rstrip("/")

        # List the target directory
        target = remote_path if remote_path != "." else "."
        names = client.listdir(target)

        for name in names:
            # Build full path: root "/" + name, or current dir + name
            if remote_path == "/":
                full_path = "/" + name
            elif remote_path == ".":
                full_path = name
            elif remote_path.endswith("/"):
                full_path = remote_path + name
            else:
                full_path = remote_path + "/" + name

            try:
                stat_result = client.stat(full_path)
                is_dir = False
                try:
                    is_dir = stat_result.isdir()
                except Exception:
                    # Fallback: try to listdir the path
                    try:
                        client.listdir(full_path)
                        is_dir = True
                    except Exception:
                        is_dir = False

                entry_type = "directory" if is_dir else "file"
                size = None
                if entry_type == "file":
                    try:
                        size = stat_result.st_size
                    except Exception:
                        pass

                entries.append(FileEntry(
                    name=name,
                    path=full_path,
                    type=entry_type,
                    size=size,
                    modified=str(stat_result.st_mtime) if hasattr(stat_result, 'st_mtime') else None,
                ))
            except Exception as e:
                # Show as file with unknown type
                entries.append(FileEntry(
                    name=name,
                    path=full_path,
                    type="file",
                    size=None,
                    modified=None,
                ))
    # Sort: directories first, then files, alphabetical
    entries.sort(key=lambda e: (0 if e.type == "directory" else 1, e.name.lower()))
    return entries


def download_file(
    ip: str,
    port: int,
    username: str,
    password: Optional[str],
    key_file: Optional[str],
    remote_path: str,
) -> bytes:
    """Compatibility helper for callers that still require complete bytes."""
    return b"".join(stream_file(
        ip, port, username, password, key_file, remote_path
    ))


def stream_file(
    ip: str,
    port: int,
    username: str,
    password: Optional[str],
    key_file: Optional[str],
    remote_path: str,
    chunk_size: int = 64 * 1024,
) -> Iterator[bytes]:
    """Yield a remote file in bounded chunks and close resources on termination."""
    with sftp_connection(ip, port, username, password, key_file) as client:
        with client.open(remote_path, "rb") as remote_file:
            while True:
                chunk = remote_file.read(chunk_size)
                if not chunk:
                    break
                yield chunk


def upload_file(
    ip: str,
    port: int,
    username: str,
    password: Optional[str],
    key_file: Optional[str],
    remote_path: str,
    content: bytes,
) -> dict:
    """Compatibility wrapper around the streaming uploader."""
    return upload_stream(
        ip,
        port,
        username,
        password,
        key_file,
        remote_path,
        io.BytesIO(content),
    )


def upload_stream(
    ip: str,
    port: int,
    username: str,
    password: Optional[str],
    key_file: Optional[str],
    remote_path: str,
    source: BinaryIO,
    chunk_size: int = 64 * 1024,
    max_bytes: Optional[int] = None,
) -> dict:
    """Copy a binary stream to SFTP without materializing the complete file."""
    with sftp_connection(ip, port, username, password, key_file) as client:
        parent = os.path.dirname(remote_path).replace("\\", "/")
        if parent and parent != ".":
            _mkdir_recursive(client, parent)

        temp_path = f"{remote_path}.upload-{secrets.token_hex(8)}.tmp"
        total = 0
        try:
            with client.open(temp_path, "wb") as remote_file:
                while True:
                    chunk = source.read(chunk_size)
                    if not chunk:
                        break
                    total += len(chunk)
                    if max_bytes is not None and total > max_bytes:
                        raise ValueError(f"file exceeds {max_bytes} byte limit")
                    remote_file.write(chunk)
            stat = client.stat(temp_path)
            _replace_remote_file(client, temp_path, remote_path)
        except Exception:
            try:
                client.remove(temp_path)
            except Exception:
                pass
            raise

        return {"path": remote_path, "size": stat.st_size, "success": True}


def _replace_remote_file(client, temp_path: str, destination: str) -> None:
    """Replace destination while preserving it if a non-atomic fallback fails."""
    posix_rename = getattr(client, "posix_rename", None)
    if posix_rename is not None:
        try:
            posix_rename(temp_path, destination)
            return
        except (OSError, IOError):
            pass

    destination_exists = True
    try:
        client.stat(destination)
    except (OSError, IOError):
        destination_exists = False

    if destination_exists:
        raise RuntimeError(
            "SFTP server does not support atomic replacement; existing file was preserved"
        )

    client.rename(temp_path, destination)


def create_directory(
    ip: str,
    port: int,
    username: str,
    password: Optional[str],
    key_file: Optional[str],
    remote_path: str,
) -> dict:
    """Create a directory recursively via SFTP."""
    with sftp_connection(ip, port, username, password, key_file) as client:
        normalized = (remote_path or "").replace("\\", "/").rstrip("/")
        if not normalized or normalized == ".":
            raise ValueError("Directory path is required")
        _mkdir_recursive(client, normalized)
        return {"path": normalized, "success": True}


def _mkdir_recursive(sftp, path: str):
    """Create directory and all parents via SFTP if they don't exist."""
    dirs = []
    while path and path != "." and path != "/":
        try:
            sftp.stat(path)
            break
        except Exception:
            dirs.insert(0, os.path.basename(path))
            path = os.path.dirname(path).replace("\\", "/")
    for d in dirs:
        path = (path + "/" + d).replace("//", "/")
        try:
            sftp.mkdir(path)
        except Exception:
            pass   # Already exists


def get_home_directory(
    ip: str,
    port: int,
    username: str,
    password: Optional[str],
    key_file: Optional[str],
) -> str:
    """Get the user's home directory via SFTP."""
    try:
        with sftp_connection(ip, port, username, password, key_file) as client:
            return client.normalize(".")
    except Exception:
        pass

    # Fallback: run remote command
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(
            ip,
            port=port,
            username=username,
            password=password,
            key_filename=key_file,
            timeout=10,
            banner_timeout=10,
            auth_timeout=10,
            look_for_keys=False,
            allow_agent=False,
        )
        _stdin, stdout, _stderr = ssh.exec_command("echo $HOME", timeout=10)
        return stdout.read().decode().strip()
    finally:
        ssh.close()
