"""Pure turn-order / attribution rules (no framework imports, easy to test)."""
from typing import Dict, List

ROLES = ("counselor", "client", "supervisor")
SPEAKING_ROLES = ("client", "counselor")


def next_speaker(transcript: List[Dict]) -> str:
    """The client always opens; after that the two chairs alternate."""
    if not transcript:
        return "client"
    return "counselor" if transcript[-1]["speaker"] == "client" else "client"


def next_controller(user_role: str, transcript: List[Dict]) -> str:
    """Who plays the next turn: the user, or an LLM.

    Whatever chair the user is not sitting in is played by an LLM - which is
    also what makes a mid-session role switch safe: nobody is ever left
    without a speaker.
    """
    return "user" if next_speaker(transcript) == user_role else "llm"


def counselor_took_over(transcript: List[Dict]) -> bool:
    """True once the counsellor chair has changed hands at least once."""
    controllers = {m["controlled_by"] for m in transcript if m["speaker"] == "counselor"}
    return len(controllers) > 1


def evaluated_party(transcript: List[Dict]) -> str:
    """Feedback targets the user's counsellor turns if they ever held the chair."""
    for m in transcript:
        if m["speaker"] == "counselor" and m["controlled_by"] == "user":
            return "user"
    return "llm"


def counselor_turns(transcript: List[Dict], controlled_by: str) -> List[int]:
    return [
        m["turn"] for m in transcript
        if m["speaker"] == "counselor" and m["controlled_by"] == controlled_by
    ]
