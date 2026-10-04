"""Live session: turns, role switching, supervisor whispers, ending a session."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as OrmSession

import config
import session_service as svc
from db import get_db
from llm import client_agent, counselor_agent, supervisor_agent
from llm.gemini_client import LLMError
from models import CounselSession, Patient, RoleSwitch, SessionSummary, SupervisorNote, User
from security import current_user

log = logging.getLogger("counselsim.sessions")
router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class StartSession(BaseModel):
    patient_id: int
    user_role: str = "counselor"


class SayBody(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    emotion: str = "neutral"
    action: str = ""


class RoleBody(BaseModel):
    role: str


class NoteBody(BaseModel):
    note: str = Field(min_length=1, max_length=1000)


def _crisis_response(db: OrmSession, session: CounselSession):
    session.status = "paused"
    db.commit()
    return {
        "crisis": True,
        "state": svc.session_state(db, session),
        **config.CRISIS_RESOURCES,
    }


def _maybe_auto_whisper(db: OrmSession, session: CounselSession):
    """Every N turns the supervisor LLM slips the counsellor a note.

    Skipped when the *user* is the supervisor - in mode C the notes are theirs.
    """
    if session.user_role == "supervisor":
        return None
    transcript = svc.transcript_dicts(session)
    if not transcript or len(transcript) % config.SUPERVISOR_TIP_EVERY_N_TURNS != 0:
        return None
    if svc.next_speaker(transcript) != "counselor":
        return None
    try:
        tip = supervisor_agent.whisper(transcript, session.patient.persona or {})
    except LLMError as exc:
        log.warning("supervisor whisper failed: %s", exc)
        return None
    note = SupervisorNote(
        session_id=session.id,
        after_turn=transcript[-1]["turn"],
        note=tip["tip"],
        focus_skill=tip["focus_skill"],
        author="llm",
        visibility="counselor",
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return svc.note_dict(note)


@router.post("")
def start_session(
    body: StartSession,
    user: User = Depends(current_user),
    db: OrmSession = Depends(get_db),
):
    if body.user_role not in svc.ROLES:
        raise HTTPException(status_code=400, detail="Unknown role")
    patient = db.get(Patient, body.patient_id)
    if not patient or patient.user_id != user.id:
        raise HTTPException(status_code=404, detail="Patient not found")

    previous = (
        db.query(CounselSession)
        .filter(CounselSession.patient_id == patient.id)
        .count()
    )
    session = CounselSession(
        user_id=user.id,
        patient_id=patient.id,
        session_number=previous + 1,
        user_role=body.user_role,
        status="active",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    db.add(
        RoleSwitch(session_id=session.id, turn=0, from_role=None, to_role=body.user_role)
    )
    db.commit()
    db.refresh(session)
    return svc.session_state(db, session)


@router.get("/{session_id}")
def get_session(
    session_id: int,
    user: User = Depends(current_user),
    db: OrmSession = Depends(get_db),
):
    session = svc.load_session(db, session_id, user)
    return svc.session_state(db, session)


@router.post("/{session_id}/say")
def say(
    session_id: int,
    body: SayBody,
    user: User = Depends(current_user),
    db: OrmSession = Depends(get_db),
):
    """The user speaks, as whichever speaking role they currently hold."""
    session = svc.load_session(db, session_id, user)
    if session.status == "ended":
        raise HTTPException(status_code=400, detail="This session has ended")
    if session.user_role == "supervisor":
        raise HTTPException(
            status_code=400,
            detail="You are the supervisor - use Intervene instead of speaking",
        )
    transcript = svc.transcript_dicts(session)
    if svc.next_speaker(transcript) != session.user_role:
        raise HTTPException(status_code=409, detail="It is not your turn")

    if svc.crisis_check(body.text):
        return _crisis_response(db, session)

    msg = svc.add_message(
        db, session, session.user_role, body.text.strip(),
        body.emotion, body.action, "user",
    )
    session.status = "active"
    db.commit()
    note = _maybe_auto_whisper(db, session)
    return {
        "message": svc.transcript_dicts(session)[msg.turn - 1],
        "new_note": note,
        "state": svc.session_state(db, session),
    }


@router.post("/{session_id}/step")
def step(
    session_id: int,
    user: User = Depends(current_user),
    db: OrmSession = Depends(get_db),
):
    """Let the LLM take the next turn.

    Also the recovery path when a role switch leaves nobody holding the chair:
    whoever the user is *not* controlling is always played by an LLM.
    """
    session = svc.load_session(db, session_id, user)
    if session.status == "ended":
        raise HTTPException(status_code=400, detail="This session has ended")
    transcript = svc.transcript_dicts(session)
    speaker = svc.next_speaker(transcript)
    if speaker == session.user_role:
        raise HTTPException(status_code=409, detail="It is the user's turn to speak")

    patient: Patient = session.patient
    persona = patient.persona or {}
    prior = svc.prior_summary_text(db, patient.id, session.session_number)

    used_note = None
    try:
        if speaker == "client":
            out = client_agent.speak(patient, persona, transcript, prior)
        else:
            note = svc.pending_note(db, session)
            guidance = ""
            if note:
                guidance = note.note
                used_note = note
            out = counselor_agent.speak(
                persona,
                transcript,
                prior_summary=prior,
                supervisor_note=guidance,
                took_over=svc.counselor_took_over(transcript),
            )
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    msg = svc.add_message(
        db, session, speaker, out["speech"], out["emotion"], out["action"], "llm"
    )
    if used_note is not None:
        used_note.consumed = True
        db.commit()
    note = _maybe_auto_whisper(db, session)
    return {
        "message": svc.transcript_dicts(session)[msg.turn - 1],
        "followed_note_id": used_note.id if used_note else None,
        "new_note": note,
        "state": svc.session_state(db, session),
    }


@router.post("/{session_id}/role")
def switch_role(
    session_id: int,
    body: RoleBody,
    user: User = Depends(current_user),
    db: OrmSession = Depends(get_db),
):
    """Take over a different chair. Switching happens between turns."""
    if body.role not in svc.ROLES:
        raise HTTPException(status_code=400, detail="Unknown role")
    session = svc.load_session(db, session_id, user)
    if session.status == "ended":
        raise HTTPException(status_code=400, detail="This session has ended")
    if body.role == session.user_role:
        return svc.session_state(db, session)

    transcript = svc.transcript_dicts(session)
    db.add(
        RoleSwitch(
            session_id=session.id,
            turn=transcript[-1]["turn"] if transcript else 0,
            from_role=session.user_role,
            to_role=body.role,
        )
    )
    session.user_role = body.role
    db.commit()
    db.refresh(session)
    return svc.session_state(db, session)


@router.post("/{session_id}/supervisor-tip")
def ask_supervisor(
    session_id: int,
    user: User = Depends(current_user),
    db: OrmSession = Depends(get_db),
):
    session = svc.load_session(db, session_id, user)
    if session.user_role == "client":
        raise HTTPException(
            status_code=403, detail="The client cannot see supervisor notes"
        )
    transcript = svc.transcript_dicts(session)
    try:
        tip = supervisor_agent.whisper(transcript, session.patient.persona or {})
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    note = SupervisorNote(
        session_id=session.id,
        after_turn=transcript[-1]["turn"] if transcript else 0,
        note=tip["tip"],
        focus_skill=tip["focus_skill"],
        author="llm",
        visibility="counselor",
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return {"note": svc.note_dict(note), "state": svc.session_state(db, session)}


@router.post("/{session_id}/intervene")
def intervene(
    session_id: int,
    body: NoteBody,
    user: User = Depends(current_user),
    db: OrmSession = Depends(get_db),
):
    """Mode C: the user (supervisor) writes guidance the counsellor must follow."""
    session = svc.load_session(db, session_id, user)
    if session.user_role != "supervisor":
        raise HTTPException(status_code=403, detail="You are not the supervisor")
    if svc.crisis_check(body.note):
        return _crisis_response(db, session)
    transcript = svc.transcript_dicts(session)
    note = SupervisorNote(
        session_id=session.id,
        after_turn=transcript[-1]["turn"] if transcript else 0,
        note=body.note.strip(),
        focus_skill="supervisor intervention",
        author="user",
        visibility="counselor",
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return {"note": svc.note_dict(note), "state": svc.session_state(db, session)}


@router.post("/{session_id}/status")
def set_status(
    session_id: int,
    status: str,
    user: User = Depends(current_user),
    db: OrmSession = Depends(get_db),
):
    if status not in ("active", "paused"):
        raise HTTPException(status_code=400, detail="Use active or paused")
    session = svc.load_session(db, session_id, user)
    if session.status == "ended":
        raise HTTPException(status_code=400, detail="This session has ended")
    session.status = status
    db.commit()
    return svc.session_state(db, session)


@router.post("/{session_id}/end")
def end_session(
    session_id: int,
    user: User = Depends(current_user),
    db: OrmSession = Depends(get_db),
):
    """Close the session and persist the structured summary."""
    import datetime as dt

    session = svc.load_session(db, session_id, user)
    transcript = svc.transcript_dicts(session)
    if not transcript:
        raise HTTPException(status_code=400, detail="Nothing to summarise yet")

    existing = (
        db.query(SessionSummary)
        .filter(SessionSummary.session_id == session.id)
        .first()
    )
    if existing:
        return {"summary": existing.data, "state": svc.session_state(db, session)}

    try:
        data = supervisor_agent.summarise(
            session.session_number, transcript, session.patient.persona or {}
        )
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    row = SessionSummary(
        session_id=session.id,
        patient_id=session.patient_id,
        session_number=session.session_number,
        data=data,
    )
    db.add(row)
    session.status = "ended"
    session.ended_at = dt.datetime.utcnow()
    db.commit()
    db.refresh(session)
    return {"summary": data, "state": svc.session_state(db, session)}


@router.get("/{session_id}/summary")
def get_summary(
    session_id: int,
    user: User = Depends(current_user),
    db: OrmSession = Depends(get_db),
):
    session = svc.load_session(db, session_id, user)
    row = (
        db.query(SessionSummary)
        .filter(SessionSummary.session_id == session.id)
        .first()
    )
    return {"summary": row.data if row else None}
