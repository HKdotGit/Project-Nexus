"""
database.py
===========
SQLAlchemy engine, session factory, and Base for Nexus.
Creates nexus.db in the same directory on first run.
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from pathlib import Path

DB_PATH = Path(__file__).parent / "nexus.db"
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}  # Needed for SQLite
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session and closes it after."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

from sqlalchemy import Column, Integer, String, JSON

class Timetable(Base):
    __tablename__ = "timetables"
    id = Column(Integer, primary_key=True, index=True)
    sheet_name = Column(String)
    row_data = Column(JSON)

class FacultySeating(Base):
    __tablename__ = "faculty_seating"
    id = Column(Integer, primary_key=True, index=True)
    category = Column(String)
    row_data = Column(JSON)

# Initialize database schema
Base.metadata.create_all(bind=engine)

