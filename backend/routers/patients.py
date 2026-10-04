"""Create and browse simulated patients."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as OrmSession

import config
from db import get_db
from llm.client_agent import generate_persona
from llm.gemini_client import LLMError
from models import CounselSession, Patient, SessionSummary, User
from security import current_user

router = APIRouter(prefix="/api/patients", tags=["patients"])


class NewPatient(BaseModel):
    gender: str
    age_group: str
    ethnicity: str
    concerns: List[str] = Field(default_factory=list)


def public_card(patient: Patient) -> dict:
    """What a counsellor is allowed to see. Hidden info stays hidden."""
    persona = patient.persona or {}
    return {
        "id": patient.id,
        "name": persona.get("name", patient.display_name),
        "age": persona.get("age", patient.age),
        "gender": patient.gender,
        "ethnicity": patient.ethnicity,
        "occupation": persona.get("occupation", ""),
        "concerns": patient.concerns or [],
        "intake_info": persona.get("intake_info", ""),
        "created_at": patient.created_at.isoformat() if patient.created_at else None,
    }


def role_card(patient: Patient) -> dict:
    """Mode B: the user plays this client, so they get the full character card."""
    persona = patient.persona or {}
    card = public_card(patient)
    card.update(
        {
            "background": persona.get("background", ""),
            "style": persona.get("style", ""),
            "secrets": persona.get("secrets", []),
            "cultural_notes": persona.get("cultural_notes", ""),
            "opening_line": persona.get("opening_line", ""),
        }
    )
    return card


def latest_summary(db: OrmSession, patient_id: int):
    return (
        db.query(SessionSummary)
        .filter(SessionSummary.patient_id == patient_id)
        .order_by(SessionSummary.session_number.desc())
        .first()
    )


@router.get("/options")
def options():
    return {
        "genders": config.GENDER_OPTIONS,
        "age_groups": config.AGE_GROUP_OPTIONS,
        "ethnicities": config.ETHNICITY_OPTIONS,
        "concerns": config.CONCERN_OPTIONS,
    }


@router.post("")
def create_patient(
    body: NewPatient,
    user: User = Depends(current_user),
    db: OrmSession = Depends(get_db),
):
    if not body.concerns:
        raise HTTPException(status_code=400, detail="Pick at least one concern")
    try:
        persona = generate_persona(
            body.gender, body.age_group, body.ethnicity, body.concerns
        )
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    patient = Patient(
        user_id=user.id,
        display_name=persona.get("name", "Client"),
        gender=body.gender,
        age_group=body.age_group,
        age=persona.get("age"),
        ethnicity=body.ethnicity,
        concerns=body.concerns,
        persona=persona,
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return public_card(patient)


@router.get("")
def list_patients(
    user: User = Depends(current_user), db: OrmSession = Depends(get_db)
):
    patients = (
        db.query(Patient)
        .filter(Patient.user_id == user.id)
        .order_by(Patient.created_at.desc())
        .all()
    )
    out = []
    for p in patients:
        sessions = db.query(CounselSession).filter(CounselSession.patient_id == p.id).count()
        summary = latest_summary(db, p.id)
        card = public_card(p)
        card["session_count"] = sessions
        card["has_summary"] = summary is not None
        out.append(card)
    return out


@router.get("/{patient_id}")
def get_patient(
    patient_id: int,
    user: User = Depends(current_user),
    db: OrmSession = Depends(get_db),
):
    patient = db.get(Patient, patient_id)
    if not patient or patient.user_id != user.id:
        raise HTTPException(status_code=404, detail="Patient not found")
    summary = latest_summary(db, patient.id)
    sessions = (
        db.query(CounselSession)
        .filter(CounselSession.patient_id == patient.id)
        .order_by(CounselSession.session_number.desc())
        .all()
    )
    return {
        "patient": public_card(patient),
        "last_summary": summary.data if summary else None,
        "last_session_number": summary.session_number if summary else 0,
        "sessions": [
            {
                "id": s.id,
                "session_number": s.session_number,
                "user_role": s.user_role,
                "status": s.status,
                "started_at": s.started_at.isoformat() if s.started_at else None,
            }
            for s in sessions
        ],
    }
