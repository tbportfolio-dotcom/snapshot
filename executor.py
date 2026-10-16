"""
executor.py — Snapshot Stage 3: The Executor
------------------------------------------------------------
Reads the cleaning recipe (from Stage 2) and APPLIES it to the raw data
using pandas. This is the ONLY stage that touches the actual data.

There is NO AI in this file. Zero. Every transform is plain, deterministic
pandas that you can read, trace, and trust. This is the whole point of the
architecture: the AI planned, Python executes.

Each recipe action maps to one small function below.
------------------------------------------------------------
"""

import os
import json
import re
from datetime import datetime
import pandas as pd


EXPECTED_MIN = datetime(2000, 1, 1)
EXPECTED_MAX = datetime(2025, 12, 31)


# ---------- load inputs ----------

def load_recipe(path="output/cleaning_recipe.json"):
    with open(path, "r") as f:
        return json.load(f)


def load_data(path="sample_data/messy_banks.csv"):
    return pd.read_csv(path, dtype=str, keep_default_na=False)


# ---------- one function per action ----------

def fix_spelling(df, col, params):
    """Replace known misspellings using the recipe's map."""
    mapping = params.get("map", {})
    if params.get("trim_whitespace"):
        df[col] = df[col].str.strip()
    # case-insensitive match if asked
    if not params.get("case_sensitive", True):
        lower_map = {k.lower(): v for k, v in mapping.items()}
        df[col] = df[col].apply(lambda v: lower_map.get(v.lower(), v))
    else:
        df[col] = df[col].replace(mapping)
    return df


def standardize_state(df, col, params):
    """Trim, uppercase, and map full names/variants to USPS 2-letter codes."""
    mapping = params.get("map", {})
    if params.get("trim_whitespace"):
        df[col] = df[col].str.strip()
    df[col] = df[col].replace(mapping)
    if params.get("uppercase_fallback"):
        # anything already 2 letters -> uppercase it
        df[col] = df[col].apply(lambda v: v.upper() if len(v) == 2 else v)
    return df


def parse_date_to_iso(df, col, params):
    """Try each known format in order; output ISO YYYY-MM-DD or null."""
    formats = params.get("formats_in_order", [])
    strip_ordinals = params.get("strip_ordinal_suffixes", False)

    def parse_one(value):
        v = value.strip()
        if v == "":
            return None
        if strip_ordinals:
            # "July 4th 2024" -> "July 4 2024"
            v = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", v)
        for fmt in formats:
            try:
                return datetime.strptime(v, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None  # unparseable

    df[col] = df[col].apply(parse_one)
    return df


def null_and_flag(df, col, params):
    """Null out listed values (or out-of-range dates) and record a flag column."""
    flag_col = params.get("flag_column", f"{col}_flag")
    flag_val = params.get("flag_value", "flagged")
    if flag_col not in df.columns:
        df[flag_col] = ""

    listed = set(params.get("values", []))

    def check(value):
        v = (value or "")
        # explicit value match (covers blanks and literal bad values)
        if v in listed or v.strip() == "" and "" in listed:
            return True
        # date range check (values are ISO by now if this ran after parsing)
        if params.get("rule", "").startswith("outside"):
            try:
                d = datetime.strptime(v, "%Y-%m-%d")
                return d < EXPECTED_MIN or d > EXPECTED_MAX
            except (ValueError, TypeError):
                return False
        return False

    for idx, value in df[col].items():
        if check(value):
            df.at[idx, flag_col] = flag_val
            df.at[idx, col] = None
    return df


def to_boolean(df, col, params):
    """Map many string reps to real True/False."""
    true_vals = set(params.get("true_values", []))
    false_vals = set(params.get("false_values", []))

    def convert(v):
        s = (v or "").strip()
        if s in true_vals:
            return True
        if s in false_vals:
            return False
        return None

    df[col] = df[col].apply(convert)
    return df


def mask(df, col, params):
    """Mask a sensitive column. 'last4' keeps only the last 4 chars."""
    style = params.get("style", "full")

    def do_mask(v):
        s = v or ""
        if style == "last4":
            return ("*" * max(0, len(s) - 4)) + s[-4:] if len(s) > 4 else s
        return "*" * len(s)

    df[col] = df[col].apply(do_mask)
    return df


def fill_null(df, col, params):
    """Optional imputation — only runs if the recipe explicitly includes it."""
    strategy = params.get("strategy")
    if strategy == "zero":
        df[col] = df[col].apply(lambda v: v if (v or "").strip() != "" else "0")
    return df


# the dispatch table: action name -> function
ACTIONS = {
    "fix_spelling": fix_spelling,
    "standardize_state": standardize_state,
    "parse_date_to_iso": parse_date_to_iso,
    "null_and_flag": null_and_flag,
    "to_boolean": to_boolean,
    "mask": mask,
    "fill_null": fill_null,
}


# ---------- run the recipe ----------

def run_recipe(df, recipe_obj):
    """Apply each recipe step in order. Steps that must run later
    (e.g. null_and_flag with run_after) are deferred to a second pass."""
    steps = recipe_obj.get("recipe", [])

    # simple two-pass ordering: anything with run_after goes last
    first_pass = [s for s in steps if "run_after" not in s.get("params", {})]
    second_pass = [s for s in steps if "run_after" in s.get("params", {})]

    for step in first_pass + second_pass:
        action = step["action"]
        col = step["column"]
        params = step.get("params", {})
        fn = ACTIONS.get(action)
        if fn is None:
            print(f"  ! Unknown action '{action}' — skipped.")
            continue
        print(f"  applying: {col} -> {action}")
        df = fn(df, col, params)

    return df


def main():
    print("Loading recipe and raw data...")
    recipe_obj = load_recipe()
    df = load_data()
    print(f"Raw data: {len(df)} rows, {len(df.columns)} columns.\n")

    print("Executing recipe (pandas only, no AI):")
    df = run_recipe(df, recipe_obj)

    os.makedirs("output", exist_ok=True)
    out_path = "output/cleaned_banks.csv"
    df.to_csv(out_path, index=False)

    print(f"\nClean data written to {out_path}")
    print(f"Final shape: {len(df)} rows, {len(df.columns)} columns.")
    print("\nPreview:")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
