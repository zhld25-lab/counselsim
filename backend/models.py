"""SQLAlchemy models: users, patients, sessions, messages, summaries,
feedback reports, role switches."""
import datetime as dt

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from db import Base


def _now():
    return dt.datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=_now)

    patients = relationship("Patient", back_populates="owner")


class Patient(Base):
    """A simulated client. `persona` holds the LLM-generated character card."""

    __tablename__ = "patients"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    display_name = Column(String(80), nullable=False)
    gender = Column(String(40))
    age_group = Column(String(20))
    age = Column(Integer)
    ethnicity = Column(String(80))
    concerns = Column(JSON, default=list)
    persona = Column(JSON, default=dict)
    created_at = Column(DateTime, default=_now)

    owner = relationship("User", back_populates="patients")
    sessions = relationship("CounselSession", back_populates="patient")


class CounselSession(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    session_number = Column(Integer, default=1)
    user_role = Column(String(20), default="counselor")  # counselor|client|supervisor
    status = Column(String(20), default="active")  # active|paused|ended
    started_at = Column(DateTime, default=_now)
    ended_at = Column(DateTime, nullable=True)

    patient = relationship("Patient", back_populates="sessions")
    messages = relationship(
        "Message", back_populates="session", order_by="Message.turn"
    )
    switches = relationship("RoleSwitch", back_populates="session")
    notes = relationship("SupervisorNote", back_populates="session")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    turn = Column(Integer, nullable=False)
    speaker = Column(String(20), nullable=False)  # client|counselor
    text = Column(Text, nullable=False)
    emotion = Column(String(20), default="neutral")
    action = Column(String(160), default="")
    controlled_by = Column(String(10), default="llm")  # user|llm
    timestamp = Column(DateTime, default=_now)

    session = relationship("CounselSession", back_populates="messages")


class SupervisorNote(Base):
    """Whisper tips (LLM) and interventions (user playing supervisor)."""

    __tablename__ = "supervisor_notes"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    after_turn = Column(Integer, default=0)
    note = Column(Text, nullable=False)
    focus_skill = Column(String(80), default="")
    author = Column(String(10), default="llm")  # user|llm
    visibility = Column(String(20), default="counselor")  # counselor|all
    consumed = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=_now)

    session = relationship("CounselSession", back_populates="notes")


class RoleSwitch(Base):
    __tablename__ = "role_switches"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    turn = Column(Integer, default=0)
    from_role = Column(String(20))
    to_role = Column(String(20))
    timestamp = Column(DateTime, default=_now)

    session = relationship("CounselSession", back_populates="switches")


class SessionSummary(Base):
    __tablename__ = "session_summaries"

    id = Column(Integer, primary_key=True)
    session_id = Column(
        Integer, ForeignKey("sessions.id"), nullable=False, unique=True, index=True
    )
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    session_number = Column(Integer, default=1)
    data = Column(JSON, default=dict)
    created_at = Column(DateTime, default=_now)


class FeedbackReport(Base):
    __tablename__ = "feedback_reports"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    evaluated_party = Column(String(10), default="user")  # user|llm
    data = Column(JSON, default=dict)
    user_scores = Column(JSON, nullable=True)  # mode C: the user's own ratings
    created_at = Column(DateTime, default=_now)
