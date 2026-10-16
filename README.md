# Snapshot

**An AI data-cleaning pipeline that reasons about messy spreadsheets — but never touches the numbers.**

Departments hand analysts spreadsheets formatted however they felt like: cities misspelled three
different ways, dates in five different formats, booleans as `yes` / `TRUE` / `1`, impossible years,
blanks with no explanation. Cleaning that by hand is slow, and every manual edit is a chance to
introduce a new error.

Snapshot reads the mess, uses an AI to figure out *what's wrong* and *what to do about it*, and then
lets plain Python do every actual edit. The AI plans; deterministic code executes. You get smart
judgment on the front end and trustworthy, traceable output on the back end — plus a report that
flags exactly what it changed, so nothing is a mystery.

---

## The core idea

> **The AI only ever reads data and writes instructions. It never writes data.**

This is the whole design. A language model asked to *transform* data can silently invent a value or
drop a row and format it so cleanly you'd never notice. So Snapshot never lets it. Instead:

1. The AI **reads** a profile of the data and **reports** what looks wrong.
2. The AI **reads** those findings and **writes a recipe** — an explicit, machine-readable plan.
3. **pandas** follows the recipe and does every actual transformation. No AI involved.

Every number that moves, moves in Python you can read and trust.

---

## How it works — four stages

| Stage | File | What it does | AI? |
|-------|------|--------------|-----|
| 1. Audit | `audit.py` | Profiles each column, asks the AI to **reason** about what's wrong (spelling drift, mixed date formats, out-of-range values, inconsistent booleans, possible duplicates). Outputs findings as JSON. | ✅ reads & reports |
| 2. Recipe | `recipe.py` | Hands the findings to the AI, which drafts a **cleaning plan** as JSON instructions. Flags risky steps for human confirmation. | ✅ plans only |
| 3. Executor | `executor.py` | Reads the recipe and applies it with **pandas**. The only stage that edits data. Fully deterministic. | ❌ zero AI |
| 4. Report | `report.py` | pandas computes every figure; the AI writes a short, data-specific **Analyst Notes** block that surfaces what a busy reader would miss. Outputs a styled HTML report. | ✅ summary only |

Each stage saves its output to `output/`, so you can inspect any step on its own. `run.py` chains all
four into a single command.

### What makes the output trustworthy

- **Flag columns, not silent deletions.** When Snapshot nulls a bad value (an out-of-range date, a
  missing amount), it adds a `*_flag` column recording *why*. Dirty data is quarantined and labeled,
  never quietly dropped — you keep an audit trail.
- **Human-in-the-loop on the finicky calls.** The recipe marks ambiguous steps (date-format
  direction, nulling values, masking) as `needs_confirmation` so a person reviews them before
  anything runs.
- **Sensitive columns masked by default.** Account references are masked (`*****0001`) in the
  cleaned output, not just the report.

---

## Setup

Requires **Python 3.10+**.

```bash
# 1. install dependencies
pip install -r requirements.txt

# 2. add your Anthropic API key
cp .env.example .env
# then open .env and paste your key (starts with sk-ant-)

# 3. confirm the connection works
python test_connection.py
```

The API key is read from `.env`, which is gitignored and never committed.

## Run it

```bash
# full pipeline, one command
python run.py

# or point it at a different file
python run.py --file sample_data/your_file.csv
```

Then open `output/snapshot_report.html` in any browser.

You can also run any stage on its own: `python audit.py`, `python recipe.py`, etc.

---

## What it needs to run — and what breaks it

Knowing what makes something work is only half of it; here's what it depends on and what stops it,
so a security team knows this isn't plug-and-play.

**Needs:**
- Python 3.10+
- The packages in `requirements.txt` (`anthropic`, `pandas`, `pyyaml`, `python-dotenv`)
- An Anthropic API key
- **Outbound HTTPS to `api.anthropic.com` (port 443).** The AI reasoning is a network call. This is
  the one piece IT has to allow.

**What breaks it:**
- **No outbound internet / a blocking proxy** → the API calls time out. The reasoning stages can't run.
- **Missing or unset API key** → authentication error on the first call.
- **Corporate SSL inspection (a man-in-the-middle proxy)** → certificate errors on the HTTPS call
  unless the proxy's CA cert is trusted by Python.
- **A locked-down VDI** that blocks installs or outbound traffic → not a suitable host. This runs in
  an open environment (a personal machine or an approved dev box), by design.

## Production hardening (not in this prototype)

This is a prototype built for clarity. In a deployed environment, two things would change:

- **Authentication:** the local `.env` API key would be replaced with **workload identity
  federation** (short-lived tokens via an identity provider) so there's no long-lived secret stored
  on disk.
- **Access:** a non-technical user wouldn't touch a terminal — see below.

## Future work

- **Streamlit front-end** so non-technical users drag in a CSV, click a button, and get the report
  in-browser — no command line.
- **Amount-level duplicate detection** as an explicit check (currently reasoned about in the notes).
- **Multi-agent split** — dedicated agents per task type as the criteria set grows.

---

## Architecture at a glance

```
messy CSV
   │
   ▼
[1] audit.py      ── AI reasons ──▶  output/audit_findings.json
   │
   ▼
[2] recipe.py     ── AI plans   ──▶  output/cleaning_recipe.json
   │
   ▼
[3] executor.py   ── pandas     ──▶  output/cleaned_banks.csv   (+ flag columns)
   │
   ▼
[4] report.py     ── pandas + AI ─▶  output/snapshot_report.html
```

Built with Python and the Anthropic API (Claude).
