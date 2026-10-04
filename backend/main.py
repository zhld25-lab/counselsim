"""CounselSim - FastAPI entry point.

Run from the project root:
    python -m uvicorn backend.main:app --reload --port 8000
or from this folder:
    python main.py
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import logging  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

import config  # noqa: E402
from db import init_db  # noqa: E402
from routers import auth, feedback, patients, sessions  # noqa: E402

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("counselsim")

app = FastAPI(title="CounselSim", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup():
    init_db()
    if config.USE_MOCK:
        log.warning(
            "No API key found (or FORCE_MOCK=1) - running with the offline mock "
            "LLM. Put a GROQ_API_KEY or GEMINI_API_KEY in .env to use a real model."
        )
    else:
        log.info(
            "LLM provider=%s  client=%s counselor=%s supervisor=%s",
            config.LLM_PROVIDER,
            config.CLIENT_MODEL, config.COUNSELOR_MODEL, config.SUPERVISOR_MODEL,
        )


@app.get("/api/meta")
def meta():
    return {
        "banner": config.SAFETY_BANNER,
        "mock_mode": config.USE_MOCK,
        "emotions": config.EMOTIONS,
        "roles": ["counselor", "client", "supervisor"],
        "autoplay_delay_seconds": config.AUTOPLAY_DELAY_SECONDS,
        "models": {
            "client": config.CLIENT_MODEL,
            "counselor": config.COUNSELOR_MODEL,
            "supervisor": config.SUPERVISOR_MODEL,
        },
    }


@app.get("/api/health")
def health():
    return {"ok": True}


app.include_router(auth.router)
app.include_router(patients.router)
app.include_router(feedback.router)
app.include_router(sessions.router)

FRONTEND_DIR = config.BASE_DIR / "frontend"
if FRONTEND_DIR.exists():

    @app.get("/")
    def index():
        return FileResponse(FRONTEND_DIR / "index.html")

    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
