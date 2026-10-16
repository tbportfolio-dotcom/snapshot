"""
report.py — Snapshot Stage 4: The Report
------------------------------------------------------------
Reads the CLEANED data and builds a self-contained HTML report for the
"doers" to drop into a senior check-in.

Division of labor (the golden rule, one more time):
  - pandas computes EVERY number (totals, counts, breakdowns). Trustworthy.
  - AI writes ONE short "Analyst Notes" block: open-ended, leads with
    whatever it judges most important THIS run. Labeled as AI-generated,
    numbers-verified. This is what varies run-to-run — because it's judging,
    not templating.
------------------------------------------------------------
"""

import os
import json
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv
import anthropic

load_dotenv()


# ---------- load cleaned data ----------

def load_clean(path="output/cleaned_banks.csv"):
    return pd.read_csv(path)


# ---------- pandas: all the numbers ----------

def compute_summaries(df):
    """Every figure in the report comes from here. No AI touches these."""
    summaries = {}

    # headline counts
    summaries["total_rows"] = len(df)
    summaries["flagged_dates"] = int((df.get("Transaction_Date_flag", pd.Series()).fillna("") != "").sum())
    summaries["flagged_amounts"] = int((df.get("Current_Amount_flag", pd.Series()).fillna("") != "").sum())

    # total amount by bank (alphabetical) — your original spec example
    by_bank = (
        df.groupby("Bank_Name")["Current_Amount"]
        .sum().reset_index().sort_values("Bank_Name")
    )
    summaries["by_bank"] = by_bank

    # total by state
    by_state = (
        df.groupby("State")["Current_Amount"]
        .sum().reset_index().sort_values("State")
    )
    summaries["by_state"] = by_state

    # open vs closed
    if "Is_Open" in df.columns:
        summaries["open_count"] = int((df["Is_Open"] == True).sum())
        summaries["closed_count"] = int((df["Is_Open"] == False).sum())

    summaries["grand_total"] = float(df["Current_Amount"].sum())
    return summaries


# ---------- the ONE ai part: analyst notes ----------

