"""
audit.py — Snapshot Stage 1: QueryAudit
------------------------------------------------------------
Reads the raw file + developer criteria, asks Claude to REASON about
what looks wrong, and returns structured findings.

THE GOLDEN RULE: this stage only READS data and WRITES findings (JSON).
It never changes a single cell. The AI reasons; it does not transform.
------------------------------------------------------------
"""

import os
import json
import yaml
import pandas as pd
from dotenv import load_dotenv
import anthropic

load_dotenv()


# ---------- plain Python: load the inputs ----------

def load_criteria(path="config/dev_criteria.yaml"):
    """Read the developer intention layer (YAML) into a dict."""
    with open(path, "r") as f:
        return yaml.safe_load(f)


def load_data(path="sample_data/messy_banks.csv"):
    """Read the raw CSV. dtype=str so pandas doesn't 'helpfully' reformat
    anything before the AI has even looked at it — we want the raw mess."""
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def profile_columns(df):
    """Build a compact, text-only summary of each column for the AI.
    We send PATTERNS (unique values, counts, blanks) — not a data dump.
    This keeps the token cost tiny and the AI focused on structure."""
    profile = {}
    for col in df.columns:
        values = df[col].tolist()
        uniques = sorted(set(values))
        profile[col] = {
            "total_rows": len(values),
            "blank_count": sum(1 for v in values if v.strip() == ""),
            "unique_count": len(uniques),
            # cap the sample so a huge column can't blow up the prompt
            "sample_unique_values": uniques[:25],
        }
    return profile


# ---------- the ONE ai part: ask Claude to reason ----------

def run_audit(column_profile, criteria):
    """Hand the column patterns + criteria to Claude and ask for findings.
    Returns a Python dict parsed from Claude's JSON. No data is modified."""

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # The system prompt sets the rules of engagement. We are explicit that
    # the model REASONS and REPORTS — it must not rewrite data.
    system_prompt = (
        "You are QueryAudit, a careful data-quality reviewer. "
        "You are given a profile of a dataset's columns (unique values, "
        "counts, blanks) and a set of developer criteria. "
        "Your job is to REASON about what looks wrong and REPORT it. "
        "You never rewrite or output corrected data — you only describe "
        "issues and suggest fixes for a human to confirm. "
        "Respond with ONLY valid JSON, no prose before or after."
    )

    # The user prompt carries the actual payload + the exact shape we want back.
    user_prompt = f"""Here is the column profile of the dataset:

{json.dumps(column_profile, indent=2)}

Here are the developer criteria (pinned rules are ground truth; proposed
items are judgment calls you should reason about):

{json.dumps(criteria, indent=2)}

Analyze the data against the criteria. Look for: spelling drift (values
that are likely the same thing misspelled), invalid or inconsistent
state values, mixed date formats, dates outside the expected range,
blank/null clusters, inconsistent boolean representations, and possible
duplicates. For duplicates, reason about whether a repeat looks genuine
or coincidental.

Return ONLY this JSON structure:
{{
  "findings": [
    {{
      "column": "column name",
      "issue_type": "spelling_drift | invalid_value | mixed_date_format | out_of_range | null_cluster | inconsistent_boolean | possible_duplicate",
      "description": "what you see, briefly",
      "suspect_values": ["the actual values involved"],
      "suggested_fix": "what a human might do about it",
      "confidence": "high | medium | low"
    }}
  ],
  "questions_for_user": ["any clarifying question worth asking before cleanup"]
}}"""

    response = client.messages.create(
        model="claude-sonnet-5-5",
        max_tokens=4000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    # Sonnet may return a thinking block first — grab the actual text block
    raw = ""
    for block in response.content:
        if block.type == "text":
            raw = block.text.strip()
            break

    # Be forgiving if the model wraps JSON in a ```json fence
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    return json.loads(raw)


# ---------- plain Python: present the findings ----------

def print_report(result):
    """Human-readable printout of the audit. Still no data touched."""
    findings = result.get("findings", [])
    questions = result.get("questions_for_user", [])

    print(f"\n{'='*60}")
    print(f"  QUERYAUDIT REPORT — {len(findings)} issue(s) found")
    print(f"{'='*60}\n")

    for i, f in enumerate(findings, 1):
        print(f"[{i}] {f['column']} — {f['issue_type']}  ({f['confidence']} confidence)")
        print(f"    {f['description']}")
        if f.get("suspect_values"):
            print(f"    Suspect: {f['suspect_values']}")
        print(f"    Suggested fix: {f['suggested_fix']}\n")

    if questions:
        print("QUESTIONS BEFORE CLEANUP:")
        for q in questions:
            print(f"  ? {q}")
    print()


# ---------- entry point ----------

def main():
    print("Loading criteria and data...")
    criteria = load_criteria()
    df = load_data()

    print(f"Loaded {len(df)} rows, {len(df.columns)} columns.")
    print("Profiling columns (no data modified)...")
    profile = profile_columns(df)

    print("Sending patterns to Claude for reasoning...\n")
    result = run_audit(profile, criteria)

    print_report(result)

    # Save findings to a file so Stage 2 (recipe) can use them later
    os.makedirs("output", exist_ok=True)
    with open("output/audit_findings.json", "w") as f:
        json.dump(result, f, indent=2)
    print("Findings saved to output/audit_findings.json")


if __name__ == "__main__":
    main()
