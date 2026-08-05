"""
Core Postgres models: documents, users, roles, audit log.
This is the metadata/RBAC layer described in the architecture doc (Section 6.3).
Chunk *text and vectors* live in Qdrant; this table just tracks
chunk IDs against their parent document for permission filtering.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, Float, ForeignKey, Text, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Role(Base):
    __tablename__ = "roles"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name = Column(String, unique=True, nullable=False)  # e.g. "engineering", "hr", "admin"
    clearance_level = Column(Integer, default=1)  # 1=general, higher=more sensitive access

    users = relationship("User", back_populates="role")


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    email = Column(String, unique=True, nullable=False)
    department = Column(String, nullable=True)
    role_id = Column(UUID(as_uuid=False), ForeignKey("roles.id"), nullable=False)

    role = relationship("Role", back_populates="users")


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    title = Column(String, nullable=False)
    source_system = Column(String, nullable=False)  # "github" | "pdf"
    source_ref = Column(String, nullable=True)       # repo path / original filename
    status = Column(String, default="current")        # current | superseded | draft
    sensitivity = Column(String, default="internal")  # internal | confidential | public
    confidence = Column(Float, default=1.0)           # trust score, 0-1
    owner_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_reviewed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    supersedes_id = Column(UUID(as_uuid=False), ForeignKey("documents.id"), nullable=True)


class Chunk(Base):
    """
    Pointer row: one per chunk stored in Qdrant. Lets Postgres answer
    permission/freshness questions fast without touching the vector store.
    """
    __tablename__ = "chunks"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)  # matches Qdrant point id
    document_id = Column(UUID(as_uuid=False), ForeignKey("documents.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    text_preview = Column(Text, nullable=True)  # first ~200 chars, for debugging/audit only


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    query = Column(Text, nullable=False)
    strategy_used = Column(String, nullable=True)      # final successful strategy, or None
    strategy_attempts = Column(JSON, nullable=True)      # [{"strategy": ..., "outcome": ...}, ...]
    planner_outcome = Column(String, nullable=True)      # success | no_evidence | access_denied | failed
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    result_summary = Column(Text, nullable=True)
