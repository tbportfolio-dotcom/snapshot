"""
recipe.py — Snapshot Stage 2: Recipe Generator
------------------------------------------------------------
Reads the audit findings + developer criteria, and asks Claude to produce
a CLEANING RECIPE: an explicit, machine-readable plan of transforms.

GOLDEN RULE (still in force): Claude returns INSTRUCTIONS, not data.
It writes the recipe (JSON). It never cleans the data itself.
Stage 3 (executor.py) is what actually runs the recipe with pandas.

This is option "B": Claude proposes sensible defaults for the open
questions, builds a DRAFT recipe, and shows it to you to approve or tweak
before anything runs.
------------------------------------------------------------
"""

import os
import json
import yaml
from dotenv import load_dotenv
import anthropic

load_dotenv()


# ---------- plain Python: load the inputs ----------

def load_criteria(path="config/dev_criteria.yaml"):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def load_findings(path="output/audit_findings.json"):
    """Read the findings produced by Stage 1 (audit.py)."""
    with open(path, "r") as f:
        return json.load(f)


# ---------- the ONE ai part: ask Claude for the recipe ----------

def generate_recipe(findings, criteria):
    """Hand the findings + criteria to Claude; get back a cleaning recipe.
    Returns a Python dict (the recipe). No data is cleaned here."""

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    system_prompt = (
        "You are the Recipe Generator for a data-cleaning pipeline. "
        "You are given audit findings and developer criteria. "
        "Your job is to produce an explicit, machine-readable cleaning "
        "recipe: a list of transform instructions that a separate pandas "
        "executor will run. You do NOT clean data yourself and you NEVER "
        "output cleaned rows — only the instructions. "
        "For the audit's open questions, choose sensible DEFAULT answers "
        "and state each assumption so a human can override it. "
        "Respond with ONLY valid JSON, no prose."
    )

    user_prompt = f"""Audit findings:

{json.dumps(findings, indent=2)}

Developer criteria (pinned rules are ground truth):

{json.dumps(criteria, indent=2)}

Produce a cleaning recipe. Each transform must name a column, an action,
and whatever parameters the executor needs to run it deterministically.

Allowed actions (use these exact names):
  - standardize_state   : map values to 2-letter USPS codes (needs "map")
  - fix_spelling        : map misspellings to correct value (needs "map")
  - parse_date_to_iso   : normalize to YYYY-MM-DD (needs "assume": "US_MM_DD" or "intl_DD_MM")
  - null_and_flag       : set listed values/rows to null and mark them (needs "values" or "rows")
  - to_boolean          : map to true/false (needs "true_values", "false_values")
  - mask                : mask a sensitive column (needs "style", e.g. "last4" or "full")
  - fill_null           : optional, only if criteria allow (needs "strategy")

Return ONLY this JSON structure:
{{
  "recipe": [
    {{
      "column": "column name",
      "action": "one of the allowed actions",
      "params": {{ ... action-specific parameters ... }},
      "reason": "one line: why this transform",
      "needs_confirmation": true or false
    }}
  ],
  "assumptions": ["each default you chose for an open question"]
}}

Set needs_confirmation to true for anything risky or ambiguous (date
format direction, nulling out-of-range values, duplicate handling), so
the human reviews those before the executor runs."""

    response = client.messages.create(
        model="claude-sonnet-5-5",
        max_tokens=4000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    # Same block-type handling as audit.py: skip any thinking block
    raw = ""
    for block in response.content:
        if block.type == "text":
            raw = block.text.strip()
            break

    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    return json.loads(raw)


# ---------- plain Python: present the draft for approval ----------

def print_recipe(recipe_obj):
    recipe = recipe_obj.get("recipe", [])
    assumptions = recipe_obj.get("assumptions", [])

    print(f"\n{'='*60}")
    print(f"  DRAFT CLEANING RECIPE — {len(recipe)} transform(s)")
    print(f"{'='*60}\n")

    for i, step in enumerate(recipe, 1):
        flag = "  <-- CONFIRM" if step.get("needs_confirmation") else ""
        print(f"[{i}] {step['column']}  ->  {step['action']}{flag}")
        print(f"    reason: {step['reason']}")
        print(f"    params: {json.dumps(step['params'])}\n")

    if assumptions:
        print("ASSUMPTIONS MADE (override any before running Stage 3):")
        for a in assumptions:
            print(f"  - {a}")
    print()


# ---------- entry point ----------

def main():
    print("Loading audit findings and criteria...")
    criteria = load_criteria()
    findings = load_findings()

    print("Asking Claude to draft a cleaning recipe...\n")
    recipe_obj = generate_recipe(findings, criteria)

    print_recipe(recipe_obj)

    os.makedirs("output", exist_ok=True)
    with open("output/cleaning_recipe.json", "w") as f:
        json.dump(recipe_obj, f, indent=2)
    print("Recipe saved to output/cleaning_recipe.json")
    print("Review it — especially the <-- CONFIRM lines — before Stage 3 runs.")


if __name__ == "__main__":
    main()
