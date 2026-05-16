"""
models.py
=========
SQLAlchemy ORM models for Nexus.

Tables:
  users         - registered user accounts
  chat_sessions - a conversation thread per user per tab
  chat_messages - individual messages within a session
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from database import Base


class User(Base):
    __tablename__ = "users"

    id           = Column(Integer, primary_key=True, index=True)
    username     = Column(String(50), unique=True, nullable=False, index=True)
    email        = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    avatar_path  = Column(String(256), nullable=True)   # e.g. "static/avatars/3.png"
    created_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    tab_name   = Column(String(50), nullable=False, default="FAQs")  # FAQs / Attendance / etc.
    title      = Column(String(200), nullable=True)                   # first user message (auto-set)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user     = relationship("User", back_populates="sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan",
                            order_by="ChatMessage.timestamp")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id         = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False)
    role       = Column(String(20), nullable=False)   # "user" or "assistant"
    content    = Column(Text, nullable=False)
    timestamp  = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    session = relationship("ChatSession", back_populates="messages")
