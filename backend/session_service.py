"""Shared session logic: turn order, transcripts, role bookkeeping, safety."""
import re
from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session as OrmSession

import config
from models import (
    CounselSession,
    Message,
    Patient,
    RoleSwitch,
    SessionSummary,
    SupervisorNote,
    User,
)
from turnlogic import (  # noqa: F401  (re-exported for the routers)
    ROLES,
    SPEAKING_ROLES,
    counselor_took_over,
    counselor_turns,
    evaluated_party,
    next_speaker,
)

_CRISIS_RE = [re.compile(p, re.I) for p in config.CRISIS_PATTERNS]


def crisis_check(text: str) -> bool:
    return any(rx.search(text or "") for rx in _CRISIS_RE)


def load_session(db: OrmSession, session_id: int, user: User) -> CounselSession:
    session = db.get(CounselSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def transcript_dicts(session: CounselSession) -> List[Dict]:
    return [
        {
            "turn": m.turn,
            "speaker": m.speaker,
            "text": m.text,
            "emotion": m.emotion,
            "action": m.action,
            "controlled_by": m.controlled_by,
            "timestamp": m.timestamp.isoformat() if m.timestamp else None,
        }
        for m in sorted(session.messages, key=lambda m: m.turn)
    ]


def next_controller(session: CounselSession, transcript: List[Dict]) -> str:
    return "user" if next_speaker(transcript) == session.user_role else "llm"


def prior_summary_text(db: OrmSession, patient_id: int, before_session_number: int) -> str:
    rows = (
        db.query(SessionSummary)
        .filter(
            SessionSummary.patient_id == patient_id,
            SessionSummary.session_number < before_session_number,
        )
        .order_by(SessionSummary.session_number.asc())
        .all()
    )
    if not rows:
        return ""
    chunks = []
    for row in rows:
        d = row.data or {}
        chunks.append(
            f"Session {d.get('session_number', row.session_number)}: "
            f"issues={d.get('presenting_issues_discussed', [])}; "
            f"disclosed={d.get('key_facts_disclosed', [])}; "
            f"mood {d.get('emotional_state_start', '?')} -> {d.get('emotional_state_end', '?')}; "
            f"alliance={d.get('therapeutic_alliance', '?')}; "
            f"agreed={d.get('goals_or_homework_agreed', [])}; "
            f"open threads={d.get('unresolved_threads', [])}; "
            f"already revealed={d.get('hidden_info_revealed', [])}"
        )
    return "\n".join(chunks)


def add_message(
    db: OrmSession,
    session: CounselSession,
    speaker: str,
    text: str,
    emotion: str,
    action: str,
    controlled_by: str,
) -> Message:
    turn = len(session.messages) + 1
    msg = Message(
        session_id=session.id,
        turn=turn,
        speaker=speaker,
        text=text,
        emotion=emotion if emotion in config.EMOTIONS else "neutral",
        action=action or "",
        controlled_by=controlled_by,
    )
    db.add(msg)
    db.commit()
    db.refresh(session)
    return msg


def pending_note(db: OrmSession, session: CounselSession) -> Optional[SupervisorNote]:
    """Newest supervisor guidance the counsellor has not acted on yet."""
    return (
        db.query(SupervisorNote)
        .filter(
            SupervisorNote.session_id == session.id,
            SupervisorNote.consumed.is_(False),
        )
        .order_by(SupervisorNote.id.desc())
        .first()
    )


def note_dict(note: SupervisorNote) -> Dict:
    return {
        "id": note.id,
        "after_turn": note.after_turn,
        "note": note.note,
        "focus_skill": note.focus_skill,
        "author": note.author,
        "visibility": note.visibility,
        "consumed": note.consumed,
        "timestamp": note.timestamp.isoformat() if note.timestamp else None,
    }


def session_state(db: OrmSession, session: CounselSession) -> Dict:
    from routers.patients import public_card, role_card  # local import: avoids cycle

    patient: Patient = session.patient
    transcript = transcript_dicts(session)
    notes = (
        db.query(SupervisorNote)
        .filter(SupervisorNote.session_id == session.id)
        .order_by(SupervisorNote.id.asc())
        .all()
    )
    # The client must never see supervisor material.
    visible_notes = [] if session.user_role == "client" else [note_dict(n) for n in notes]

    switches = (
        db.query(RoleSwitch)
        .filter(RoleSwitch.session_id == session.id)
        .order_by(RoleSwitch.id.asc())
        .all()
    )

    state = {
        "session_id": session.id,
        "patient_id": patient.id,
        "session_number": session.session_number,
        "user_role": session.user_role,
        "status": session.status,
        "patient_card": public_card(patient),
        "transcript": transcript,
        "supervisor_notes": visible_notes,
        "role_history": [
            {
                "turn": s.turn,
                "from_role": s.from_role,
                "to_role": s.to_role,
                "timestamp": s.timestamp.isoformat() if s.timestamp else None,
            }
            for s in switches
        ],
        "next_speaker": next_speaker(transcript),
        "next_controlled_by": next_controller(session, transcript),
        "prior_summary": None,
        "banner": config.SAFETY_BANNER,
        "mock_mode": config.USE_MOCK,
    }
    if session.user_role == "client":
        state["role_card"] = role_card(patient)

    prior = (
        db.query(SessionSummary)
        .filter(
            SessionSummary.patient_id == patient.id,
            SessionSummary.session_number < session.session_number,
        )
        .order_by(SessionSummary.session_number.desc())
        .first()
    )
    if prior:
        state["prior_summary"] = prior.data
    return state
