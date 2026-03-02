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
    seed_admin()


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

    # Migration 3: Add is_admin to users
    if 'users' in inspector.get_table_names():
        columns = [c['name'] for c in inspector.get_columns('users')]
        if 'is_admin' not in columns:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0"
                ))

    # Migration 4: Create invite_tokens table
    if 'invite_tokens' not in inspector.get_table_names():
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE invite_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token VARCHAR NOT NULL UNIQUE,
                    created_by INTEGER NOT NULL REFERENCES users(id),
                    used_by INTEGER REFERENCES users(id),
                    revoked INTEGER NOT NULL DEFAULT 0,
                    created_at DATETIME DEFAULT (datetime('now')),
                    used_at DATETIME
                )
            """))
            conn.execute(text(
                "CREATE UNIQUE INDEX ix_invite_tokens_token ON invite_tokens (token)"
            ))

def seed_admin():
    """
    Seeds the admin user from ADMIN_USERNAME / ADMIN_PASSWORD env vars.
    - Creates the user if it doesn't exist.
    - Promotes to admin if it exists but isn't one.
    - Always updates password from env (allows credential rotation via .env).
    - Assigns all orphaned SearchProfiles (user_id IS NULL) to the admin.
    All imports are local to avoid circular import with auth.py.
    """
    import logging
    from lesgoski.config import ADMIN_USERNAME, ADMIN_PASSWORD
    from lesgoski.database.models import User, SearchProfile
    from lesgoski.webapp.auth import hash_password, generate_ntfy_topic

    logger = logging.getLogger(__name__)
    if not ADMIN_USERNAME or not ADMIN_PASSWORD:
        return

    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == ADMIN_USERNAME).first()
        if admin is None:
            admin = User(
                username=ADMIN_USERNAME,
                hashed_password=hash_password(ADMIN_PASSWORD),
                is_admin=True,
                ntfy_topic=generate_ntfy_topic(),
            )
            db.add(admin)
            db.flush()
            logger.info(f"Admin user '{ADMIN_USERNAME}' created.")
        else:
            admin.hashed_password = hash_password(ADMIN_PASSWORD)
            if not admin.is_admin:
                admin.is_admin = True
                logger.info(f"User '{ADMIN_USERNAME}' promoted to admin.")
            if not admin.ntfy_topic:
                admin.ntfy_topic = generate_ntfy_topic()
                logger.info(f"Assigned ntfy_topic to admin '{ADMIN_USERNAME}'.")

        orphaned = db.query(SearchProfile).filter(SearchProfile.user_id is None).all()
        if orphaned:
            for p in orphaned:
                p.user_id = admin.id
            logger.info(f"Assigned {len(orphaned)} orphaned profile(s) to admin '{ADMIN_USERNAME}'.")

        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Admin seeding failed: {e}", exc_info=True)
    finally:
        db.close()


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
