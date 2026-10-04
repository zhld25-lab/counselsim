# Lab 3b Technical Report — CounselSim

**A three-role counsellor-training web application**

| | |
|---|---|
| Course | CSE398/CSE498-024 — Generative AI for Healthcare & Robotics |
| Instructor | Prof. Mooi Choo Chuah |
| Lab 3b option | Mental Health Chatbot / Counsellor Training Web-Based App |
| Repository | <https://github.com/zhld25-lab/counselsim> |
| Date | October 2026 |

---

## 1. Abstract

CounselSim is a web application for practising counselling skills against an
LLM-played client. Unlike a single-assistant chatbot, a session has three
seats — **client**, **counsellor**, and **supervisor** — and the trainee
occupies exactly one of them at a time while LLMs play the rest. The trainee
can change seats mid-session; an LLM then takes over the vacated seat and is
instructed to continue the previous occupant's approach rather than restart.

The system produces two artefacts per session: a structured case note that is
injected into the next session's prompts (giving the simulated client memory
across sessions), and a feedback report scored on five dimensions. The report
is **attribution-aware**: every turn carries a `controlled_by` tag, and the
report grades only the turns the trainee actually spoke.

The application is implemented in FastAPI + SQLite with a vanilla-JS frontend
and a Three.js scene. The LLM layer is provider-agnostic; the delivered
configuration uses Groq's `openai/gpt-oss` models. All 75 automated tests pass,
and the system was exercised across four live sessions against the real API.

---

## 2. Design rationale

### 2.1 Why three roles rather than one chatbot

A counsellor-in-training needs more than conversational practice. The three
seats correspond to three distinct learning activities:

| Seat | What it trains |
|---|---|
| Counsellor | Performing the skill, with live supervisory coaching |
| Client | Experiencing an intervention from the receiving end |
| Supervisor | *Evaluating* a session — scoring it, then comparing against the AI supervisor |

The supervisor seat is the one that is hardest to practise in a classroom, and
it is also where the system's most interesting behaviour emerges (§5.3).

### 2.2 Why role switching matters

Switching seats mid-session is not a convenience feature. It creates the
condition the attribution logic exists to handle: a single transcript in which
some counsellor turns are human and some are machine. Grading such a transcript
naively would credit the trainee for the model's turns. §5.2 shows the system
separating them correctly.

### 2.3 Scope limits taken deliberately

The "Real Patients" area is a closed placeholder. Connecting real records would
require de-identification, IRB approval, and a HIPAA-compliant data pathway;
none of these are in scope for a course lab, and building a convincing
non-compliant version would be worse than building none.

---

## 3. System architecture

```
Browser (vanilla JS single page + Three.js scene)
  │  fetch + Bearer token
  ▼
FastAPI  backend/main.py
  ├── routers/auth.py        register / login      (bcrypt + HMAC token)
  ├── routers/patients.py    persona generation
  ├── routers/sessions.py    say / step / role / intervene / end
  └── routers/feedback.py    scored report
        │
  session_service.py  ── transcript assembly, crisis check, summary injection
  turnlogic.py        ── pure functions: whose turn, who controlled it,
        │                who gets evaluated (unit-tested, no I/O)
  llm/common.py       ── perspective conversion
        │
  llm/{client,counselor,supervisor}_agent.py
        │
  llm/gemini_client.py ── single door: 30s timeout, JSON retry, mock routing
        ├─ llm/openai_compat.py  → Groq / any OpenAI-compatible endpoint
        ├─ (google-genai SDK)    → Gemini
        └─ llm/mock.py           → offline scripted LLM
        │
  SQLite — 8 tables
```

**Code size:** 2,413 lines of Python (backend + tools), 1,867 lines of
HTML/CSS/JS.

### 3.1 Perspective conversion

The three roles share one transcript but must each see it from their own point
of view. `llm/common.py:to_contents` rewrites the shared log per role: a turn
spoken by the requesting role becomes an `assistant`/`model` message, every
other turn becomes a `user` message. Consecutive same-role turns are merged,
and a trailing `(it is your turn to speak now)` nudge is appended when the log
would otherwise end on the model's own voice.