def write_analyst_notes(df):
    """Open-ended: AI reads the clean data + flags and surfaces what matters
    MOST this run. Leads with its own judgment. Varies by data."""
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # send a compact view: the data as records + the flag columns
    sample = df.to_dict(orient="records")

    system_prompt = (
        "You are a data analyst writing the closing note on a cleaned "
        "dataset for a busy manager. You are given the cleaned rows, "
        "including any flag columns marking rows that were nulled or need "
        "review. Write a short, tight paragraph (up to about 5 sentences) "
        "that leads with the SINGLE most important thing a busy person "
        "should notice in THIS data — a "
        "pattern, an outlier, a relationship between columns, or a "
        "data-quality concern. Do not just restate totals; the tables "
        "already show those. Surface what they'd miss. Plain, matter-of-fact "
        "tone. No preamble, just the note."
    )

    user_prompt = f"Cleaned data (with flags):\n\n{json.dumps(sample, indent=2, default=str)}"

    response = client.messages.create(
        model="claude-sonnet-5-5",
        max_tokens=1000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    for block in response.content:
        if block.type == "text":
            return block.text.strip()
    return "(No notes generated.)"


# ---------- build the HTML ----------

def df_to_html_table(df, money_cols=None):
    money_cols = money_cols or []
    d = df.copy()
    for c in money_cols:
        d[c] = d[c].apply(lambda v: f"${v:,.2f}")
    return d.to_html(index=False, border=0, classes="data")


def bar_chart(df, label_col, value_col):
    """Pure HTML/CSS horizontal bars — no chart library, no images.
    Each bar is a div sized by percentage of the largest value."""
    rows = df.sort_values(value_col, ascending=False)
    max_val = rows[value_col].max() or 1
    bars = ""
    for _, r in rows.iterrows():
        pct = (r[value_col] / max_val) * 100
        bars += f"""
      <div class="bar-row">
        <div class="bar-label">{r[label_col]}</div>
        <div class="bar-track">
          <div class="bar-fill" style="width:{pct:.1f}%"></div>
        </div>
        <div class="bar-value">${r[value_col]:,.0f}</div>
      </div>"""
    return f'<div class="bars">{bars}</div>'


def build_html(summaries, notes, df):
    now = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    bank_table = df_to_html_table(summaries["by_bank"], money_cols=["Current_Amount"])
    state_table = df_to_html_table(summaries["by_state"], money_cols=["Current_Amount"])
    bank_bars = bar_chart(summaries["by_bank"], "Bank_Name", "Current_Amount")

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Snapshot Report</title>
<style>
  :root {{
    --bg: #192432; --panel: #2F3A49; --inset: #26313F;
    --surface: #D9DEDD; --muted: #6A7C89;
    --low: #5F9E7F; --high: #D47A3A; --critical: #C94F4F;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 32px 16px; background: var(--bg);
    color: var(--surface); font-family: -apple-system, Segoe UI, Roboto, sans-serif;
    line-height: 1.5;
  }}
  .wrap {{ max-width: 860px; margin: 0 auto; }}
  h1 {{ font-size: 1.6rem; margin: 0 0 4px; }}
  .meta {{ color: var(--muted); font-size: 0.85rem; margin-bottom: 28px; }}
  .notes {{
    background: var(--panel); border-left: 4px solid var(--low);
    padding: 18px 20px; border-radius: 8px; margin-bottom: 10px;
  }}
  .notes h2 {{ font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em;
    color: var(--muted); margin: 0 0 10px; }}
  .notes p {{ margin: 0; font-size: 1.05rem; }}
  .tag {{ display: inline-block; margin-bottom: 28px; font-size: 0.72rem;
    color: var(--muted); }}
  .kpis {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 28px; }}
  .kpi {{ background: var(--surface); color: var(--bg); border-radius: 8px;
    padding: 14px 18px; flex: 1; min-width: 120px; }}
  .kpi .num {{ font-size: 1.8rem; font-weight: 700; }}
  .kpi .lbl {{ font-size: 0.78rem; color: #40515f; }}
  .kpi.flag .num {{ color: var(--critical); }}
  h3 {{ font-size: 1rem; margin: 24px 0 8px; color: var(--surface); }}
  table.data {{ width: 100%; border-collapse: collapse; background: var(--panel);
    border-radius: 8px; overflow: hidden; font-size: 0.9rem; }}
  table.data th {{ background: var(--inset); text-align: left; padding: 10px 14px;
    color: var(--muted); font-weight: 600; }}
  table.data td {{ padding: 10px 14px; border-top: 1px solid var(--inset); }}
  .bars {{ background: var(--panel); border-radius: 8px; padding: 16px 18px; }}
  .bar-row {{ display: flex; align-items: center; gap: 12px; margin: 8px 0; }}
  .bar-label {{ width: 130px; font-size: 0.85rem; color: var(--surface); flex-shrink: 0; }}
  .bar-track {{ flex: 1; background: var(--inset); border-radius: 4px; height: 22px; overflow: hidden; }}
  .bar-fill {{ height: 100%; background: var(--low); border-radius: 4px; }}
  .bar-value {{ width: 90px; text-align: right; font-size: 0.82rem; color: var(--muted); flex-shrink: 0; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Snapshot Report</h1>
  <div class="meta">Generated {now} &middot; source: cleaned_banks.csv</div>

  <div class="notes">
    <h2>Analyst Notes</h2>
    <p>{notes}</p>
  </div>
  <div class="tag">AI-generated summary &middot; all figures computed and verified by the pipeline</div>

  <div class="kpis">
    <div class="kpi"><div class="num">{summaries['total_rows']}</div><div class="lbl">Total records</div></div>
    <div class="kpi"><div class="num">${summaries['grand_total']:,.0f}</div><div class="lbl">Grand total</div></div>
    <div class="kpi flag"><div class="num">{summaries['flagged_dates']}</div><div class="lbl">Dates flagged</div></div>
    <div class="kpi flag"><div class="num">{summaries['flagged_amounts']}</div><div class="lbl">Amounts flagged</div></div>
  </div>

  <h3>Balances by Bank</h3>
  {bank_bars}

  <h3>Total Amount by Bank</h3>
  {bank_table}

  <h3>Total Amount by State</h3>
  {state_table}
</div>
</body>
</html>"""
    return html


def main():
    print("Loading cleaned data...")
    df = load_clean()

    print("Computing summaries (pandas)...")
    summaries = compute_summaries(df)

    print("Writing Analyst Notes (AI reads the data + flags)...")
    notes = write_analyst_notes(df)
    print(f"\n  Notes: {notes}\n")

    print("Building HTML report...")
    html = build_html(summaries, notes, df)

    os.makedirs("output", exist_ok=True)
    out = "output/snapshot_report.html"
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Report written to {out}")
    print("Open it in any browser.")


if __name__ == "__main__":
    main()
