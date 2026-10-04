# Lab3b: Counsellor Training Web-Based App

**CounselSim** — a three-role counselling simulator for counsellor training.

Course: CSE398/CSE498-024 — Generative AI for Healthcare & Robotics
Instructor: Prof. Mooi Choo Chuah
Lab 3b option: Mental Health Chatbot / Counsellor Training Web-Based App

> **Training simulation only — not a substitute for real clinical care.**

---

## Overview

CounselSim is a web application for practising counselling skills against an
LLM-played client. A counselling session has three seats — **client**,
**counsellor**, and **supervisor** — and the trainee occupies exactly one of
them at a time. Every seat the trainee is *not* holding is played by the LLM,
so the conversation always continues with three participants.

The point of the three seats is that a counsellor-in-training learns different
things from each perspective:

- sitting as the **counsellor**, you practise the skills and get whispered
  coaching from an LLM supervisor;
- sitting as the **client**, you feel what a given intervention is like on the
  receiving end, and watch a competent counsellor work;
- sitting as the **supervisor**, you practise *evaluating* a session — you
  score it yourself, then compare your scores against the LLM supervisor's.

The trainee can change seats mid-session. When they do, an LLM picks up the
seat they left, and is explicitly told to continue the previous occupant's tone
rather than restart the session.

At the end of a session the app produces a structured feedback report scored on
five dimensions, and a case-note summary that is injected into the next
session's prompts so the simulated client remembers prior sessions.