### 3.2 Information isolation

Supervisor whispers are injected into the **counsellor's system prompt only**.
The client agent's context never contains them, so the simulated client cannot
"overhear" coaching about itself. This is enforced structurally — the client
agent is never passed the note — rather than by instructing the model not to
mention it.

### 3.3 Turn logic as pure functions

`backend/turnlogic.py` contains five functions with no I/O:
`next_speaker`, `next_controller`, `counselor_took_over`, `evaluated_party`,
and `counselor_turns`. Isolating these made the attribution rules unit-testable
without a database or an API key; they account for 14 of the project's tests.

### 3.4 Provider abstraction

`llm/gemini_client.py` owns the cross-cutting concerns — timeout enforcement,
JSON extraction with one retry, graceful degradation, and mock routing — and
dispatches the actual request to one of two backends based on `config.LLM_PROVIDER`.
Adding Groq required one new module (`openai_compat.py`, ~120 lines) and no
changes to any agent, router, or frontend file.

---

## 4. Implementation details

### 4.1 Model configuration

| | |
|---|---|
| Provider | Groq (OpenAI-compatible `/chat/completions`) |
| Base URL | `https://api.groq.com/openai/v1` |
| Client model | `openai/gpt-oss-20b` — many short turns, latency-sensitive |
| Counsellor model | `openai/gpt-oss-120b` — stronger reasoning needed |
| Supervisor model | `openai/gpt-oss-120b` — reasons over the whole transcript |

Generation settings: `temperature` 0.9 for in-character JSON turns and 0.7
otherwise; `response_format: {"type": "json_object"}` when JSON is expected,
with an automatic retry without it on HTTP 400; a hard 30-second timeout per
call enforced by a thread future.

### 4.2 Provider migration

The project was originally built against Google Gemini. Obtaining an API key
failed on the available account: Google AI Studio returned *"Failed to create
project. The request is suspicious."* when auto-creating the backing Cloud
project, and creating a key manually through Google Cloud Console required
binding it to a service account — a different credential format that the
`google-genai` SDK does not consume in the same way.

Rather than work around a single vendor's provisioning, the LLM layer was made
provider-agnostic. The Gemini path remains in the codebase and is selected
automatically if a `GEMINI_API_KEY` is supplied; no code change is needed to
switch back. This turned a blocking external dependency into a configuration
choice, which is the more defensible engineering outcome.

### 4.3 Structured output contract

The client and counsellor agents must return
`{"speech", "emotion", "action"}`, where `emotion` is one of six values that
drive the 3D figures' expressions. Parsing degrades in three stages: parse the
response; on failure, retry once with a stricter instruction; on second
failure, treat the raw text as `speech` with `emotion: "neutral"`. The session
therefore never breaks because a model returned prose instead of JSON.

### 4.4 Safety mechanisms

- A disclaimer banner is pinned to every screen.
- All role prompts forbid describing any specific method of self-harm, in
  character and in case notes.
- The counsellor prompt instructs a gentle risk check and safety planning if
  the client raises self-harm — never a discussion of methods.
- Trainee input is screened by regex (`config.CRISIS_PATTERNS`) for
  first-person crisis language, distinct from in-character speech. On a match
  the session is paused and helplines are shown: 988 (US/CA), 116 123 (UK/IE),
  findahelpline.com, and Lehigh UCPS.
- The API key lives only in the backend `.env`; all model calls are
  server-side and the browser never receives it.

---

## 5. Testing and results

### 5.1 Automated tests

| Suite | Command | Result |
|---|---|---|
| Turn/attribution unit tests | `python tools/test_turnlogic.py` | **14 passed, 0 failed** |
| End-to-end smoke test (offline mock) | `python tools/smoke_test.py` | **61 passed, 0 failed** |
| Live API and model check | `python tools/check_key.py` | **3/3 models OK** |

`smoke_test.py` drives the full stack in memory using the mock LLM: register →
login → create patient → Mode A conversation → two mid-session role switches →
supervisor intervention → end session and summary → feedback report with
attribution → second session reading the prior summary → Mode B → Mode C score
comparison → crisis detection.

