# DRISHTI — 3-minute demo video script (KSP Datathon 2026, Challenge 2)

Target: **≤ 3:00**. Record the deployed Catalyst URL (or `localhost:8000`) with screen
capture + voiceover. Sign in as **dgp** first (password `drishti2026`). Keep the cursor
deliberate; let each screen settle for ~1s before narrating.

---

### 0:00–0:20 · The problem
> "Karnataka's crime records live in Excel silos — fragmented across districts, reactive,
> with no way to see one offender operating across jurisdictions. DRISHTI turns those
> records into a live, AI-driven command centre for the State Crime Records Bureau."

**Show:** the Command Map already loaded — KPI strip on top, districts pulsing.

### 0:20–0:50 · Advanced visualization & hotspots
> "Every district, sized by case volume. Red zones pulse where a crime is spiking above
> its historical baseline. We can layer time-of-day onto location…"

**Do:** change the **hour band** to `21–24` → leaderboard reorders (night-crime geography).
Click a **district** → drill into its **stations**. Reset to *All hours*.

### 0:50–1:35 · The differentiator — entity resolution
> "Now the core: entity resolution. I'll search one offender."

**Do:** search **Ravikumar** → open the profile.
> "One person — 11 cases across THREE districts, under four different spellings including
> the alias 'Chikka Ravi'. How do we know it's him? The SAME Aadhaar was captured on two
> different arrests — that's what exposes the alias. And the risk score is fully
> explainable. This is impossible in isolated Excel sheets."

**Show:** case history, KNOWN NAMES/SPELLINGS, the repeated Aadhaar in CAPTURED IDENTIFIERS.

### 1:35–2:05 · Criminal networks
> "From any offender we open their association network…"

**Do:** click **View network** (or Network tab → a group) → the graph fans out.
> "Node-based link analysis reveals organized structures — co-accused links, shared MO —
> that connect fragmented cases into one picture."

### 2:05–2:40 · Agentic AI on Zoho Catalyst
**Do:** Ask-the-Data → type **"Tell me about the repeat offender Ravikumar B"** → answer.
> "This is our agentic layer — GLM 4.7 running on Zoho Catalyst QuickML. It answers in
> plain English, and every claim is a clickable FIR citation. It never writes SQL — it
> calls typed, access-controlled tools." Flip **EN → ಕನ್ನಡ**: the whole interface
> and the AI's answer switch to Kannada — regional-language support in one click.

### 2:40–2:55 · RBAC + evidence doctrine
**Do:** switch rank chip DGP → **sp.dharwad**.
> "Access mirrors the real police hierarchy — an SP sees only their district; identity
> intelligence is shared, but out-of-jurisdiction FIR details stay redacted. Every action
> is audited."

### 2:55–3:00 · Close
> "200,000 synthetic, NCRB-calibrated FIRs. Deployed entirely on Zoho Catalyst. Every
> number auditable. DRISHTI — from records to intelligence."

**Show:** back to the Command Map (strong closing frame).

---

**Recording tips**
- 1080p, browser zoomed so text is legible; hide bookmarks bar.
- If the live LLM is slow on the day, pre-run the chat query once to warm it, then record.
- Upload as **unlisted YouTube** or **public Google Drive**, then paste the link into
  slide 13 of the submission deck.
