"""The SUPERVISOR LLM: live whisper tips, post-session summary, feedback report."""
from typing import Dict, List

import config
from llm import mock
from llm.common import transcript_as_text
from llm.gemini_client import call_json
from llm.prompts import (
    FEEDBACK_SCHEMA,
    SUMMARY_SCHEMA,
    SUMMARY_SYSTEM,
    SUPERVISOR_FEEDBACK_SYSTEM,
    SUPERVISOR_WHISPER_SYSTEM,
)

DIMENSIONS = [
    "cultural_sensitivity",
    "therapeutic_progress",
    "professional_boundaries",
    "empathy",
    "conversational_flow",
]


def whisper(transcript: List[Dict], persona: Dict) -> Dict:
    prompt = (
        f"CLIENT CARD: {persona.get('intake_info', '')}\n\n"
        f"TRANSCRIPT SO FAR:\n{transcript_as_text(transcript, include_control=False)}"
    )
    data = call_json(
        config.SUPERVISOR_MODEL,
        SUPERVISOR_WHISPER_SYSTEM,
        [{"role": "user", "text": prompt}],
        mock=lambda: mock.whisper(transcript),
        fallback=lambda raw: {"tip": (raw or "Slow down and reflect.")[:300],
                              "focus_skill": "general"},
    )
    return {
        "tip": str(data.get("tip", "")).strip() or "Reflect the feeling before your next question.",
        "focus_skill": str(data.get("focus_skill", "")).strip() or "general",
    }


def summarise(session_number: int, transcript: List[Dict], persona: Dict) -> Dict:
    secrets = persona.get("secrets", [])
    system = SUMMARY_SYSTEM.format(
        session_number=session_number,
        secrets="; ".join(secrets) or "(none)",
        summary_schema=SUMMARY_SCHEMA,
    )
    data = call_json(
        config.SUPERVISOR_MODEL,
        system,
        [{"role": "user", "text": "TRANSCRIPT:\n" + transcript_as_text(transcript)}],
        mock=lambda: mock.summary(session_number, transcript, secrets),
        fallback=lambda raw: mock.summary(session_number, transcript, secrets),
    )
    data.setdefault("session_number", session_number)
    for key in (
        "presenting_issues_discussed", "key_facts_disclosed", "risk_indicators",
        "coping_strategies_mentioned", "goals_or_homework_agreed",
        "unresolved_threads", "hidden_info_revealed",
    ):
        value = data.get(key)
        if not isinstance(value, list):
            data[key] = [str(value)] if value else []
    if data.get("therapeutic_alliance") not in ("weak", "developing", "strong"):
        data["therapeutic_alliance"] = "developing"
    return data


def _clamp_score(value, default=5):
    try:
        return max(1, min(10, int(round(float(value)))))
    except (TypeError, ValueError):
        return default


def evaluate(transcript: List[Dict], evaluated_party: str, persona: Dict) -> Dict:
    system = SUPERVISOR_FEEDBACK_SYSTEM.format(
        evaluated_party=evaluated_party, feedback_schema=FEEDBACK_SCHEMA
    )
    prompt = (
        f"CLIENT CARD: {persona.get('intake_info', '')}\n\n"
        f"TRANSCRIPT (each turn tagged with its controller):\n"
        f"{transcript_as_text(transcript)}"
    )
    data = call_json(
        config.SUPERVISOR_MODEL,
        system,
        [{"role": "user", "text": prompt}],
        mock=lambda: mock.feedback(evaluated_party, transcript),
        fallback=lambda raw: mock.feedback(evaluated_party, transcript),
    )

    scores = data.get("scores") or {}
    cleaned = {}
    for dim in DIMENSIONS:
        entry = scores.get(dim)
        if isinstance(entry, dict):
            cleaned[dim] = {
                "score": _clamp_score(entry.get("score")),
                "justification": str(entry.get("justification", "")).strip(),
            }
        else:
            cleaned[dim] = {"score": _clamp_score(entry), "justification": ""}
    data["scores"] = cleaned
    data["overall_score"] = _clamp_score(
        data.get("overall_score"),
        default=round(sum(c["score"] for c in cleaned.values()) / len(DIMENSIONS)),
    )
    data["evaluated_party"] = evaluated_party
    data.setdefault("evaluated_turns", [
        m["turn"] for m in transcript
        if m["speaker"] == "counselor" and m.get("controlled_by") == evaluated_party
    ])
    for key in ("strengths", "improvements"):
        if not isinstance(data.get(key), list):
            data[key] = []
    return data