**Reproducibility was verified by cloning the published repository into a clean
directory and running the full suite there**, which is the procedure a grader
would follow. The clone produced the same 61/61 result and started the server
successfully.

### 5.2 Attribution behaviour (live sessions)

The attribution rule has three branches, and all three were observed in live
sessions (screenshots in `docs/screenshots/`):

| Situation | Report header | Screenshot |
|---|---|---|
| Trainee held the counsellor's chair throughout | *"Evaluating **your 6 turn(s)** as counsellor (turns 2, 4, 6, 8, 10, 12)"* | `01-feedback-mode-a-7of10.png` |
| Trainee switched seats mid-session | *"Evaluating your **3** turn(s)… The AI's **3** counsellor turn(s) were excluded."* | `06-attribution-mixed-turns.png` |
| Trainee never sat in the chair (Mode C) | *"You never sat in the counsellor's chair, so this evaluates the **AI counsellor's** 6 turn(s)."* | `09-feedback-mode-c-8of10.png` |

The middle case is the significant one: in a transcript with six counsellor
turns, three human and three machine, the report graded only the human three.

### 5.3 Supervisor intervention (live session)

In a Mode C session the LLM counsellor drifted into problem-solving from its
second turn — asking what would help the client "feel more in control", which
class to focus on, and what "small, doable step" to take that day — while the
client remained `anxious` and shrugged twice. No feeling had been reflected.

A supervisor note was written from the trainee's seat instructing the
counsellor to stop action-planning, reflect what lay underneath "trying to keep
up", and ask about the pressure rather than the schedule. The note was injected
into the counsellor's system prompt only.

The counsellor's next turn changed register completely:

> "I'm hearing that **underneath trying to keep up** there's a strong
> **pressure** you feel — to meet expectations, avoid letting your parents
> down, and not fall behind. How does that pressure feel for you right now…?"

It adopted the note's phrasing ("underneath trying to keep up", "pressure") and
replaced the action question with an emotion question. The same turn also
referenced the client's parents, who were **not mentioned anywhere in that
session** — that detail came from the previous session's summary, injected into
the counsellor's prompt. One response therefore demonstrated both supervisor
injection and cross-session memory.

Four turns later the counsellor drifted back toward action planning, which
suggests the effect of a single injected note decays over subsequent turns.

### 5.4 Cross-session memory (live session)

Session 1 produced a summary recording, among other things, *"I worry that
asking for help makes me look weak."* Opening session 2 with the same client,
her first response was:

> "…I've started skipping some study group sessions because I think I can
> handle it alone. I just keep worrying that if I ask for help, I'll look weak."

She resumed from the prior session's disclosures rather than restarting, and
retained her persona's deflect-with-humour speaking style across the session
boundary.

### 5.5 Supervisor score comparison (Mode C)

| Dimension | Trainee | AI supervisor | Difference |
|---|---|---|---|
| Cultural sensitivity | 4 | 8 | −4 |
| Therapeutic progress | 5 | 7 | −2 |
| Professional boundaries | 9 | 9 | 0 |
| Empathy | 5 | 8 | −3 |
| Conversational flow | 6 | 6 | 0 |
| | | **Mean absolute difference** | **1.8** |

The two scorers agreed exactly on boundaries and flow and diverged most on
cultural sensitivity. Inspecting the justifications shows this is a
**disagreement about definitions, not a scoring error**. The AI scored 8 because
the counsellor "avoids cultural assumptions… without stereotyping"; the trainee
scored 4 because the counsellor never engaged the client's cultural context at
all, treating parental expectation as generic academic pressure.

Whether cultural sensitivity means *not imposing* assumptions or *actively
exploring* context is a genuine question in counselling supervision. Surfacing
that question is arguably more useful to a trainee than agreement would be.

### 5.6 Error handling

