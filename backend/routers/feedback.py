"""Feedback on the counselling session (and mode-C score comparison)."""
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as OrmSession

import session_service as svc
from db import get_db
from llm import supervisor_agent
from llm.gemini_client import LLMError
from llm.supervisor_agent import DIMENSIONS
from models import FeedbackReport, User
from security import current_user

router = APIRouter(prefix="/api/sessions", tags=["feedback"])


class MyScores(BaseModel):
    scores: Dict[str, int] = Field(default_factory=dict)
    comment: str = ""


def _attribution(transcript):
    counselor_turns = [m for m in transcript if m["speaker"] == "counselor"]
    return {
        "counselor_turns_total": len(counselor_turns),
        "counselor_turns_by_user": [
            m["turn"] for m in counselor_turns if m["controlled_by"] == "user"
        ],
        "counselor_turns_by_llm": [
            m["turn"] for m in counselor_turns if m["controlled_by"] == "llm"
        ],
    }


def _build_report(db: OrmSession, session) -> FeedbackReport:
    row = (
        db.query(FeedbackReport)
        .filter(FeedbackReport.session_id == session.id)
        .first()
    )
    if row:
        return row
    transcript = svc.transcript_dicts(session)
    if not any(m["speaker"] == "counselor" for m in transcript):
        raise HTTPException(
            status_code=400, detail="No counsellor turns to evaluate yet"
        )
    party = svc.evaluated_party(transcript)
    try:
        data = supervisor_agent.evaluate(transcript, party, session.patient.persona or {})
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    data["attribution"] = _attribution(transcript)
    data["evaluated_party_label"] = (
        "your turns as counsellor" if party == "user" else "the AI counsellor's turns"
    )
    row = FeedbackReport(session_id=session.id, evaluated_party=party, data=data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.post("/{session_id}/feedback")
def create_feedback(
    session_id: int,
    user: User = Depends(current_user),
    db: OrmSession = Depends(get_db),
):
    session = svc.load_session(db, session_id, user)
    row = _build_report(db, session)
    return {
        "report": row.data,
        "evaluated_party": row.evaluated_party,
        "user_scores": row.user_scores,
    }


@router.get("/{session_id}/feedback")
def read_feedback(
    session_id: int,
    user: User = Depends(current_user),
    db: OrmSession = Depends(get_db),
):
    session = svc.load_session(db, session_id, user)
    row = (
        db.query(FeedbackReport)
        .filter(FeedbackReport.session_id == session.id)
        .first()
    )
    if not row:
        return {"report": None}
    return {
        "report": row.data,
        "evaluated_party": row.evaluated_party,
        "user_scores": row.user_scores,
    }


@router.post("/{session_id}/my-scores")
def submit_my_scores(
    session_id: int,
    body: MyScores,
    user: User = Depends(current_user),
    db: OrmSession = Depends(get_db),
):
    """Mode C: the user grades the counsellor, then sees the LLM supervisor's grades."""
    session = svc.load_session(db, session_id, user)
    cleaned = {}
    for dim in DIMENSIONS:
        try:
            cleaned[dim] = max(1, min(10, int(body.scores.get(dim, 5))))
        except (TypeError, ValueError):
            cleaned[dim] = 5

    row = _build_report(db, session)
    row.user_scores = {"scores": cleaned, "comment": body.comment.strip()}
    db.commit()
    db.refresh(row)

    llm_scores = {d: row.data["scores"][d]["score"] for d in DIMENSIONS}
    comparison = [
        {
            "dimension": d,
            "you": cleaned[d],
            "supervisor_llm": llm_scores[d],
            "delta": cleaned[d] - llm_scores[d],
        }
        for d in DIMENSIONS
    ]
    mean_abs = sum(abs(c["delta"]) for c in comparison) / len(comparison)
    return {
        "report": row.data,
        "evaluated_party": row.evaluated_party,
        "user_scores": row.user_scores,
        "comparison": comparison,
        "mean_absolute_difference": round(mean_abs, 2),
    }