This is an educational training tool. It does not diagnose, treat, or advise
real patients, and the "Real Patients" area of the app is deliberately closed
(see [Safety / Disclaimer](#safety--disclaimer)).

---

## Features

**Chat core**

- Multi-turn conversation with full history maintained server-side in SQLite
- Clear visual separation of client / counsellor / supervisor messages
- Non-blocking input: you can type while the LLM is generating; your message
  queues and sends when your turn arrives (cancellable)
- Start a new session at any time from the patient picker; ending a session
  closes it and generates its summary

**Counsellor-training specific**

- **Simulated patient generation** — pick gender, age group, ethnicity and
  presenting concerns; the LLM writes a persona with background, speaking
  style, cultural notes, and *hidden information* it will only disclose if the
  trainee asks good open questions
- **Three modes** — A: you are the counsellor; B: you are the client; C: you
  are the supervisor observing two LLMs
- **Mid-session role switching** — change seats between turns; all switches are
  recorded in a `role_switches` table
- **Supervisor whispers** — an LLM supervisor sends a short coaching note every
  3 turns, or on demand via `Ask Supervisor`; notes are injected into the
  counsellor's system prompt only, never the client's
- **Feedback report** — 1–10 scores on cultural sensitivity, therapeutic
  progress, professional boundaries, empathy, and conversational flow, each
  justified with turn references; plus 3 strengths and 3 concrete improvements
  (original line → why → suggested alternative)
- **Attribution-correct grading** — every turn is tagged `controlled_by:
  user|llm`. If the trainee ever sat in the counsellor's seat, the report
  evaluates only their turns and excludes LLM-played ones
- **Session memory** — structured case notes persist and are injected into the
  next session, so the client remembers what was disclosed
- **3D counselling room** — low-poly Three.js scene with per-turn emotion on
  each figure (6 emotions) and a `YOU` marker that animates to your current seat

**Safety**

- Persistent disclaimer banner on every screen
- Prompts forbid describing any specific method of self-harm
- Crisis detection on trainee input (as distinct from in-character speech):
  pauses the simulation and surfaces helplines
- Offline mock mode so the app is fully demonstrable without an API key

---

## Architecture

```
Browser (vanilla JS single page, Three.js scene)
  │  fetch + Bearer token
  ▼
FastAPI  backend/main.py
  │
  ├── routers/auth.py        register / login       (bcrypt + HMAC token)
  ├── routers/patients.py    persona generation
  ├── routers/sessions.py    say / step / role / intervene / end
  └── routers/feedback.py    scored report
        │
        ▼
  session_service.py   ── loads transcript from SQLite, checks for crisis
  turnlogic.py         ── pure functions: whose turn, who controlled it,
        │                 who gets evaluated  (unit-tested, no I/O)
        ▼
  llm/common.py        ── converts the shared transcript into ONE role's
        │                 point of view (your turns = assistant, theirs = user)
        ▼
  llm/{client,counselor,supervisor}_agent.py
        │                 each builds its own system prompt from prompts.py
        ▼
  llm/gemini_client.py ── single door: 30s timeout, JSON parse + one retry,
        │                 graceful degrade, mock routing
        ├─ llm/openai_compat.py  → Groq / any OpenAI-compatible endpoint
        ├─ (google-genai SDK)    → Gemini
        └─ llm/mock.py           → offline scripted LLM (no network)
        │
        ▼
  SQLite (counselsim.db) — 8 tables, created automatically on first run
```

Each of the three roles is a **separate LLM call** with its own system prompt
and its own perspective-converted view of the same transcript. Supervisor
whispers are injected into the counsellor's system prompt only — the client's
LLM context never contains them, so the client cannot "hear" the coaching.

The client and counsellor must return
`{"speech": ..., "emotion": ..., "action": ...}` JSON, which drives the 3D
figures' expressions and body language.

---

## Model

| | |
|---|---|
| **Provider** | Groq (OpenAI-compatible `/chat/completions` API) |
| **Base URL** | `https://api.groq.com/openai/v1` |
| **Client model** | `openai/gpt-oss-20b` — many short turns, latency matters |
| **Counsellor model** | `openai/gpt-oss-120b` — needs stronger reasoning |
| **Supervisor model** | `openai/gpt-oss-120b` — reasons over the whole transcript |

**Where the model is called:** `backend/llm/gemini_client.py` is the single
entry point (`call_json` / `call_text`). It dispatches to
`backend/llm/openai_compat.py:raw_call` for Groq, or to the `google-genai` SDK
for Gemini. No other module talks to a model.

**Generation settings** (`openai_compat.py`, `config.py`):

- `temperature` 0.9 for in-character JSON turns, 0.7 otherwise
- `response_format: {"type": "json_object"}` when JSON is expected; if the
  vendor rejects it (HTTP 400) the request is retried once without it
- Hard 30s timeout per call (`LLM_TIMEOUT`), enforced with a thread future
- On unparseable JSON: one retry with a stricter instruction, then degrade to
  treating the raw text as speech with `emotion: neutral`

**Why not Gemini:** the project was originally built against Gemini. Google AI
Studio blocked API-key creation on the available account (`"Failed to create
project. The request is suspicious."`), and creating a key through Google Cloud
Console required binding it to a service account, which is a different
credential format. The LLM layer was therefore made provider-agnostic. The
Gemini path is still present and selected automatically if you supply a
`GEMINI_API_KEY` — no code change needed.

**Switching providers** — set one key in `.env`; the provider is inferred:

| Provider | Set in `.env` |
|---|---|
| Groq (default) | `GROQ_API_KEY=gsk_…` |
| Google Gemini | `GEMINI_API_KEY=AIza…` (also `pip install google-genai`) |
| Any OpenAI-compatible | `OPENAI_API_KEY=…` **and** `LLM_BASE_URL=…` |
| None (offline demo) | leave all blank → scripted mock LLM |

---

## Installation

Requires Python 3.10+.

```bash
git clone <your-repo-url>
cd counselsim

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

---

## Environment Variables

Copy the template and fill in **one** key:

```bash
# Windows
copy .env.example .env
# macOS / Linux
cp .env.example .env
```

| Variable | Required | Purpose |
|---|---|---|
| `GROQ_API_KEY` | one key required* | Groq API key (free: <https://console.groq.com/keys>) |
| `GEMINI_API_KEY` | alternative | Google AI Studio key |
| `OPENAI_API_KEY` + `LLM_BASE_URL` | alternative | any OpenAI-compatible endpoint |
| `LLM_PROVIDER` | no | force `groq` / `gemini` / `openai` instead of inferring |
| `CLIENT_MODEL` / `COUNSELOR_MODEL` / `SUPERVISOR_MODEL` | no | override model ids |
| `LLM_TIMEOUT` | no | seconds per call (default 30) |
| `FORCE_MOCK` | no | `1` forces the offline mock even with a key |
| `SECRET_KEY` | no | signs auth tokens; change for any real deployment |

\* With no key at all the app still runs end-to-end on the offline mock LLM.

**The real `.env` is never committed** — it is listed in `.gitignore`. Only
`.env.example`, which contains no secret, is in the repository.

Verify your key and model names before the demo:

```bash
python tools/check_key.py
```

It prints the detected provider, lists the model ids your key can reach, and
sends one real request per configured model.

---

## Run

```bash
python -m uvicorn backend.main:app --reload --port 8000
```

Open <http://127.0.0.1:8000>.

The startup log states which provider is live:

```
INFO:counselsim:LLM provider=groq  client=openai/gpt-oss-20b counselor=openai/gpt-oss-120b supervisor=openai/gpt-oss-120b
```

If no key is configured it logs a warning instead and the UI shows a `mock LLM`
badge in the session header.

---

## Demo Workflow

1. **Register** a user (any username 3+ chars, password 6+), then log in.
2. Choose **Simulated Patients** → **New patient**. Pick e.g. *female*,
   *18–24*, *East Asian*, concerns *academic performance* + *anxiety*. Click
   **Create**. The LLM writes the persona; the profile card appears on the right.
3. Pick role **Counsellor** and start the session. The client speaks first.
4. Type a first message:

   > I have been feeling overwhelmed by school recently. Can you tell me a bit
   > more about what that has been like?

5. Read the client's reply, then send a second message that builds on it:

   > It sounds like the deadlines are the hardest part. What happens in your
   > body when you think about them?

   The reply should refer back to what the client said in step 4 — this is the
   multi-turn context check.
6. After 3 turns a **supervisor whisper** appears, or click **Ask Supervisor**.
7. Click **Switch role → Client** to change seats mid-session; the `YOU` marker
   animates across the room and an LLM takes over the counsellor's chair.
8. Click **End session** → a structured case-note summary is generated, then
   **Feedback** for the scored report.
9. Start a second session with the *same* patient — the previous summary card
   appears, and the client remembers what was disclosed.

---

## Project Structure

```
counselsim/
  backend/
    main.py              FastAPI entry point; also serves the frontend
    config.py            provider/model selection, timeouts, safety copy
    db.py  models.py     SQLAlchemy + SQLite, 8 tables
    security.py          bcrypt hashing, HMAC-signed bearer tokens
    turnlogic.py         pure functions: turn order, control, grading target
    session_service.py   transcript assembly, crisis check, summary injection
    llm/
      gemini_client.py   single entry point: timeout, JSON retry, mock routing
      openai_compat.py   Groq / OpenAI-compatible provider
      prompts.py         system prompts for all three roles
      client_agent.py  counselor_agent.py  supervisor_agent.py
      common.py          perspective conversion, output normalisation
      mock.py            offline scripted LLM
    routers/             auth.py  patients.py  sessions.py  feedback.py
  frontend/
    index.html  css/style.css
    js/api.js  ui.js  scene.js  figures.js
    scene-preview.html   3D scene preview without starting the backend
  tools/
    check_key.py         verify API key + model ids against the live API
    smoke_test.py        offline end-to-end test of every acceptance item
    test_turnlogic.py    14 unit tests for turn/attribution rules
  requirements.txt  .env.example  .gitignore  README.md
```

**Database tables:** `users`, `patients`, `sessions`, `messages`,
`supervisor_notes`, `role_switches`, `session_summaries`, `feedback_reports`.
`counselsim.db` is created on first run and is git-ignored.

---

## Testing

| Test | How to run | Result |
|---|---|---|
| Turn/attribution unit tests | `python tools/test_turnlogic.py` | **14 passed, 0 failed** |
| Offline end-to-end smoke test | `python tools/smoke_test.py` | **61 passed, 0 failed** |
| Live API + model check | `python tools/check_key.py` | **3/3 models OK** on Groq |
| Live multi-turn session | manual, in the browser | **verified** — see below |

`smoke_test.py` drives the whole app in memory with the mock LLM: register →
login → create patient → mode A conversation → two mid-session role switches →
supervisor intervention → end session + summary → feedback report with correct
user/LLM attribution → second session reading the prior summary → mode B →
mode C score comparison → crisis detection.

**Live multi-turn evidence.** A real session was run against Groq and persisted
to SQLite. Context carried across turns: the counsellor's turn 6 reflected the
client's turn 5 phrasing (*"tight knot in your chest"*), and turn 8 referenced
the coping strategy and family expectation introduced in turn 7 (*"drawing"*,
*"Mom's expectations"*). Both the structured summary and the feedback report
(overall score 7/10, all 11 fields populated) generated successfully.

**Missing-key behaviour** is covered by design: with no key, `config.USE_MOCK`
becomes true, the startup log warns, the UI shows a `mock LLM` badge, and every
agent routes to `llm/mock.py` instead of the network.

---

## Error Handling

| Failure | Behaviour |
|---|---|
| No API key | Falls back to the offline mock LLM; warning logged; `mock LLM` badge in the UI |
| Invalid key / model not found | LLM call raises `LLMError` → HTTP 502 with the vendor's message → toast in the UI; the session stays open |
| API timeout | Hard 30s cap per call → `LLMError` → 502 → toast; no hung request |
| Malformed JSON from the model | One stricter retry, then degrade to raw text as speech with neutral emotion |
| `response_format` unsupported | Automatic retry without it |
| Empty input | Send button is disabled; backend rejects with 422 (`min_length=1`) |
| Expired/invalid token | 401 → client clears the token and returns to the login screen |
| Turn raced (you typed while the LLM was mid-turn) | 409 → message is queued and auto-sent when your turn comes |
| Backend unreachable at page load | Caught; the login screen still renders |

---

## Limitations

- **Not clinically validated.** Scores and coaching come from a general-purpose
  LLM with no clinical training, validation, or inter-rater reliability. Treat
  the numbers as discussion prompts, not assessment.
- **Simulated clients are not real people.** Personas are LLM-generated
  fiction. They may be culturally stereotyped or unrealistically cooperative.
- **Grading is non-deterministic.** The same transcript can score differently
  across runs; there is no fixed rubric anchor or calibration set.
- **Single-user sessions.** No concurrency control; two browser tabs on the
  same session will race.
- **Auth is coursework-grade.** bcrypt + HMAC bearer tokens over plain HTTP on
  localhost. No HTTPS, rate limiting, password reset, or account lockout.
- **Crisis detection is regex-based** (`config.CRISIS_PATTERNS`) and matches
  English phrasings only. It will miss indirect or non-English expressions. It
  is a safety net for an obvious case, not a screening instrument.
- **No moderation layer** beyond prompt instructions; a jailbroken prompt could
  still elicit unsafe content.
- **Free-tier model limits.** Groq rate-limits the free tier, and model ids are
  retired periodically — `tools/check_key.py` exists because of this.
- **"Real Patients" is intentionally non-functional.**

---

## Safety / Disclaimer

**This is an educational counsellor-training simulation. It is not a therapist,
not a medical device, and not a substitute for professional mental-health
care.** It must not be used with real patients or real patient data.

Safety measures actually implemented in the code:

- A disclaimer banner is pinned to every screen (`config.SAFETY_BANNER`).
- All role prompts explicitly forbid describing any specific method of
  self-harm, in character or in case notes (`llm/prompts.py`).
- The counsellor prompt instructs a gentle risk check and safety-planning if
  the client raises self-harm — never a discussion of methods.
- Trainee input is screened for first-person crisis language distinct from
  in-character speech (`config.CRISIS_PATTERNS`). On a match the simulation
  pauses and helplines are displayed (`config.CRISIS_RESOURCES`): 988 (US/CA),
  116 123 (UK/IE), <https://findahelpline.com>, and Lehigh UCPS 610-758-3880.
- The persona generator is instructed to avoid harmful content and to produce
  entirely fictional people.
- The **Real Patients** section is a closed placeholder that explains why real
  records would require de-identification, IRB approval, and a HIPAA-compliant
  data pathway.
- The API key lives only in the backend `.env`; the browser never sees it. All
  model calls are server-side.

The LLM may still produce inaccurate, culturally insensitive, or
clinically inappropriate output. Nothing it says should be taken as
professional advice.

---

## Acknowledgements

Built for CSE398/CSE498-024 Lab 3b. The three-role design, attribution-aware
grading, and cross-session memory are extensions beyond the base assignment
brief.
