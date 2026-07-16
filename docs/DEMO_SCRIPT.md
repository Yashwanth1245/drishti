# DEMO_SCRIPT — the four-minute judge walkthrough

Updated 2026-07-02 to match the BUILT product (every step verified live in the
browser). One continuous investigation story; every judged capability appears
as a natural step. Rehearse to 4 minutes; judges' Q&A follows.

Pre-demo state: backend (`uvicorn app.main:app --port 8000`) + frontend
(`npm run dev`) running, data regenerated (seed 2026), `app.precompute` run.
Demo asset: `exports/demo_fir_scan.png`. Warm the LLM once (ask any chat
question) before going on stage so the first live answer isn't cold.
SIGN IN AS `dgp` BEFORE going on stage (password `drishti2026`) — the app
opens on the login screen; the close at 3:45 does the live role switch.

## 0:00–0:30 — Command map (the cold open)

Open `#/map`. Karnataka on the dark basemap, districts as circles; only the
genuinely-hottest zones pulse red (Bengaluru Urban z≈9.5, Vijayanagara,
Dakshina Kannada — NOT every district, that's the point). Point at the KPI
strip: 4,711 FIRs last 30 days (+30% YoY), 321 active alerts. Role chip:
"DGP — Karnataka State".

> "Every number here traces to specific FIRs — the design rule of the whole
> platform. And the map is honest: only the true statistical hotspots pulse,
> not everything."

Flip the hour filter to **21-24 hrs** while still at the STATE view — the
whole map re-weighs and the night-crime geography appears (different
districts lead the rate board). Back to All hours, then click a pulsing
district (e.g. **Bengaluru Urban**) → drills to station level; the hour
filter layers there too. The Dharwad snatching series (our story) surfaces
on the next tab.

## 0:30–1:00 — Alerts (proactive, not reactive)

Tab **Alerts**. Read the top spike card:
*"Pattern 'two-wheeler-pillion-snatch' in Dharwad is 220% above its 8-window
baseline (z = 2.4)"* — with 4 clickable evidence FIR chips.

> "No human configured this alert. The monitoring engine watches every
> district × crime-pattern series against its own history and flags the
> deviations — a pattern-level surge that would be invisible inside the broad
> robbery totals."

## 1:00–2:00 — The reveal: entity resolution + profile

Search **"Ravikumar"** (top-right). The dropdown lists SEVERAL distinct
Ravikumars across districts.

> "The database has thousands of people named Ravikumar. Our system keeps them
> apart — it does not merge on name."

Click the top hit (**Ravikumar B, 11 cases, Dharwad, risk 64.5** — entity
215774). Profile page: 11-case timeline across Belagavi → Davanagere →
Hubballi, the explainable risk breakdown, the aliases (Ravi Kumar / B. Ravi
Kumar / **Chikka Ravi**), and the captured-ID table showing the SAME Aadhaar
738492016453 twice — once under "Ravikumar B" (2024), once under the alias
"Chikka Ravi" (2025).

> "In the source data these were 11 unrelated rows in three district silos. No
> Excel sheet connects them. Our resolver linked them — and the row that named
> him only by his street alias is linked with certainty by the Aadhaar captured
> at both arrests. 94% precision on a held-out test set, and it shows its work
> on every merge."

## 2:00–2:35 — Network (organized crime)

Search **"Salim Mujawar"**, open the 4-case Bengaluru entity → **View
network**. The vehicle-theft ring renders: the fence at center connecting six
thieves with co-accused edges. Click an edge → the shared FIRs.

> "The same engine, seen as a graph — a receiver of stolen property tying a
> rotating crew together across four districts."

## 2:35–3:20 — Ask the data (the agentic layer)

Tab **Ask the data**. Type (or click the suggestion):
*"Tell me about Ravikumar B from Dharwad — history, aliases, associates."*
The agent answers in prose with **[FIR-number] citations** and a "How I got
this" trace showing the 3 typed tool calls.

> "GLM 4.7 running on Zoho Catalyst. It cannot write SQL — it can only call
> typed, parameter-bound query tools, so it cannot be prompt-injected and
> cannot invent a case number. Every claim is cited; every tool call is shown."

Optionally ask a fresh one: *"How many chain snatching cases in Dharwad in
2026?"* → "7", one tool call.

## 3:20–3:45 — Beyond manual records (Qwen scan)

Tab **Scan FIR**, upload `demo_fir_scan.png` (a photographed paper FIR). Qwen
VLM returns a structured draft record — FIR number, station, parties, BNS
sections, brief, property — with an "officer must verify" guard.

> "This is the 'moving beyond Excel and paper' pillar — a photographed FIR
> becomes a structured, searchable record in seconds."

## 3:45–4:00 — Close: RBAC + production readiness

Back to **Alerts** → "Generate brief" on the Dharwad spike (pre-generated in
rehearsal if time is tight) → cited intelligence brief with **Save as PDF**.
Then the 15-second rank ladder: pick **SP (District) — Dharwad** in the rank
dropdown (top right — each pick is a real re-login, no sign-out needed) →
the map collapses to one district, KPIs rescope, and the snatcher's profile
still shows ALL 11 linked case numbers — 5 marked 🔒. Open a 🔒 Belagavi FIR:
sections, dates and the accused are visible, but victims and the narrative
are redacted → click **Request access**. Flip back to **DGP** and flash the
**Audit** tab: the role switches and the SP's access request are in the
trail.

> "Access mirrors the real command hierarchy and is enforced in the database
> layer, not the UI — and every sensitive action — who searched which name,
> who opened whose file, every denial — is on the audit trail. Synthetic data as the rules require — but calibrated to real NCRB
> proportions, deliberately messy, 200,000 FIRs, sub-second queries, one
> Catalyst container. It works on mess, so it will work on the real thing."

## Backup plans

- Network dead: local run + a pre-recorded screen capture of this exact flow.
- LLM slow/down: the map, alerts, entity, network, and case lenses never touch
  the LLM — only Ask-the-data / Scan / Generate-brief do. Lead with the
  non-LLM reveal (search → profile → network) and treat the agent as the
  bonus.
- Time cut to 2 min: cold open (map+alert) → search → profile → ask-the-data.

## Concrete anchors (verified live 2026-07-02)

- S1 snatcher entity 215774; Aadhaar 738492016453; Dharwad snatching spike
  +220%, z 2.4.
- S2 fence "Salim Mujawar" Bengaluru entity (4 cases) → 7-node / 6-edge ring.
- ER precision 0.94; 321 alerts; 200,846 cases; warm API < 170 ms.
- RBAC (verified 2026-07-03): every rank sees all 11 S1 case numbers; the
  🔒-restricted count walks the ladder — dgp 0 / dig.northern 2 /
  sp.belagavi 8 / sp.davanagere 9 / sp.dharwad 5. SP on a Belagavi FIR →
  restricted view (no victims/narrative) + "Request access" → lands in the
  audit trail. All passwords `drishti2026`.
