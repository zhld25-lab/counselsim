"""The COUNSELLOR LLM."""
import json
from typing import Dict, List

import config
from llm import mock
from llm.common import normalise_utterance, raw_text_fallback, to_contents
from llm.gemini_client import call_json
from llm.prompts import COUNSELOR_SYSTEM


def _system_prompt(persona: Dict, prior_summary: str, supervisor_note: str,
                   took_over: bool) -> str:
    system = COUNSELOR_SYSTEM.format(
        intake_info=persona.get("intake_info", ""),
        prior_summary=prior_summary or "(this is the first session)",
        latest_supervisor_note=supervisor_note or "(none)",
    )
    if supervisor_note:
        system += (
            "\nThe supervisor guidance above is MANDATORY for this turn: your next "
            "reply must visibly act on it, without ever mentioning the supervisor.\n"
        )
    if took_over:
        system += (
            "\nYou are taking over this role mid-session from someone else. Read the "
            "counsellor turns already in the transcript and continue with the same "
            "tone, stance and anything already agreed. Do not re-introduce yourself.\n"
        )
    return system


def speak(
    persona: Dict,
    transcript: List[Dict],
    prior_summary: str = "",
    supervisor_note: str = "",
    took_over: bool = False,
) -> Dict:
    system = _system_prompt(persona, prior_summary, supervisor_note, took_over)
    contents = to_contents(transcript, me="counselor")
    data = call_json(
        config.COUNSELOR_MODEL,
        system,
        contents,
        mock=lambda: mock.turn("counselor", transcript),
        fallback=raw_text_fallback,
    )
    out = normalise_utterance(data)
    if not out["speech"]:
        out["speech"] = json.dumps(data)[:300]
    return out
