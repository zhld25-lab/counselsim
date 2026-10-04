"""Offline scripted stand-in for Gemini.

Used automatically when GEMINI_API_KEY is missing (or FORCE_MOCK=1) so the
whole app - including the 3D scene, role switching, summaries and feedback -
can be demoed without any network access. Replies are deterministic-ish and
shaped by the transcript so the demo still feels like a conversation.
"""
import random

_FIRST_NAMES = {
    "East Asian": ["Mei", "Jun", "Hana", "Wei", "Sora"],
    "South Asian": ["Anaya", "Rohan", "Priya", "Dev", "Ishaan"],
    "Southeast Asian": ["Linh", "Arif", "Dara", "Nadia", "Bayu"],
    "Black / African diaspora": ["Amara", "Kwame", "Zuri", "Malik", "Chidi"],
    "Hispanic / Latino": ["Camila", "Mateo", "Lucia", "Diego", "Valeria"],
    "Middle Eastern / North African": ["Layla", "Omar", "Yasmin", "Karim", "Rana"],
    "White / European": ["Hannah", "Thomas", "Greta", "Liam", "Marta"],
    "Indigenous": ["Aiyana", "Tahoma", "Nayeli", "Kanti", "Sequoia"],
    "Mixed heritage": ["Noa", "Elias", "Maya", "Kai", "Sienna"],
}
_LAST_NAMES = ["Alvarez", "Chen", "Okafor", "Patel", "Novak", "Haddad", "Lindqvist",
               "Moreau", "Santos", "Whitefeather"]

_AGE_MID = {"13-17": 16, "18-24": 20, "25-34": 29, "35-49": 41, "50-64": 56, "65+": 68}


def _rand(seed_text: str) -> random.Random:
    return random.Random(hash(seed_text) & 0xFFFFFFFF)


# --------------------------------------------------------------------------
# persona
# --------------------------------------------------------------------------
def persona(gender: str, age_group: str, ethnicity: str, concerns):
    rng = _rand(f"{gender}{age_group}{ethnicity}{concerns}")
    first = rng.choice(_FIRST_NAMES.get(ethnicity, _FIRST_NAMES["Mixed heritage"]))
    last = rng.choice(_LAST_NAMES)
    concern_text = ", ".join(concerns) if concerns else "general distress"
    age = _AGE_MID.get(age_group, 24) + rng.randint(-2, 2)
    return {
        "name": f"{first} {last}",
        "age": age,
        "occupation": rng.choice(
            ["second-year student", "graduate researcher", "retail supervisor",
             "junior nurse", "software tester", "part-time barista"]
        ),
        "background": (
            f"{first} moved for study or work about two years ago and has been "
            f"managing on their own since. Family calls every weekend and the "
            f"conversations mostly stay on the surface. Lately {concern_text} "
            f"has been taking up most of their week, and sleep has been thin."
        ),
        "style": rng.choice(
            ["hesitant, short answers at first",
             "polite and agreeable, deflects with humour",
             "talks quickly, jumps between topics",
             "careful and measured, downplays feelings"]
        ),
        "secrets": [
            "has not told family about how badly things are going",
            "skipped classes or shifts several times in the last month",
            "an argument with a close friend that has not been repaired",
        ],
        "cultural_notes": (
            "In their family, difficulties are usually framed as problems to be "
            "solved quietly; naming feelings directly can feel like complaining."
        ),
        "opening_line": rng.choice([
            "I wasn't sure I'd actually come today... but here I am.",
            "Sorry, I don't really know where to start with this.",
            "It's probably not a big deal. My friend said I should talk to someone.",
        ]),
        "opening_emotion": rng.choice(["anxious", "neutral", "thinking"]),
        "intake_info": (
            f"{first} {last}, {age}, {gender}, {ethnicity}. Self-referred. "
            f"Presenting concerns: {concern_text}. No prior counselling."
        ),
    }


# --------------------------------------------------------------------------
# in-session turns
# --------------------------------------------------------------------------
_CLIENT_LINES = [
    ("I guess... it's been building up for a while. I just keep pushing through.",
     "anxious", "picks at their sleeve"),
    ("Everyone else seems to manage fine. That's the part I keep getting stuck on.",
     "sad", "looks down"),
    ("I haven't told my family. They'd worry, and then I'd have to manage that too.",
     "thinking", "shifts in the seat"),
    ("Honestly? Most mornings I just... sit there before I can get moving.",
     "sad", "long pause"),
    ("It helps a bit, saying it out loud. I didn't expect that.",
     "relieved", "small exhale"),
    ("I don't need someone to fix it. I just don't want to feel like this every day.",
     "angry", "sits up straighter"),
    ("There was something last month I haven't really told anyone about.",
     "anxious", "hesitates"),
    ("Maybe I could try one small thing this week. Nothing big.",
     "neutral", "nods slightly"),
]

_COUNSELOR_LINES = [
    ("Thank you for coming in - that first step isn't small. What's been on your mind most this week?",
     "neutral", "leans in slightly"),
    ("It sounds like you've been carrying this mostly on your own. What has that been like?",
     "neutral", "nods"),
    ("I hear both the tiredness and the pressure to keep going. Which one feels heavier right now?",
     "thinking", "soft eye contact"),
    ("You mentioned your family - I don't want to assume. How are difficulties usually talked about at home?",
     "neutral", "open posture"),
    ("That sounds lonely. I want to check something gently: have there been moments you've felt unsafe?",
     "neutral", "slows pace"),
    ("So if I've got it right: it's been building, you've been coping alone, and you'd like it to ease. Did I miss anything?",
     "neutral", "summarising gesture"),
    ("What would a slightly better week look like - not a perfect one, just slightly better?",
     "neutral", "encouraging"),
    ("Before we close, shall we agree on one small thing to try, and pick it up next time?",
     "relieved", "sits back"),
]


