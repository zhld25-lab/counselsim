# Lab 3b — Functional Screenshot Evidence

**Student:** Zhenzhe Luo  
**Course:** CSE 498  
**Project:** CounselSim — Counsellor Training Web-Based App

These screenshots show outputs from simulated counselling sessions. Scores are LLM-generated educational feedback and are **not clinically validated assessments**.

## Figure 1 — Mode A: counsellor feedback (7/10)

The supervisor grades six user-controlled counsellor turns over five dimensions.

![Figure 1: Mode A: counsellor feedback (7/10)](docs/screenshots/01-feedback-mode-a-7of10.png)

## Figure 2 — Mode A: qualitative assessment

Feedback details active listening, open-ended questioning, safety and ethics, and strengths.

![Figure 2: Mode A: qualitative assessment](docs/screenshots/02-feedback-strengths.png)

## Figure 3 — Mode A: suggested revisions

The system identifies exact turns, explains weaknesses, and proposes alternative responses. One suggestion concerns a safety check.

![Figure 3: Mode A: suggested revisions](docs/screenshots/03-feedback-improvements-safety-check.png)

## Figure 4 — Mixed-control: improvement advice

Turn-specific replacement suggestions target user counsellor responses in a mixed human/AI session.

![Figure 4: Mixed-control: improvement advice](docs/screenshots/04-feedback-improvements-alt.png)

## Figure 5 — Mixed-control: skills assessed

Evidence of reflective listening, question quality, and professional boundaries.

![Figure 5: Mixed-control: skills assessed](docs/screenshots/05-feedback-strengths-alt.png)

## Figure 6 — Mixed-control: attribution-aware grading (8/10)

The report explicitly grades the trainee's three counsellor turns and excludes three AI-generated counsellor turns.

![Figure 6: Mixed-control: attribution-aware grading (8/10)](docs/screenshots/06-attribution-mixed-turns.png)

## Figure 7 — Session 1: structured summary

Case note includes concerns, disclosure, mood progression, coping, follow-up steps, and open threads.

![Figure 7: Session 1: structured summary](docs/screenshots/07-session-summary-s1.png)

## Figure 8 — Session 2: later summary

A second summary records later concerns and action plans; screenshots alone do not prove that old summaries were retrieved into future prompts.

![Figure 8: Session 2: later summary](docs/screenshots/08-session-summary-s2.png)

## Figure 9 — Mode C: AI counsellor feedback (8/10)

Since the trainee was never the counsellor, evaluation covers six AI counsellor turns.

![Figure 9: Mode C: AI counsellor feedback (8/10)](docs/screenshots/09-feedback-mode-c-8of10.png)

## Figure 10 — Mode C: assessed skills

Qualitative comments address listening, open questions, and safety/ethics.

![Figure 10: Mode C: assessed skills](docs/screenshots/10-feedback-mode-c-assessed.png)

## Figure 11 — Mode C: improvement advice

Specific AI counsellor turns are flagged for verbosity or leading prompts, with revised examples.

![Figure 11: Mode C: improvement advice](docs/screenshots/11-feedback-mode-c-improvements.png)

## Figure 12 — Mode C: human vs AI supervisor scores

User and AI supervisor scores are compared on five dimensions; reported mean absolute difference is 1.8.

![Figure 12: Mode C: human vs AI supervisor scores](docs/screenshots/12-scores-vs-ai-supervisor.png)

## Interpretation and limitations

- **Attribution matters:** Mode A assesses six trainee counsellor turns; mixed-control evaluation omits three AI turns and scores three trainee turns; Mode C evaluates six AI counsellor turns because the trainee did not occupy that role.
- **Scoring disagreement is not ground truth:** In Mode C, a human–AI mean absolute difference of 1.8 indicates disagreement among raters, not validated scoring accuracy.
- **Memory claims need care:** The saved summaries demonstrate generation of structured notes; proving retrieval requires session replay or code-level verification.
- **Hidden-information leakage:** An undisclosed topic appearing under `Open threads` may expose a persona secret prematurely, which is an important limitation.

See [README.md](README.md) for implementation details and setup instructions.
