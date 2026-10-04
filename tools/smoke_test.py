"""End-to-end check of every acceptance item, using the offline mock LLM.

    python tools/smoke_test.py

It spins the app up in-process against a throwaway SQLite file, runs all three
modes, switches roles twice mid-session, and asserts the summary + feedback
behave as specified. No API key and no network needed.
"""
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
os.environ["FORCE_MOCK"] = "1"
os.environ["DB_PATH"] = str(pathlib.Path(tempfile.gettempdir()) / "counselsim_smoke.db")
if os.path.exists(os.environ["DB_PATH"]):
    os.remove(os.environ["DB_PATH"])
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402

client = TestClient(app)
PASS, FAIL = [], []


def check(name, condition, detail=""):
    (PASS if condition else FAIL).append(name)
    print(("  PASS  " if condition else "  FAIL  ") + name + (f"   {detail}" if detail and not condition else ""))


def auth_header(token):
    return {"Authorization": "Bearer " + token}


with client:
    print("\n1. auth")
    r = client.post("/api/auth/register", json={"username": "trainee", "password": "pw123456"})
    check("register returns a token", r.status_code == 200 and r.json().get("token"), r.text)
    token = r.json()["token"]
    H = auth_header(token)
    check("duplicate username rejected",
          client.post("/api/auth/register", json={"username": "trainee", "password": "pw123456"}).status_code == 400)
    check("wrong password rejected",
          client.post("/api/auth/login", json={"username": "trainee", "password": "nope123"}).status_code == 401)
    check("login works",
          client.post("/api/auth/login", json={"username": "trainee", "password": "pw123456"}).status_code == 200)
    check("protected route needs auth", client.get("/api/patients").status_code == 401)

    print("\n2. patient creation")
    r = client.post("/api/patients", headers=H, json={
        "gender": "female", "age_group": "18-24", "ethnicity": "East Asian",
        "concerns": ["anxiety", "academic performance", "cultural adjustment"],
    })
    check("patient created", r.status_code == 200, r.text)
    patient = r.json()
    pid = patient["id"]
    check("persona has a fake name and age", bool(patient["name"]) and patient["age"] > 0)
    check("hidden info is not exposed to the counsellor", "secrets" not in patient)

    print("\n3. MODE A - user is the counsellor")
    r = client.post("/api/sessions", headers=H, json={"patient_id": pid, "user_role": "counselor"})
    s = r.json()
    sid = s["session_id"]
    check("session starts with the client due to speak", s["next_speaker"] == "client")
    check("and that turn belongs to the LLM", s["next_controlled_by"] == "llm")

    s = client.post(f"/api/sessions/{sid}/step", headers=H).json()["state"]
    check("client opened the session", s["transcript"][0]["speaker"] == "client")
    check("client turn is tagged llm", s["transcript"][0]["controlled_by"] == "llm")
    check("emotion is on the message (drives the face)", s["transcript"][0]["emotion"])
    check("now it is the user's turn", s["next_controlled_by"] == "user")

    out = client.post(f"/api/sessions/{sid}/say", headers=H,
                      json={"text": "Thank you for coming in. What's been hardest this week?",
                            "emotion": "neutral"}).json()
    check("user turn tagged user", out["message"]["controlled_by"] == "user")
    s = client.post(f"/api/sessions/{sid}/step", headers=H).json()["state"]
    out = client.post(f"/api/sessions/{sid}/say", headers=H,
                      json={"text": "It sounds like you've been carrying a lot alone.",
                            "emotion": "neutral"}).json()
    check("supervisor whisper appears automatically", out["new_note"] is not None or
          len(out["state"]["supervisor_notes"]) > 0)
    s = client.post(f"/api/sessions/{sid}/step", headers=H).json()["state"]

    tip = client.post(f"/api/sessions/{sid}/supervisor-tip", headers=H)
    check("Ask Supervisor works on demand", tip.status_code == 200 and tip.json()["note"]["note"])

    print("\n4. role switching mid-session")
    before = len(s["transcript"])
    s = client.post(f"/api/sessions/{sid}/role", headers=H, json={"role": "client"}).json()
    check("switched to client", s["user_role"] == "client")
    check("switch recorded in role_history",
          any(h["from_role"] == "counselor" and h["to_role"] == "client" for h in s["role_history"]))
    check("client role card is revealed to the user now", "role_card" in s)
    check("the client can no longer see supervisor notes", s["supervisor_notes"] == [])

    # the counsellor chair is now empty -> the LLM must pick it up
    if s["next_speaker"] == "counselor":
        s = client.post(f"/api/sessions/{sid}/step", headers=H).json()["state"]
        check("LLM took over the counsellor chair", s["transcript"][-1]["speaker"] == "counselor"
              and s["transcript"][-1]["controlled_by"] == "llm")
    out = client.post(f"/api/sessions/{sid}/say", headers=H,
                      json={"text": "I keep telling everyone I'm fine.", "emotion": "sad"}).json()
    check("user now speaks as the client", out["message"]["speaker"] == "client"
          and out["message"]["controlled_by"] == "user")
    check("transcript kept growing across the switch", len(out["state"]["transcript"]) > before)

    s = client.post(f"/api/sessions/{sid}/role", headers=H, json={"role": "supervisor"}).json()
    check("second switch recorded", len([h for h in s["role_history"] if h["from_role"]]) >= 2)
    if s["next_controlled_by"] == "llm":
        s = client.post(f"/api/sessions/{sid}/step", headers=H).json()["state"]
    note = client.post(f"/api/sessions/{sid}/intervene", headers=H,
                       json={"note": "Slow down - reflect the loneliness before your next question."})
    check("supervisor intervention accepted", note.status_code == 200)
    s = client.post(f"/api/sessions/{sid}/step", headers=H).json()
    check("the counsellor consumed the supervisor note",
          s.get("followed_note_id") is not None or s["state"]["transcript"][-1]["speaker"] == "client")

    print("\n5. end of session + summary")
    end = client.post(f"/api/sessions/{sid}/end", headers=H).json()
    summary = end["summary"]
    for key in ["presenting_issues_discussed", "key_facts_disclosed", "emotional_state_start",
                "emotional_state_end", "risk_indicators", "coping_strategies_mentioned",
                "goals_or_homework_agreed", "therapeutic_alliance", "unresolved_threads",
                "hidden_info_revealed"]:
        check(f"summary has {key}", key in summary)
    check("session marked ended", end["state"]["status"] == "ended")

    print("\n6. feedback report")
    fb = client.post(f"/api/sessions/{sid}/feedback", headers=H).json()
    rep = fb["report"]
    check("evaluates the user (they held the counsellor chair)", fb["evaluated_party"] == "user")
    for dim in ["cultural_sensitivity", "therapeutic_progress", "professional_boundaries",
                "empathy", "conversational_flow"]:
        check(f"scored {dim}", dim in rep["scores"] and 1 <= rep["scores"][dim]["score"] <= 10)
    check("overall score present", 1 <= rep["overall_score"] <= 10)
    check("3 strengths", len(rep["strengths"]) == 3)
    check("3 improvements with alternatives",
          len(rep["improvements"]) == 3 and all("alternative" in i for i in rep["improvements"]))
    att = rep["attribution"]
    check("user turns and llm turns separated",
          set(att["counselor_turns_by_user"]).isdisjoint(att["counselor_turns_by_llm"]))

    print("\n7. memory - a second session with the same patient")
    d = client.get(f"/api/patients/{pid}", headers=H).json()
    check("patient page shows the last summary", d["last_summary"] is not None)
    s2 = client.post("/api/sessions", headers=H, json={"patient_id": pid, "user_role": "counselor"}).json()
    check("session number increments", s2["session_number"] == 2)
    check("prior summary is loaded into the new session", s2["prior_summary"] is not None)

    print("\n8. MODE B - user is the client")
    s3 = client.post("/api/sessions", headers=H, json={"patient_id": pid, "user_role": "client"}).json()
    sid3 = s3["session_id"]
    check("user opens as the client", s3["next_controlled_by"] == "user")
    check("full character card provided", "role_card" in s3 and s3["role_card"]["secrets"])
    out = client.post(f"/api/sessions/{sid3}/say", headers=H,
                      json={"text": "I didn't really want to come.", "emotion": "anxious"}).json()
    s3 = client.post(f"/api/sessions/{sid3}/step", headers=H).json()["state"]
    check("LLM counsellor replied", s3["transcript"][-1]["speaker"] == "counselor")
    fb3 = client.post(f"/api/sessions/{sid3}/feedback", headers=H).json()
    check("with no user counsellor turns, the LLM counsellor is evaluated",
          fb3["evaluated_party"] == "llm")

    print("\n9. MODE C - user is the supervisor")
    s4 = client.post("/api/sessions", headers=H, json={"patient_id": pid, "user_role": "supervisor"}).json()
    sid4 = s4["session_id"]
    for _ in range(4):
        s4 = client.post(f"/api/sessions/{sid4}/step", headers=H).json()["state"]
    check("client and counsellor both played by the LLM",
          all(m["controlled_by"] == "llm" for m in s4["transcript"]))
    check("supervisor cannot speak in the room",
          client.post(f"/api/sessions/{sid4}/say", headers=H,
                      json={"text": "hello", "emotion": "neutral"}).status_code == 400)
    cmp = client.post(f"/api/sessions/{sid4}/my-scores", headers=H, json={
        "scores": {"cultural_sensitivity": 8, "therapeutic_progress": 5,
                   "professional_boundaries": 9, "empathy": 7, "conversational_flow": 6},
        "comment": "Good warmth, thin on culture follow-up.",
    }).json()
    check("comparison table returned", len(cmp["comparison"]) == 5)
    check("mean absolute difference computed", "mean_absolute_difference" in cmp)

    print("\n10. safety")
    s5 = client.post("/api/sessions", headers=H, json={"patient_id": pid, "user_role": "counselor"}).json()
    sid5 = s5["session_id"]
    client.post(f"/api/sessions/{sid5}/step", headers=H)
    crisis = client.post(f"/api/sessions/{sid5}/say", headers=H,
                         json={"text": "honestly i want to kill myself", "emotion": "sad"}).json()
    check("user-in-crisis pauses the simulation and offers resources",
          crisis.get("crisis") is True and crisis["state"]["status"] == "paused")
    check("banner text present", client.get("/api/meta").json()["banner"].startswith("Training simulation only"))

print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("failed:", ", ".join(FAIL))
    sys.exit(1)