| Failure | Behaviour |
|---|---|
| No API key | Falls back to offline mock; warning logged; `mock LLM` badge in UI |
| Invalid key / model not found | `LLMError` → HTTP 502 → toast; session stays open |
| API timeout | 30s cap → `LLMError` → 502; no hung request |
| Malformed JSON | One stricter retry, then degrade to raw text |
| `response_format` unsupported | Automatic retry without it |
| Empty input | Send disabled client-side; 422 server-side |
| Expired token | 401 → client clears token, returns to login |
| Turn raced | 409 → message queued, auto-sent when the turn arrives |

The missing-key path was verified by setting `FORCE_MOCK=1` and confirming
`config.USE_MOCK` became true; the invalid-key path was observed accidentally
during provider migration, when a Groq key placed in `GEMINI_API_KEY` produced
a clean 400 error and a UI toast rather than a crash.

---

## 6. Limitations

1. **Not clinically validated.** Scores come from a general-purpose LLM with no
   clinical training, validation, or inter-rater reliability. §5.5 shows two
   scorers disagreeing by 4 points on one dimension; treat numbers as
   discussion prompts, not assessment.
2. **Grading is non-deterministic.** The same transcript can score differently
   across runs. There is no rubric anchor or calibration set.
3. **Session summaries can leak undisclosed persona details.** The summariser
   receives the client's hidden-information list so it can record what *was*
   revealed, but it twice filed an *unrevealed* item ("crush on a classmate")
   under `unresolved_threads`. Since summaries are shown to the counsellor next
   session, this can pre-empt a disclosure the trainee was meant to earn. A
   prompt-level fix would constrain `unresolved_threads` to topics actually
   present in the transcript. Reproduced in two sessions; not fixed in this
   submission.
4. **Supervisor-note effect decays** (§5.3). A single note changes the next
   turn reliably but not subsequent ones.
5. **Crisis detection is regex-based and English-only.** It will miss indirect
   or non-English expressions. It is a safety net for an obvious case, not a
   screening instrument.
6. **Personas may be stereotyped or unrealistically cooperative.** They are
   LLM-generated fiction.
7. **Single-user sessions.** No concurrency control; two tabs on one session
   will race.
8. **Coursework-grade auth.** bcrypt + HMAC bearer tokens over plain HTTP on
   localhost; no HTTPS, rate limiting, or account lockout.
9. **No moderation layer** beyond prompt instructions.
10. **Free-tier model volatility.** Groq retires model ids periodically;
    `tools/check_key.py` exists because of this, and was needed once during
    development when the Llama family was withdrawn mid-project.

---

## 7. Conclusion

The system meets the lab requirement — a web application in which a user enters
a message, receives an LLM-generated response, and continues a multi-turn
conversation — and extends it in three directions that are specific to
counsellor training: three switchable roles, attribution-aware grading, and
memory that persists across sessions.

The two results worth highlighting are the ones that could not have been
predicted from the code alone. First, a supervisor note injected into one
agent's prompt measurably changed that agent's next turn while remaining
invisible to the other agent — structural information isolation working as
designed. Second, the human and AI supervisors diverged most on the dimension
where the term itself is contested, which suggests that the comparison feature's
value lies in surfacing disagreement rather than in producing a trustworthy
score.

The most significant known defect is the summary disclosure leak (§6.3), which
weakens the earned-disclosure mechanic that the simulated-client design depends
on. It is documented rather than fixed, and the fix is a prompt constraint
rather than a structural change.

---

## Appendix A — Running the system

```bash
git clone https://github.com/zhld25-lab/counselsim.git
cd counselsim
pip install -r requirements.txt
cp .env.example .env          # Windows: copy .env.example .env
# put a Groq key in GROQ_API_KEY (free: https://console.groq.com/keys)
python tools/check_key.py
python -m uvicorn backend.main:app --reload --port 8000
```

Open <http://127.0.0.1:8000>. With no key configured the application still runs
end-to-end on the offline mock LLM.

## Appendix B — Database schema

`users` · `patients` (persona JSON) · `sessions` · `messages`
(speaker / `controlled_by` / emotion) · `supervisor_notes` · `role_switches` ·
`session_summaries` · `feedback_reports`

The `controlled_by` column on `messages` is what makes attribution-aware
grading possible; `role_switches` records every seat change with the turn
number at which it occurred.
