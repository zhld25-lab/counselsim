/* Tiny fetch wrapper. The API key never lives here - all LLM calls are server side. */
const API = (() => {
  let token = localStorage.getItem("cs_token") || "";

  function setToken(t) {
    token = t || "";
    if (t) localStorage.setItem("cs_token", t);
    else localStorage.removeItem("cs_token");
  }

  async function req(method, path, body) {
    const res = await fetch(path, {
      method,
      headers: Object.assign(
        { "Content-Type": "application/json" },
        token ? { Authorization: "Bearer " + token } : {}
      ),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    let data = null;
    try { data = await res.json(); } catch (e) { /* empty body */ }
    if (!res.ok) {
      const err = new Error((data && data.detail) || res.statusText || "Request failed");
      err.status = res.status;
      throw err;
    }
    return data;
  }

  return {
    setToken,
    get token() { return token; },
    meta: () => req("GET", "/api/meta"),
    register: (username, password) => req("POST", "/api/auth/register", { username, password }),
    login: (username, password) => req("POST", "/api/auth/login", { username, password }),
    me: () => req("GET", "/api/auth/me"),

    options: () => req("GET", "/api/patients/options"),
    createPatient: (p) => req("POST", "/api/patients", p),
    listPatients: () => req("GET", "/api/patients"),
    getPatient: (id) => req("GET", "/api/patients/" + id),

    startSession: (patient_id, user_role) => req("POST", "/api/sessions", { patient_id, user_role }),
    getSession: (id) => req("GET", "/api/sessions/" + id),
    say: (id, text, emotion, action) => req("POST", `/api/sessions/${id}/say`, { text, emotion, action: action || "" }),
    step: (id) => req("POST", `/api/sessions/${id}/step`),
    switchRole: (id, role) => req("POST", `/api/sessions/${id}/role`, { role }),
    askSupervisor: (id) => req("POST", `/api/sessions/${id}/supervisor-tip`),
    intervene: (id, note) => req("POST", `/api/sessions/${id}/intervene`, { note }),
    endSession: (id) => req("POST", `/api/sessions/${id}/end`),
    feedback: (id) => req("POST", `/api/sessions/${id}/feedback`),
    myScores: (id, scores, comment) => req("POST", `/api/sessions/${id}/my-scores`, { scores, comment }),
  };
})();
