import json

from app.core import audit_log


def test_read_json_lines_returns_newest_tail_with_exact_total(tmp_path):
    path = tmp_path / "server.log"
    path.write_text(
        "".join(json.dumps({"seq": seq}) + "\n" for seq in range(1, 6)),
        encoding="utf-8",
    )

    result = audit_log.read_json_lines(str(path), limit=2)

    assert result["total"] == 5
    assert result["logs"] == [{"seq": 5}, {"seq": 4}]


def test_read_json_lines_preserves_malformed_tail_lines(tmp_path):
    path = tmp_path / "server.log"
    path.write_text('{"seq": 1}\nnot-json\n', encoding="utf-8")

    result = audit_log.read_json_lines(str(path), limit=2)

    assert result == {
        "total": 2,
        "logs": [{"raw": "not-json"}, {"seq": 1}],
    }


def test_append_json_log_rotates_before_file_grows_without_bound(tmp_path):
    path = tmp_path / "server.log"
    payload = {"message": "x" * 80}

    for _ in range(4):
        audit_log.append_json_log(
            str(path),
            payload,
            max_bytes=120,
            backup_count=2,
        )

    assert path.exists()
    assert (tmp_path / "server.log.1").exists()
    assert (tmp_path / "server.log.2").exists()
    assert not (tmp_path / "server.log.3").exists()
    assert path.stat().st_size <= 120


def test_clear_log_removes_active_file_and_rotated_backups(tmp_path):
    path = tmp_path / "server.log"
    path.write_text("active\n", encoding="utf-8")
    (tmp_path / "server.log.1").write_text("old\n", encoding="utf-8")
    (tmp_path / "server.log.2").write_text("older\n", encoding="utf-8")

    audit_log.clear_log(str(path), backup_count=2)

    assert not path.exists()
    assert not (tmp_path / "server.log.1").exists()
    assert not (tmp_path / "server.log.2").exists()
