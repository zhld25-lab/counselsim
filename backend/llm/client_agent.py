"""The CLIENT (patient) LLM: persona generation and in-session turns."""
import json
from typing import Dict, List

import config
from llm import mock
from llm.common import normalise_utterance, raw_text_fallback, to_contents
from llm.gemini_client import call_json
from llm.prompts import CLIENT_SYSTEM, PERSONA_SYSTEM


def generate_persona(gender: str, age_group: str, ethnicity: str, concerns: List[str]) -> Dict:
    system = PERSONA_SYSTEM.format(
        gender=gender,
        age_group=age_group,
        ethnicity=ethnicity,
        concerns=", ".join(concerns) or "general distress",
    )
    data = call_json(
        config.CLIENT_MODEL,
        system,
        [{"role": "user", "text": "Create the client persona now."}],
        mock=lambda: mock.persona(gender, age_group, ethnicity, concerns),
        fallback=lambda raw: mock.persona(gender, age_group, ethnicity, concerns),
    )
    base = mock.persona(gender, age_group, ethnicity, concerns)
    base.pop("_mock", None)
    for key, value in data.items():
        if value:
            base[key] = value
    if not isinstance(base.get("secrets"), list):
        base["secrets"] = [str(base.get("secrets", ""))]
    try:
        base["age"] = int(base["age"])
    except (TypeError, ValueError):
        base["age"] = 24
    if base.get("opening_emotion") not in config.EMOTIONS:
        base["opening_emotion"] = "anxious"
    return base


def _system_prompt(patient, persona: Dict, prior_summary: str) -> str:
    return CLIENT_SYSTEM.format(
        name=persona.get("name", patient.display_name),
        age=persona.get("age", patient.age or "?"),
        gender=patient.gender,
        ethnicity=patient.ethnicity,
        concerns=", ".join(patient.concerns or []),
        background=persona.get("background", ""),
        style=persona.get("style", ""),
        secrets="; ".join(persona.get("secrets", [])) or "(none)",
        cultural_notes=persona.get("cultural_notes", ""),
        prior_summary=prior_summary or "(this is the first session)",
    )


def speak(patient, persona: Dict, transcript: List[Dict], prior_summary: str = "") -> Dict:
    """Produce the client's next utterance as {speech, emotion, action}."""
    system = _system_prompt(patient, persona, prior_summary)
    contents = to_contents(transcript, me="client")
    data = call_json(
        config.CLIENT_MODEL,
        system,
        contents,
        mock=lambda: mock.turn("client", transcript),
        fallback=raw_text_fallback,
    )
    out = normalise_utterance(data)
    if not out["speech"]:
        out["speech"] = json.dumps(data)[:300]
    return out
