import os
import stat
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=connect_args)

if settings.database_url.startswith("sqlite"):
    # WAL mode allows the Streamlit dashboard to read the DB concurrently
    # with the backend's writes, without lock contention.
    @event.listens_for(engine, "connect")
    def _enable_wal(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    @event.listens_for(engine, "connect")
    def _restrict_file_permissions(_dbapi_connection, _connection_record):
        # Owner-only read/write. This is a POSIX permission bits mechanism -
        # on Windows (this project's actual dev environment) os.chmod has no
        # equivalent effect and this is a no-op; real access control there
        # would need Windows ACLs (icacls / pywin32), not attempted here.
        # This does NOT encrypt the file at rest - see docs/NOTES_SECURITY.md
        # for why full encryption (e.g. SQLCipher) was evaluated and not
        # implemented for this MVP's threat model.
        db_path = Path(settings.database_url.replace("sqlite:///", "", 1))
        if db_path.exists():
            try:
                os.chmod(db_path, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
