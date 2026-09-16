from sqlalchemy import create_engine, text

from app.core import database


def test_ensure_schema_upgrades_old_database_idempotently(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE servers (id INTEGER PRIMARY KEY)"))
        connection.execute(text(
            "CREATE TABLE network_links (id INTEGER PRIMARY KEY, raw_output TEXT)"
        ))
        connection.execute(text(
            "INSERT INTO network_links (raw_output) VALUES ('large legacy table')"
        ))

    database.ensure_schema(engine)
    database.ensure_schema(engine)

    with engine.connect() as connection:
        columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(servers)"))
        }
        raw_output = connection.execute(text(
            "SELECT raw_output FROM network_links"
        )).scalar_one()
        schema_version = connection.execute(text("PRAGMA user_version")).scalar_one()

    assert {"detail_note", "occupied_at", "dpu"}.issubset(columns)
    assert raw_output is None
    assert schema_version == 1
