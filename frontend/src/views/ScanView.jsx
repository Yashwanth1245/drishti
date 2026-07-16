import React, { useState } from "react";
import { api } from "../api.js";

// Scan-FIR lens: Qwen VLM on Zoho Catalyst digitizes a photographed/scanned
// FIR into a structured draft record — the "beyond manual records" demo.
export default function ScanView() {
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  async function onFile(e) {
    const f = e.target.files?.[0];
    if (!f) return;
    setPreview(URL.createObjectURL(f));
    setResult(null);
    setErr(null);
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", f);
      setResult(await api("/api/ingest/scan", { method: "POST", body: fd }));
    } catch (x) {
      setErr(String(x));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="pad">
      <h2 className="pagetitle">Scan a paper FIR
        <span className="muted" style={{ fontSize: 13, marginLeft: 10 }}>
          Qwen VLM on Zoho Catalyst · photograph → structured draft record
        </span>
      </h2>
      <div className="filters">
        <input type="file" accept="image/*" onChange={onFile} />
      </div>
      <div className="grid2">
        <div className="card">
          <h3>Document</h3>
          {preview
            ? <img src={preview} alt="scan"
                   style={{ width: "100%", borderRadius: 8,
                            border: "1px solid var(--border)" }} />
            : <div className="muted">Choose a photo or scan of an FIR.
                (Demo asset: exports/demo_fir_scan.png)</div>}
        </div>
        <div className="card">
          <h3>Extracted draft record</h3>
          {busy && <div className="loading">Qwen is reading the document…</div>}
          {err && <div className="err">{err}</div>}
          {result?.fields && (
            <>
              <table className="t">
                <tbody>
                  {Object.entries(result.fields).map(([k, v]) => (
                    <tr key={k}>
                      <td className="muted">{k.replaceAll("_", " ")}</td>
                      <td>{Array.isArray(v) ? v.join("; ") : String(v ?? "—")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="chip warn" style={{ marginTop: 10 }}>
                {result.note}
              </div>
            </>
          )}
          {result && !result.fields && (
            <pre style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>
              {result.raw_text}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
