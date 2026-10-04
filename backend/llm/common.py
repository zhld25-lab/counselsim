"""Shared helpers: perspective conversion and output normalisation."""
from typing import Dict, List

from config import EMOTIONS


def to_contents(transcript: List[Dict], me: str) -> List[Dict]:
    """Convert the shared transcript into one role's point of view.

    For the client LLM the counsellor's turns are `user` messages and its own
    are `model` messages; for the counsellor LLM it is the other way round.
    Supervisor material is never included here - it is injected into the
    counsellor's *system* prompt only, so the client can never see it.
    """
    contents: List[Dict] = []
    for m in transcript:
        role = "model" if m["speaker"] == me else "user"
        text = m["text"]
        action = m.get("action")
        if action and role == "user":
            text = f"{text}  [{action}]"
        if contents and contents[-1]["role"] == role:
            contents[-1]["text"] += "\n" + text
        else:
            contents.append({"role": role, "text": text})

    if not contents or contents[-1]["role"] == "model":
        contents.append(
            {"role": "user", "text": "(it is your turn to speak now)"}
        )
    return contents


def transcript_as_text(transcript: List[Dict], include_control: bool = True) -> str:
    lines = []
    for m in transcript:
        tag = f" [controlled_by={m.get('controlled_by', 'llm')}]" if include_control else ""
        emo = m.get("emotion", "neutral")
        lines.append(f"Turn {m['turn']} - {m['speaker']}{tag} ({emo}): {m['text']}")
    return "\n".join(lines) if lines else "(the session has not started yet)"


def normalise_utterance(data: dict) -> dict:
    """Coerce whatever the model returned into the animation contract."""
    speech = (data.get("speech") or data.get("text") or "").strip()
    emotion = str(data.get("emotion") or "neutral").strip().lower()
    if emotion not in EMOTIONS:
        emotion = "neutral"
    action = str(data.get("action") or "").strip()[:160]
    return {"speech": speech, "emotion": emotion, "action": action}


def raw_text_fallback(raw: str) -> dict:
    """Second parse failure: treat the raw text as speech, emotion neutral."""
    return {"speech": (raw or "...").strip()[:800], "emotion": "neutral", "action": ""}