def turn(speaker: str, transcript):
    lines = _CLIENT_LINES if speaker == "client" else _COUNSELOR_LINES
    said = [m["text"] for m in transcript if m["speaker"] == speaker]
    idx = min(len(said), len(lines) - 1)
    speech, emotion, action = lines[idx]
    return {"speech": speech, "emotion": emotion, "action": action}


def whisper(transcript):
    tips = [
        ("They just named feeling alone with this - reflect that before asking anything else.",
         "reflection of feeling"),
        ("You have three closed questions in a row. Try one open question about their week.",
         "open-ended questioning"),
        ("They hinted at something they haven't told anyone. Leave a pause and let it come.",
         "use of silence"),
        ("Check culture rather than assume it - ask how their family talks about stress.",
         "cultural humility"),
        ("Low mood plus poor sleep: a gentle safety check is due now.", "risk assessment"),
        ("You're moving toward advice. Summarise first and ask what they want from today.",
         "pacing / collaboration"),
    ]
    tip, skill = tips[(len(transcript) // 2) % len(tips)]
    return {"tip": tip, "focus_skill": skill}


# --------------------------------------------------------------------------
# post-session artefacts
# --------------------------------------------------------------------------
def summary(session_number, transcript, secrets):
    emotions = [m.get("emotion", "neutral") for m in transcript if m["speaker"] == "client"]
    return {
        "session_number": session_number,
        "presenting_issues_discussed": ["ongoing stress", "coping alone", "sleep difficulty"],
        "key_facts_disclosed": [
            "has not told family how bad things have got",
            "has been pushing through for several weeks",
        ],
        "emotional_state_start": emotions[0] if emotions else "anxious",
        "emotional_state_end": emotions[-1] if emotions else "neutral",
        "risk_indicators": [],
        "coping_strategies_mentioned": ["keeping busy", "talking to one friend"],
        "goals_or_homework_agreed": ["try one small change before next session"],
        "therapeutic_alliance": "developing" if len(transcript) < 8 else "strong",
        "unresolved_threads": [
            "the thing they hinted at but did not describe",
            "how to involve family, if at all",
        ],
        "hidden_info_revealed": secrets[:1] if secrets else [],
        "_mock": True,
    }


def feedback(evaluated_party, transcript):
    turns = [m for m in transcript
             if m["speaker"] == "counselor" and m.get("controlled_by") == evaluated_party]
    first_turn = turns[0]["turn"] if turns else 0
    last_turn = turns[-1]["turn"] if turns else 0
    base = 7 if evaluated_party == "llm" else 6

    def dim(name, score, why):
        return {"score": score, "justification": why}

    return {
        "evaluated_party": evaluated_party,
        "evaluated_turns": [t["turn"] for t in turns],
        "scores": {
            "cultural_sensitivity": dim(
                "cultural_sensitivity", base,
                f"Turn {first_turn} asked about family context rather than assuming, "
                "but cultural meaning was not followed up later."),
            "therapeutic_progress": dim(
                "therapeutic_progress", base,
                f"By turn {last_turn} the concern was clearer, though no shared goal "
                "was fully agreed."),
            "professional_boundaries": dim(
                "professional_boundaries", base + 2,
                "No inappropriate self-disclosure or promises across the evaluated turns."),
            "empathy": dim(
                "empathy", base + 1,
                f"Turn {first_turn} validated the effort it took to attend; later "
                "reflections were shorter."),
            "conversational_flow": dim(
                "conversational_flow", base,
                "Pacing was mostly steady; a few questions arrived before the previous "
                "answer had landed."),
        },
        "additional_assessment": {
            "active_listening": "Reflections were present but often paraphrase rather than feeling.",
            "open_ended_questioning": "Roughly half the questions were open; widen the rest.",
            "safety_and_ethics": "A gentle risk check was raised; document and follow up next session.",
        },
        "overall_score": base + 1,
        "overall_rationale": (
            "Empathy and boundaries weighted most heavily for an early session; "
            "therapeutic progress weighted less because rapport-building comes first."),
        "strengths": [
            "Opened with warmth and made attending feel worthwhile",
            "Asked about family culture instead of assuming",
            "Kept a clear professional frame throughout",
        ],
        "improvements": [
            {"turn": first_turn,
             "original": turns[0]["text"] if turns else "(no counsellor turns by this party)",
             "why": "Moves to content before naming the feeling underneath it.",
             "alternative": "It took something to walk in here today. What's the feeling that's loudest right now?"},
            {"turn": last_turn,
             "original": turns[-1]["text"] if turns else "(n/a)",
             "why": "Closes the topic before checking the client's own priority.",
             "alternative": "Before we move on - of everything we've touched, which piece matters most to you?"},
            {"turn": last_turn,
             "original": "(overall pattern)",
             "why": "Several questions in a row without a reflection between them.",
             "alternative": "Alternate: reflect, pause, then one open question."},
        ],
        "_mock": True,
    }
