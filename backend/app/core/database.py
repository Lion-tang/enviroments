from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool

DATABASE_URL = "sqlite:///./enviroments.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

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


def ensure_schema():
    """Apply small SQLite-compatible schema updates for existing databases."""
    with engine.begin() as conn:
        server_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(servers)"))}
        if "detail_note" not in server_columns:
            conn.execute(text("ALTER TABLE servers ADD COLUMN detail_note TEXT"))
        if "occupied_at" not in server_columns:
            conn.execute(text("ALTER TABLE servers ADD COLUMN occupied_at DATETIME"))
        if "dpu" not in server_columns:
            conn.execute(text("ALTER TABLE servers ADD COLUMN dpu TEXT"))
