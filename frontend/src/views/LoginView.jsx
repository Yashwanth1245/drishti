import React, { useEffect, useState } from "react";
import { api, setSession } from "../api.js";

// Sign-in gate. The demo roster comes from /api/auth/demo so judges can walk
// the rank ladder (DGP -> DIG -> SP -> IO) in one click per role — publishing
// the shared password is deliberate: the entire dataset is synthetic.
export default function LoginView() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [demo, setDemo] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api("/api/auth/demo").then(setDemo).catch(() => setDemo({ accounts: [] }));
  }, []);

  async function submit(u, p) {
    setBusy(true);
    setErr(null);
    try {
      const r = await api("/api/auth/login", {
        method: "POST", json: { username: u, password: p },
      });
      setSession(r.token, r.user);
    } catch (x) {
      setErr(x.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <div className="brand" style={{ textAlign: "center", fontSize: 26 }}>
          DRISHTI<span className="kn">ದೃಷ್ಟಿ</span>
          <small>KARNATAKA CRIME INTELLIGENCE — SYNTHETIC DATA PROTOTYPE</small>
        </div>

        <form className="login-form" onSubmit={(e) => {
          e.preventDefault();
          submit(username, password);
        }}>
          <label>Username
            <input value={username} autoFocus autoComplete="username"
                   onChange={(e) => setUsername(e.target.value)} />
          </label>
          <label>Password
            <input type="password" value={password} autoComplete="current-password"
                   onChange={(e) => setPassword(e.target.value)} />
          </label>
          {err && <div className="err" style={{ padding: 0 }}>{err}</div>}
          <button className="login-btn" disabled={busy || !username || !password}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>

        {demo?.accounts?.length > 0 && (
          <div className="login-demo">
            <div className="muted" style={{ fontSize: 11, margin: "14px 0 8px" }}>
              DEMO ROLES — one click each · access is enforced server-side by rank
            </div>
            {demo.accounts.map((a) => (
              <button key={a.username} className="rolebtn" disabled={busy}
                      onClick={() => submit(a.username, demo.password)}>
                <b>{a.username}</b>
                <span>{a.label}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
