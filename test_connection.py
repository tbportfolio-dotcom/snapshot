"""
test_connection.py — Snapshot: first-light check.
Proves your API key works and the pipe to Claude is connected.
Run this ONCE before building anything else. If it prints a reply, you're good.
"""

import os
from dotenv import load_dotenv
import anthropic

# Load the key from .env into the environment
load_dotenv()

api_key = os.getenv("ANTHROPIC_API_KEY")

# --- sanity checks before we even call out ---
if not api_key:
    raise SystemExit("No ANTHROPIC_API_KEY found. Is your .env file set up?")
if not api_key.startswith("sk-ant-"):
    raise SystemExit("Key doesn't start with 'sk-ant-'. That's not a Claude API key.")

print("Key loaded. Calling Claude...\n")

# The one and only 'AI' line — everything else is plain Python
client = anthropic.Anthropic(api_key=api_key)

response = client.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=100,
    messages=[
        {"role": "user", "content": "Reply with exactly: Snapshot is connected and ready."}
    ],
)

print("Claude says:", response.content[0].text)
print("\nPipe confirmed. We're ready to build.")
