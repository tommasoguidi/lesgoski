import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Use an environment variable for flexibility, defaulting to SQLite for local dev
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./flights.db")

# SQLite specific arguments:
# check_same_thread=False is required for SQLite when using multiple threads
# (e.g. if you add a web interface later or run the scanner in a thread)
connect_args = {}
if "sqlite" in DATABASE_URL:
    connect_args["check_same_thread"] = False

engine = create_engine(
    DATABASE_URL, 
    connect_args=connect_args,
    # echo=True is useful for debugging SQL queries during development
    echo=False 
)

# SessionLocal is the factory for creating new database sessions
# autocommit=False and autoflush=False are standard safety practices
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# This class will be inherited by your models in database/models.py
Base = declarative_base()

def init_db():
    """
    Creates the tables in the database.
    Call this function when the application starts or via a setup script.
    """
    # Import models here to ensure they are registered with Base.metadata before creation
    # This prevents the 'tables not created' issue if models aren't imported
    import database.models  
    
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
