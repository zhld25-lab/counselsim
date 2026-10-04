/* ui.js — screens, session loop, role switching, feedback. */
(() => {
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));

  const ROLE_LABEL = { client: "Client", counselor: "Counsellor", supervisor: "Supervisor" };
  const MODE_LABEL = {
    counselor: "Mode A · you are the counsellor",
    client: "Mode B · you are the client",
    supervisor: "Mode C · you are the supervisor",
  };

  let meta = { emotions: ["neutral"], autoplay_delay_seconds: 3 };
  let options = null;
  let state = null;              // current session state from the server
  let autoplay = false;
  let busy = false;
  let queued = null;             // what you typed while the AI was still replying
  let renderedUpTo = 0;          // turns already animated in the 3D scene
  let selectedRole = "counselor";
  let selectedConcerns = new Set();

  /* ---------------- helpers ---------------- */
  function showScreen(name) {
    $$(".screen").forEach((s) => s.classList.remove("active"));
    $("#screen-" + name).classList.add("active");
    if (name === "session") setTimeout(() => Scene.resize(), 50);
  }
  function toast(msg, ms) {
    const t = $("#toast");
    t.textContent = msg;
    t.classList.remove("hidden");
    clearTimeout(t._h);
    t._h = setTimeout(() => t.classList.add("hidden"), ms || 2600);
  }
  function openModal(html) {
    $("#modal-body").innerHTML = html;
    $("#modal").classList.remove("hidden");
  }
  function closeModal() { $("#modal").classList.add("hidden"); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }
  function list(arr) {
    if (!arr || !arr.length) return '<span class="muted">—</span>';
    return "<ul>" + arr.map((x) => "<li>" + esc(x) + "</li>").join("") + "</ul>";
  }
  function handle(err) {
    console.error(err);
    if (err && err.status === 401) { logout(); return; }
    toast((err && err.message) || "Something went wrong", 4200);
  }

  /* ---------------- auth ---------------- */
  let authMode = "login";
  $$("[data-authtab]").forEach((b) => b.addEventListener("click", () => {
    authMode = b.dataset.authtab;
    $$("[data-authtab]").forEach((x) => x.classList.toggle("active", x === b));
    $("#auth-submit").textContent = authMode === "login" ? "Login" : "Create account";
    $("#auth-error").textContent = "";
  }));

  $("#auth-submit").addEventListener("click", async () => {
    const u = $("#auth-username").value.trim();
    const p = $("#auth-password").value;
    $("#auth-error").textContent = "";
    if (u.length < 3 || p.length < 6) {
      $("#auth-error").textContent = "Username needs 3+ characters, password 6+.";
      return;
    }
    try {
      const out = authMode === "login" ? await API.login(u, p) : await API.register(u, p);
      API.setToken(out.token);
      await enterApp(out.username);
    } catch (e) { $("#auth-error").textContent = e.message; }
  });
  $("#auth-password").addEventListener("keydown", (e) => {
    if (e.key === "Enter") $("#auth-submit").click();
  });

  function logout() {
    API.setToken("");
    state = null; autoplay = false;
    showScreen("auth");
  }
  $("#logout").addEventListener("click", logout);

  async function enterApp(username) {
    $("#home-user").textContent = "signed in as " + username;
    if (!options) options = await API.options();
    fillForm();
    showScreen("home");
  }

  /* ---------------- home ---------------- */
  $("#go-real").addEventListener("click", () => showScreen("real"));
  $("#go-sim").addEventListener("click", async () => {
    showScreen("patients");
    loadPatients();
  });
  $$("[data-back]").forEach((b) => b.addEventListener("click", () => {
    autoplay = false;
    showScreen(b.dataset.back);
    if (b.dataset.back === "patients") loadPatients();
  }));

  /* ---------------- patient form ---------------- */
  function fillForm() {
    const fill = (sel, arr) => {
      $(sel).innerHTML = arr.map((v) => `<option>${esc(v)}</option>`).join("");
    };
    fill("#f-gender", options.genders);
    fill("#f-age", options.age_groups);
    fill("#f-ethnicity", options.ethnicities);
    $("#f-concerns").innerHTML = options.concerns
      .map((c) => `<button class="chip" data-concern="${esc(c)}">${esc(c)}</button>`).join("");
    $$("[data-concern]").forEach((b) => b.addEventListener("click", () => {
      const c = b.dataset.concern;
      if (selectedConcerns.has(c)) selectedConcerns.delete(c); else selectedConcerns.add(c);
      b.classList.toggle("on");
    }));
    $$(".role-opt").forEach((b) => b.addEventListener("click", () => {
      selectedRole = b.dataset.role;
      $$(".role-opt").forEach((x) => x.classList.toggle("selected", x === b));
    }));
  }

  $$("[data-ptab]").forEach((b) => b.addEventListener("click", () => {
    $$("[data-ptab]").forEach((x) => x.classList.toggle("active", x === b));
    $$(".ptab").forEach((p) => p.classList.remove("active"));
    $("#ptab-" + b.dataset.ptab).classList.add("active");
    if (b.dataset.ptab === "existing") loadPatients();
  }));

  $("#create-patient").addEventListener("click", async () => {
    const btn = $("#create-patient");
    $("#create-error").textContent = "";
    if (!selectedConcerns.size) {
      $("#create-error").textContent = "Pick at least one concern.";
      return;
    }
    btn.disabled = true; btn.textContent = "Generating persona…";
    try {
      const p = await API.createPatient({
        gender: $("#f-gender").value,
        age_group: $("#f-age").value,
        ethnicity: $("#f-ethnicity").value,
        concerns: Array.from(selectedConcerns),
      });
      await beginSession(p.id, selectedRole);
    } catch (e) { $("#create-error").textContent = e.message; }
    finally { btn.disabled = false; btn.textContent = "Create patient & start session"; }
  });

  async function loadPatients() {
    try {
      const ps = await API.listPatients();
      $("#patient-list").innerHTML = ps.length ? ps.map((p) => `
        <div class="p-card" data-pid="${p.id}">
          <h4>${esc(p.name)}</h4>
          <div class="muted tiny">${esc(p.age)} · ${esc(p.gender)} · ${esc(p.ethnicity)}</div>
          <div class="p-tags">${(p.concerns || []).map((c) => `<span>${esc(c)}</span>`).join("")}</div>
          <div class="muted tiny" style="margin-top:8px">${p.session_count} session(s)${p.has_summary ? " · has notes" : ""}</div>
        </div>`).join("")
        : '<p class="muted">No simulated patients yet — create one on the other tab.</p>';
      $$("[data-pid]").forEach((el) => el.addEventListener("click", () => openPatient(+el.dataset.pid)));
    } catch (e) { handle(e); }
  }

  async function openPatient(pid) {
    try {
      const d = await API.getPatient(pid);
      const s = d.last_summary;
      openModal(`
        <h2>${esc(d.patient.name)}</h2>
        <p class="muted">${esc(d.patient.age)} · ${esc(d.patient.gender)} · ${esc(d.patient.ethnicity)} · ${esc(d.patient.occupation || "")}</p>
        <p>${esc(d.patient.intake_info)}</p>
        <h3 style="margin-top:18px">Last session summary</h3>
        ${s ? summaryHtml(s) : '<p class="muted">No previous session yet.</p>'}
        <h3 style="margin-top:18px">Start session ${(d.last_session_number || 0) + 1} as…</h3>
        <div class="role-picker" id="modal-roles">
          <button class="role-opt selected" data-mrole="counselor"><b>Counsellor</b><span>Mode A</span></button>
          <button class="role-opt" data-mrole="client"><b>Client</b><span>Mode B</span></button>
          <button class="role-opt" data-mrole="supervisor"><b>Supervisor</b><span>Mode C</span></button>
        </div>
        <button class="btn primary" id="modal-start" style="margin-top:16px">Start session</button>
      `);
      let role = "counselor";
      $$("[data-mrole]").forEach((b) => b.addEventListener("click", () => {
        role = b.dataset.mrole;
        $$("[data-mrole]").forEach((x) => x.classList.toggle("selected", x === b));
      }));
      $("#modal-start").addEventListener("click", () => { closeModal(); beginSession(pid, role); });
    } catch (e) { handle(e); }
  }

  function summaryHtml(s) {
    return `
      <div class="kv">
        <p><b>Issues discussed:</b></p>${list(s.presenting_issues_discussed)}
        <p><b>Disclosed:</b></p>${list(s.key_facts_disclosed)}
        <p><b>Mood:</b> ${esc(s.emotional_state_start)} → ${esc(s.emotional_state_end)} &nbsp;
           <b>Alliance:</b> ${esc(s.therapeutic_alliance)}</p>
        <p><b>Risk indicators:</b></p>${list(s.risk_indicators)}
        <p><b>Coping mentioned:</b></p>${list(s.coping_strategies_mentioned)}
        <p><b>Agreed next steps:</b></p>${list(s.goals_or_homework_agreed)}
        <p><b>Open threads:</b></p>${list(s.unresolved_threads)}
        <p><b>Hidden info revealed:</b></p>${list(s.hidden_info_revealed)}
      </div>`;
  }

  /* ---------------- session ---------------- */
  async function beginSession(patientId, role) {
    try {
      autoplay = false;
      renderedUpTo = 0;
      queued = null;
      $("#say-input").value = "";
      state = await API.startSession(patientId, role);
      Scene.clearBubbles();
      showScreen("session");
      Scene.setYou(state.user_role, true);
      render();
      if (state.prior_summary) {
        toast("This client remembers your last session — see Previous notes in the sidebar.", 4200);
      }
      maybeAdvance();
    } catch (e) { handle(e); }
  }

  function render() {
    if (!state) return;
    const p = state.patient_card;
    $("#s-title").textContent = `${p.name} · session ${state.session_number}`;
    $("#s-mode").textContent = MODE_LABEL[state.user_role];
    $("#s-mock").classList.toggle("hidden", !state.mock_mode);
    $("#btn-tip").classList.toggle("hidden", state.user_role === "client");

    // sidebar: patient card
    $("#card-patient").innerHTML = `
      <h4>Client file</h4>
      <dl>
        <dt>Name</dt><dd>${esc(p.name)}</dd>
        <dt>Age</dt><dd>${esc(p.age)}</dd>
        <dt>Gender</dt><dd>${esc(p.gender)}</dd>
        <dt>Background</dt><dd>${esc(p.ethnicity)}</dd>
      </dl>
      <p class="tiny" style="margin:.6em 0 0">${esc(p.intake_info)}</p>
      <div class="p-tags">${(p.concerns || []).map((c) => `<span>${esc(c)}</span>`).join("")}</div>`;

    $$(".rs").forEach((b) => b.classList.toggle("on", b.dataset.switch === state.user_role));

    // mode B: the user needs their own character card
    $("#card-rolecard").innerHTML = state.role_card ? `
      <h4>Your character card</h4>
      <p class="tiny"><b>Style:</b> ${esc(state.role_card.style)}</p>
      <p class="tiny"><b>Background:</b> ${esc(state.role_card.background)}</p>
      <p class="tiny"><b>Culture:</b> ${esc(state.role_card.cultural_notes)}</p>
      <p class="tiny"><b>Things you don't say at first:</b></p>
      <div class="tiny">${list(state.role_card.secrets)}</div>
      <p class="tiny muted">Suggested opening: “${esc(state.role_card.opening_line)}”</p>` : "";

    $("#card-summary").innerHTML = state.prior_summary
      ? `<h4>Previous session notes</h4><div class="tiny">${summaryHtml(state.prior_summary)}</div>` : "";

    const notes = state.supervisor_notes || [];
    $("#card-notes").innerHTML = notes.length ? `<h4>Supervisor notes</h4>` + notes.slice(-6).map((n) =>
      `<p class="tiny" style="border-left:3px solid var(--warm);padding-left:8px;margin:.5em 0">
         ${esc(n.note)}<br><span class="muted">after turn ${n.after_turn} · ${esc(n.focus_skill)} · ${n.author === "user" ? "you" : "AI supervisor"}</span>
       </p>`).join("") : "";

    const hist = (state.role_history || []).filter((h) => h.from_role);
    $("#card-history").innerHTML = hist.length ? `<h4>Role history</h4>` + hist.map((h) =>
      `<p class="tiny">turn ${h.turn}: ${ROLE_LABEL[h.from_role]} → ${ROLE_LABEL[h.to_role]}</p>`).join("") : "";

    renderTranscript();
    renderControls();
    Scene.setYou(state.user_role);
  }

  const AVATAR = { client: "CLI", counselor: "CNS", supervisor: "SUP" };

  function renderTranscript() {
    const items = [];
    (state.transcript || []).forEach((m) => items.push({ k: "msg", turn: m.turn, m }));
    (state.supervisor_notes || []).forEach((n) => items.push({ k: "note", turn: n.after_turn + 0.4, n }));
    (state.role_history || []).filter((h) => h.from_role)
      .forEach((h) => items.push({ k: "switch", turn: h.turn + 0.6, h }));
    items.sort((a, b) => a.turn - b.turn);

    const el = $("#transcript");
    let html = items.map((it) => {
      if (it.k === "msg") {
        const m = it.m;
        const mine = m.controlled_by === "user";
        return `<div class="msg ${m.speaker} ${mine ? "right" : ""}">
          <div class="avatar ${m.speaker}">${AVATAR[m.speaker]}</div>
          <div class="balloon">
            <div class="meta"><b>${ROLE_LABEL[m.speaker]}</b>
              <span>${mine ? "you" : "AI"} · ${esc(m.emotion)} · turn ${m.turn}</span></div>
            ${esc(m.text)}
            ${m.action ? `<span class="act">— ${esc(m.action)}</span>` : ""}
          </div></div>`;
      }
      if (it.k === "note") {
        return `<div class="chat-note">🗒️ ${esc(it.n.note)}
          <span>${it.n.author === "user" ? "your intervention" : "supervisor whisper"} · the client never sees this</span></div>`;
      }
      return `<div class="chat-switch">you took over as ${ROLE_LABEL[it.h.to_role]}</div>`;
    }).join("");

    if (queued) {
      html += `<div class="msg ${state.user_role} right pendingmsg">
        <div class="avatar ${state.user_role}">${AVATAR[state.user_role]}</div>
        <div class="balloon"><div class="meta"><b>${ROLE_LABEL[state.user_role]}</b>
          <span>queued — sends when it's your turn</span></div>${esc(queued.text)}</div></div>`;
    }
    if (busy && state.status !== "ended") {
      html += `<div class="typing">${ROLE_LABEL[state.next_speaker]} is typing…</div>`;
    }
    el.innerHTML = html;
    el.scrollTop = el.scrollHeight;
  }

  function renderControls() {
    const isSupervisor = state.user_role === "supervisor";
    const ended = state.status === "ended";
    $("#autoplay-bar").classList.toggle("hidden", !isSupervisor);
    $("#emotion-pick").classList.toggle("hidden", isSupervisor);

    if ($("#emotion-pick").options.length === 0) {
      $("#emotion-pick").innerHTML = meta.emotions.map((e) => `<option>${e}</option>`).join("");
    }

    // The box is always typable — nothing you write is ever thrown away.
    $("#say-input").disabled = ended;
    $("#btn-say").disabled = ended;
    $("#say-input").placeholder = isSupervisor
      ? "Write a note the counsellor must follow next turn…"
      : "Type what you say…";
    $("#btn-say").textContent = isSupervisor ? "Send note" : "Send";

    const yourTurn = state.next_controlled_by === "user" && !ended;
    $("#turn-hint").textContent = ended
      ? "This session has ended. Open Feedback, or leave to start a new one."
      : isSupervisor
        ? "You're behind the glass. Type a note any time — the counsellor uses it on their next turn."
        : yourTurn
          ? `Your turn as ${ROLE_LABEL[state.user_role]}.`
          : `The AI ${ROLE_LABEL[state.next_speaker]} is replying — keep typing, your message sends next.`;

    $("#queued").classList.toggle("hidden", !queued);
    if (queued) {
      $("#queued").innerHTML = `Queued: “${esc(queued.text.slice(0, 60))}${queued.text.length > 60 ? "…" : ""}”
        <button id="unqueue">cancel</button>`;
      $("#unqueue").addEventListener("click", () => {
        $("#say-input").value = queued.text;
        queued = null; renderControls(); renderTranscript();
      });
    }

    $("#btn-play").textContent = autoplay ? "⏸ Pause" : "▶ Auto-play";
    $("#btn-stepone").disabled = busy || ended;
    $("#autoplay-status").textContent = ended
      ? "session ended"
      : autoplay ? `auto · one turn every ${meta.autoplay_delay_seconds}s` : "manual — click Next turn";
  }

  async function animateNew() {
    const msgs = (state.transcript || []).filter((m) => m.turn > renderedUpTo);
    for (const m of msgs) {
      renderedUpTo = m.turn;
      Scene.setExpression(m.speaker, m.emotion);
      await Scene.speak(m.speaker, m.text, m.emotion);
    }
  }

  function showWhisper(note) {
    const el = $("#whisper");
    if (!note || state.user_role === "client") { el.classList.add("hidden"); return; }
    el.innerHTML = `<b>${note.author === "user" ? "your note" : "supervisor whisper"}</b>${esc(note.note)}`;
    el.classList.remove("hidden");
    clearTimeout(el._h);
    el._h = setTimeout(() => el.classList.add("hidden"), 12000);
  }

  function crisis(data) {
    autoplay = false;
    openModal(`<h2>Let's pause the simulation</h2>
      <p>${esc(data.message)}</p>
      <ul>${data.resources.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
      <p class="muted tiny">If this was in-character dialogue, you can close this and rephrase.</p>`);
    state = data.state;
    render();
  }

  /* ---- turn loop ---- */
  async function doStep() {
    if (busy || !state || state.status === "ended") return false;
    busy = true; renderControls(); renderTranscript();
    Scene.showThinking(state.next_speaker, true);
    try {
      const out = await API.step(state.session_id);
      Scene.showThinking(out.message.speaker, false);
      state = out.state;
      render();
      await animateNew();
      if (out.new_note) { showWhisper(out.new_note); render(); }
      return true;
    } catch (e) {
      Scene.clearBubbles();
      if (e.status !== 409) handle(e);
      return false;
    } finally { busy = false; renderControls(); renderTranscript(); }
  }

  async function maybeAdvance() {
    if (!state || state.status === "ended") return;
    if (state.next_controlled_by !== "llm") { await flushQueue(); return; }
    // Mode C never runs on its own unless you switch auto-play on.
    if (state.user_role === "supervisor" && !autoplay) return;
    const ok = await doStep();
    if (!ok) return;
    if (state.user_role === "supervisor" && autoplay) {
      setTimeout(() => { if (autoplay) maybeAdvance(); }, meta.autoplay_delay_seconds * 1000);
    } else {
      maybeAdvance();
    }
  }

  async function actuallySay(text, emotion) {
    busy = true; renderControls(); renderTranscript();
    try {
      const out = await API.say(state.session_id, text, emotion);
      if (out.crisis) { busy = false; crisis(out); return; }
      state = out.state;
      render();
      await animateNew();
      if (out.new_note) { showWhisper(out.new_note); render(); }
    } catch (e) {
      if (e.status === 409) { queued = { text, emotion }; }   // turn moved under us
      else handle(e);
    } finally { busy = false; renderControls(); }
    maybeAdvance();
  }

  async function sendNote(text) {
    try {
      const out = await API.intervene(state.session_id, text);
      if (out.crisis) { crisis(out); return; }
      state = out.state; render(); showWhisper(out.note);
      toast("Sent — the counsellor uses it on their next turn.");
    } catch (e) { handle(e); }
  }

  /** The composer never blocks: if it isn't your turn yet, the message waits. */
  async function submitComposer() {
    if (!state || state.status === "ended") return;
    const text = $("#say-input").value.trim();
    if (!text) return;
    $("#say-input").value = "";

    if (state.user_role === "supervisor") { await sendNote(text); return; }

    const emotion = $("#emotion-pick").value;
    if (busy || state.next_controlled_by !== "user") {
      queued = { text, emotion };
      renderControls(); renderTranscript();
      return;
    }
    await actuallySay(text, emotion);
  }

  async function flushQueue() {
    if (!queued || busy || !state || state.status === "ended") return;
    if (state.user_role === "supervisor") return;
    if (state.next_controlled_by !== "user") return;
    const q = queued;
    queued = null;
    await actuallySay(q.text, q.emotion);
  }

  $("#btn-say").addEventListener("click", submitComposer);
  $("#say-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submitComposer(); }
  });

  $("#btn-play").addEventListener("click", () => {
    autoplay = !autoplay;
    renderControls();
    if (autoplay) maybeAdvance();
  });
  $("#btn-stepone").addEventListener("click", async () => { await doStep(); });

  $("#btn-tip").addEventListener("click", async () => {
    if (!state) return;
    try {
      const out = await API.askSupervisor(state.session_id);
      state = out.state; render(); showWhisper(out.note);
    } catch (e) { handle(e); }
  });

  /* ---- role switching ---- */
  $$(".rs").forEach((b) => b.addEventListener("click", async () => {
    if (!state || busy) { toast("Hold on — a turn is being generated."); return; }
    const role = b.dataset.switch;
    if (role === state.user_role) return;
    try {
      if (queued) { $("#say-input").value = queued.text; queued = null; }  // it was for the old chair
      state = await API.switchRole(state.session_id, role);
      autoplay = false;
      Scene.setYou(state.user_role);       // 0.5s flight animation
      render();
      toast(`You are now the ${ROLE_LABEL[role]}.`);
      maybeAdvance();                      // nobody left holding the old chair? LLM picks it up
    } catch (e) { handle(e); }
  }));

  /* ---- end + feedback ---- */
  $("#btn-end").addEventListener("click", async () => {
    if (!state) return;
    if (state.status === "ended") { toast("Already ended."); return; }
    autoplay = false;
    const btn = $("#btn-end");
    btn.disabled = true; btn.textContent = "Summarising…";
    try {
      const out = await API.endSession(state.session_id);
      state = out.state; render();
      openModal(`<h2>Session summary</h2>${summaryHtml(out.summary)}
        <p class="muted tiny">Saved — this is what the client (and the counsellor) will remember next time.</p>`);
    } catch (e) { handle(e); }
    finally { btn.disabled = false; btn.textContent = "End session"; }
  });

  $("#btn-feedback").addEventListener("click", async () => {
    if (!state) return;
    autoplay = false;
    const btn = $("#btn-feedback");
    btn.disabled = true; btn.textContent = "Evaluating…";
    try {
      const out = await API.feedback(state.session_id);
      if (state.user_role === "supervisor" && !out.user_scores) showRatingForm(out);
      else showReport(out, null);
    } catch (e) { handle(e); }
    finally { btn.disabled = false; btn.textContent = "Feedback"; }
  });

  const DIMS = ["cultural_sensitivity", "therapeutic_progress", "professional_boundaries", "empathy", "conversational_flow"];
  const nice = (d) => d.replace(/_/g, " ");

  function showRatingForm(out) {
    openModal(`<h2>Your turn to supervise</h2>
      <p class="muted">You watched the session. Score the counsellor first — then you'll see the AI supervisor's scores next to yours.</p>
      ${DIMS.map((d) => `<div class="rate-row">
          <label>${nice(d)}</label>
          <input type="range" min="1" max="10" value="6" data-dim="${d}">
          <span class="score-num" data-out="${d}">6</span>
        </div>`).join("")}
      <textarea id="my-comment" rows="2" placeholder="Optional note to the counsellor" style="width:100%;margin-top:10px;padding:.6em;border-radius:10px;border:1px solid var(--line);background:#191322;color:var(--ink)"></textarea>
      <button class="btn primary" id="my-send" style="margin-top:14px">Submit &amp; compare</button>`);
    $$("[data-dim]").forEach((r) => r.addEventListener("input", () => {
      $(`[data-out="${r.dataset.dim}"]`).textContent = r.value;
    }));
    $("#my-send").addEventListener("click", async () => {
      const scores = {};
      $$("[data-dim]").forEach((r) => { scores[r.dataset.dim] = +r.value; });
      try {
        const res = await API.myScores(state.session_id, scores, $("#my-comment").value);
        showReport(res, res.comparison);
      } catch (e) { handle(e); }
    });
  }

  function showReport(out, comparison) {
    const r = out.report;
    const att = r.attribution || {};
    const partyLine = out.evaluated_party === "user"
      ? `Evaluating <b>your ${((att.counselor_turns_by_user || []).length)} turn(s)</b> as counsellor (turns ${(att.counselor_turns_by_user || []).join(", ") || "—"}). The AI's ${((att.counselor_turns_by_llm || []).length)} counsellor turn(s) were excluded.`
      : `You never sat in the counsellor's chair, so this evaluates the <b>AI counsellor's</b> ${((att.counselor_turns_by_llm || []).length)} turn(s).`;

    openModal(`
      <h2>Feedback on the counselling session</h2>
      <p class="tiny muted">${partyLine}</p>
      <div class="overall"><b>${r.overall_score}</b><span class="muted">/ 10 overall</span></div>
      <p class="tiny muted">${esc(r.overall_rationale || "")}</p>
      ${DIMS.map((d) => {
        const s = (r.scores && r.scores[d]) || { score: 0, justification: "" };
        return `<div class="score-row">
          <div>${nice(d)}<div class="bar"><i style="width:${s.score * 10}%"></i></div></div>
          <div class="score-num">${s.score}</div>
          <div class="muted">${esc(s.justification)}</div></div>`;
      }).join("")}
      ${comparison ? `<h3 style="margin-top:20px">Your scores vs the AI supervisor</h3>
        <div class="cmp-row"><b>dimension</b><b>you</b><b>AI</b><b>diff</b></div>
        ${comparison.map((c) => `<div class="cmp-row"><span>${nice(c.dimension)}</span>
          <span>${c.you}</span><span>${c.supervisor_llm}</span>
          <span style="color:${Math.abs(c.delta) > 2 ? "var(--danger)" : "var(--muted)"}">${c.delta > 0 ? "+" : ""}${c.delta}</span></div>`).join("")}
        <p class="tiny muted" style="margin-top:8px">Mean absolute difference: ${out.mean_absolute_difference}</p>` : ""}
      <h3 style="margin-top:20px">Also assessed</h3>
      <div class="kv tiny">
        <p><b>Active listening:</b> ${esc((r.additional_assessment || {}).active_listening)}</p>
        <p><b>Open-ended questioning:</b> ${esc((r.additional_assessment || {}).open_ended_questioning)}</p>
        <p><b>Safety &amp; ethics:</b> ${esc((r.additional_assessment || {}).safety_and_ethics)}</p>
      </div>
      <h3 style="margin-top:20px">Strengths</h3>${list(r.strengths)}
      <h3 style="margin-top:16px">Three things to work on</h3>
      ${(r.improvements || []).map((i) => `<div class="imp">
        <div class="q">turn ${esc(i.turn)} — “${esc(i.original)}”</div>
        <p><b>Why:</b> ${esc(i.why)}</p>
        <p><b>Try instead:</b> “${esc(i.alternative)}”</p></div>`).join("")}
    `);
  }

  $("#modal-close").addEventListener("click", closeModal);
  $("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });

  /* ---------------- boot ---------------- */
  (async function boot() {
    Scene.init($("#scene"), $("#overlay"));
    if (!Scene.available) {
      $("#stage").innerHTML =
        '<div style="padding:24px;color:#a496b5">3D scene unavailable (Three.js could not load). ' +
        'The session still works as text below.</div>';
    }
    try {
      meta = await API.meta();
      $("#banner").textContent = meta.banner;
    } catch (e) { /* server not reachable yet */ }

    if (API.token) {
      try {
        const me = await API.me();
        await enterApp(me.username);
        return;
      } catch (e) { API.setToken(""); }
    }
    showScreen("auth");
  })();
})();
