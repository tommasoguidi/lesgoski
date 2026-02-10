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
