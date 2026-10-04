"""Central configuration for CounselSim.

Every model name lives here so it can be swapped in one place.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# --------------------------------------------------------------------------
# LLM provider
# --------------------------------------------------------------------------
# Three roles, one provider. Supported values for LLM_PROVIDER:
#
#   gemini   -> Google AI Studio, via the google-genai SDK
#   groq     -> Groq, via the OpenAI-compatible /chat/completions dialect
#   openai   -> any other OpenAI-compatible endpoint (OpenRouter, DeepSeek,
#               Moonshot, 智谱, a local vLLM/Ollama, OpenAI itself); set
#               LLM_BASE_URL yourself
#
# Leave LLM_PROVIDER empty and it is inferred from whichever key is present,
# so a one-line .env is enough to switch vendors.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

_PROVIDER_ENV = os.getenv("LLM_PROVIDER", "").strip().lower()
if _PROVIDER_ENV:
    LLM_PROVIDER = _PROVIDER_ENV
elif GROQ_API_KEY:
    LLM_PROVIDER = "groq"
elif OPENAI_API_KEY:
    LLM_PROVIDER = "openai"
elif GEMINI_API_KEY:
    LLM_PROVIDER = "gemini"
else:
    LLM_PROVIDER = "none"

_DEFAULT_BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "openai": "https://api.openai.com/v1",
}
LLM_BASE_URL = (
    os.getenv("LLM_BASE_URL", "").strip()
    or _DEFAULT_BASE_URLS.get(LLM_PROVIDER, "")
)

_KEYS = {
    "gemini": GEMINI_API_KEY,
    "groq": GROQ_API_KEY,
    "openai": OPENAI_API_KEY,
}
# The key actually in play, whichever vendor won above.
LLM_API_KEY = _KEYS.get(LLM_PROVIDER, "")

# --------------------------------------------------------------------------
# LLM models
# --------------------------------------------------------------------------
# Per-provider defaults. Override any of them in .env. If a vendor rejects a
# name ("model not found"), run `python tools/check_key.py` - it prints the
# model ids your key can actually reach.
_DEFAULT_MODELS = {
    # (client, counselor, supervisor) - the supervisor gets the stronger model
    # because it has to reason over the whole transcript at once.
    "gemini": ("gemini-2.5-flash-lite", "gemini-2.5-flash-lite", "gemini-2.5-flash"),
    # Groq retired the Llama family; gpt-oss is what the free tier serves now.
    # The 20b handles the client (faster, cheaper turns), the 120b handles the
    # counsellor and supervisor, who need the stronger reasoning.
    "groq": (
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-120b",
    ),
    "openai": ("gpt-4o-mini", "gpt-4o-mini", "gpt-4o"),
}
_client_d, _counselor_d, _supervisor_d = _DEFAULT_MODELS.get(
    LLM_PROVIDER, _DEFAULT_MODELS["gemini"]
)

CLIENT_MODEL = os.getenv("CLIENT_MODEL", _client_d)
COUNSELOR_MODEL = os.getenv("COUNSELOR_MODEL", _counselor_d)
SUPERVISOR_MODEL = os.getenv("SUPERVISOR_MODEL", _supervisor_d)

# Seconds to wait for any single LLM call before giving up.
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "30"))

# When no API key is present we fall back to a scripted offline "LLM" so the
# whole app can still be demoed. Set FORCE_MOCK=1 to use it even with a key.
FORCE_MOCK = os.getenv("FORCE_MOCK", "0") == "1"
USE_MOCK = FORCE_MOCK or not LLM_API_KEY

# --------------------------------------------------------------------------
# Storage / auth
# --------------------------------------------------------------------------
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "counselsim.db"))
DATABASE_URL = f"sqlite:///{DB_PATH}"

SECRET_KEY = os.getenv("SECRET_KEY", "counselsim-dev-secret-change-me")
TOKEN_TTL_SECONDS = int(os.getenv("TOKEN_TTL_SECONDS", str(60 * 60 * 24 * 7)))

# --------------------------------------------------------------------------
# Session behaviour
# --------------------------------------------------------------------------
SUPERVISOR_TIP_EVERY_N_TURNS = 3
AUTOPLAY_DELAY_SECONDS = 3  # mode C pacing (enforced by the frontend)

EMOTIONS = ["neutral", "sad", "anxious", "angry", "relieved", "thinking"]

CONCERN_OPTIONS = [
    "academic performance",
    "parent-child relationship",
    "cultural adjustment",
    "anxiety",
    "low mood",
    "burnout",
    "grief",
    "loneliness",
    "relationship difficulties",
    "self-esteem",
]

GENDER_OPTIONS = ["female", "male", "non-binary", "prefer not to say"]
AGE_GROUP_OPTIONS = ["13-17", "18-24", "25-34", "35-49", "50-64", "65+"]
ETHNICITY_OPTIONS = [
    "East Asian",
    "South Asian",
    "Southeast Asian",
    "Black / African diaspora",
    "Hispanic / Latino",
    "Middle Eastern / North African",
    "White / European",
    "Indigenous",
    "Mixed heritage",
]

SAFETY_BANNER = (
    "Training simulation only — not a substitute for real clinical care."
)

# Phrases that suggest the *user* (not their character) may be in crisis.
CRISIS_PATTERNS = [
    r"\bi want to (kill|hurt|harm) myself\b",
    r"\bi'?m going to (kill|hurt|harm) myself\b",
    r"\bi want to die\b",
    r"\bi'?m suicidal\b",
    r"\bend my life\b",
    r"\bi can'?t go on\b.*\breal(ly)?\b",
]

CRISIS_RESOURCES = {
    "message": (
        "It sounds like this may be about you, not the character you are "
        "playing. The simulation is paused. If you are in danger right now, "
        "please contact local emergency services."
    ),
    "resources": [
        "US & Canada: call or text 988 (Suicide & Crisis Lifeline)",
        "UK & Ireland: call 116 123 (Samaritans)",
        "International directory: https://findahelpline.com",
        "Lehigh University Counseling & Psychological Services (UCPS): "
        "610-758-3880",
    ],
}
