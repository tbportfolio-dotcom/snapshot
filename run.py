"""
run.py — Snapshot: run the whole pipeline with one command.
------------------------------------------------------------
Chains all four stages in order:
  1. audit      — AI reasons about what's wrong (no data touched)
  2. recipe     — AI drafts a cleaning plan (instructions only)
  3. executor   — pandas applies the plan (the only stage that edits data)
  4. report     — pandas computes numbers, AI writes Analyst Notes, HTML out

Usage:
  python run.py
  python run.py --file sample_data/some_other_file.csv

Each stage still saves its own output in output/, so you can inspect any
step individually. This just saves you running four commands by hand.
------------------------------------------------------------
"""

import sys
import argparse

import audit
import recipe
import executor
import report


def main():
    parser = argparse.ArgumentParser(description="Run the Snapshot pipeline end to end.")
    parser.add_argument(
        "--file",
        default="sample_data/messy_banks.csv",
        help="Path to the messy CSV to process (default: sample_data/messy_banks.csv)",
    )
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  SNAPSHOT PIPELINE")
    print(f"  Input: {args.file}")
    print("=" * 60)

    # ---- Stage 1: Audit ----
    print("\n[1/4] QUERYAUDIT — reasoning about data quality...")
    criteria = audit.load_criteria()
    df_raw = audit.load_data(args.file)
    profile = audit.profile_columns(df_raw)
    audit_result = audit.run_audit(profile, criteria)
    audit._save(audit_result)  # save findings for the record
    print(f"      Found {len(audit_result.get('findings', []))} issue(s).")

    # ---- Stage 2: Recipe ----
    print("\n[2/4] RECIPE — drafting the cleaning plan...")
    recipe_obj = recipe.generate_recipe(audit_result, criteria)
    recipe._save(recipe_obj)
    confirms = sum(1 for s in recipe_obj.get("recipe", []) if s.get("needs_confirmation"))
    print(f"      {len(recipe_obj.get('recipe', []))} transform(s), {confirms} need confirmation.")

    # ---- Stage 3: Executor ----
    print("\n[3/4] EXECUTOR — applying the plan with pandas (no AI)...")
    df_clean = executor.load_data(args.file)
    df_clean = executor.run_recipe(df_clean, recipe_obj)
    executor._save(df_clean)
    print(f"      Clean data written ({len(df_clean)} rows).")

    # ---- Stage 4: Report ----
    print("\n[4/4] REPORT — building the HTML summary...")
    # Reload the cleaned CSV from disk so pandas infers numeric types.
    # The executor keeps every column as text (to avoid reformatting raw
    # data); the report needs real floats to sum amounts, so we read the
    # saved file back the same way the standalone report stage does.
    df_report = report.load_clean()
    summaries = report.compute_summaries(df_report)
    notes = report.write_analyst_notes(df_report)
    html = report.build_html(summaries, notes, df_report)
    report._save(html)
    print("      Report written to output/snapshot_report.html")

    print("\n" + "=" * 60)
    print("  DONE — open output/snapshot_report.html in your browser.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
