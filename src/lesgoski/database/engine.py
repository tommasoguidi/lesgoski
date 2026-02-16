# database/engine.py
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

from lesgoski.config import DATABASE_URL

# SQLite specific arguments:
# check_same_thread=False is required for SQLite when using multiple threads
connect_args = {}
if "sqlite" in DATABASE_URL:
    connect_args["check_same_thread"] = False

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=False
)

# Enable WAL journal mode for better concurrent read/write performance.
# Critical when the web server and scheduler both access the same SQLite file.
if "sqlite" in DATABASE_URL:
    @event.listens_for(engine, "connect")
    def _set_sqlite_wal(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

# SessionLocal is the factory for creating new database sessions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# This class will be inherited by your models in database/models.py
Base = declarative_base()

def init_db():
    """
    Creates the tables in the database.
    Call this function when the application starts or via a setup script.
    """
    # Import models here to ensure they are registered with Base.metadata before creation
    import lesgoski.database.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _run_migrations()


def _run_migrations():
    """Run any pending column additions for existing tables."""
    from sqlalchemy import inspect, text
    inspector = inspect(engine)

    # Migration 1: Add user_id to search_profiles
    if 'search_profiles' in inspector.get_table_names():
        columns = [c['name'] for c in inspector.get_columns('search_profiles')]
        if 'user_id' not in columns:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE search_profiles ADD COLUMN user_id INTEGER REFERENCES users(id)"
                ))

    # Migration 2: Add favourite_profile_id to users
    if 'users' in inspector.get_table_names():
        columns = [c['name'] for c in inspector.get_columns('users')]
        if 'favourite_profile_id' not in columns:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE users ADD COLUMN favourite_profile_id INTEGER REFERENCES search_profiles(id)"
                ))

def get_db():
    """
    Generator function to provide a database session.
    Useful for dependency injection or usage in 'with' contexts.
    Ensures the connection is always closed after use.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
