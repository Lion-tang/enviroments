from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "sqlite:///./enviroments.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def _configure_sqlite(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables."""
    from app.models.server import Server
    from app.models.switch import Switch
    from app.models.user import User
    from app.models.server_favorite import ServerFavorite
    from app.models.network_link import NetworkLink
    Base.metadata.create_all(bind=engine)
    ensure_schema()


def ensure_schema(bind=engine):
    """Apply small SQLite-compatible schema updates for existing databases."""
    with bind.begin() as conn:
        server_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(servers)"))}
        if "detail_note" not in server_columns:
            conn.execute(text("ALTER TABLE servers ADD COLUMN detail_note TEXT"))
        if "occupied_at" not in server_columns:
            conn.execute(text("ALTER TABLE servers ADD COLUMN occupied_at DATETIME"))
        if "dpu" not in server_columns:
            conn.execute(text("ALTER TABLE servers ADD COLUMN dpu TEXT"))

        link_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(network_links)"))}
        schema_version = conn.execute(text("PRAGMA user_version")).scalar_one()
        if schema_version < 1 and "raw_output" in link_columns:
            conn.execute(text(
                "UPDATE network_links SET raw_output = NULL WHERE raw_output IS NOT NULL"
            ))
        if schema_version < 1:
            conn.execute(text("PRAGMA user_version = 1"))
