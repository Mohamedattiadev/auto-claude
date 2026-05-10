#!/usr/bin/env python3
"""
Scan the installed `claude` binary for permission-prompt strings and diff
them against the trigger list in claude_auto.py.

Run after each Claude Code release to detect new prompts before users hit
them in the wild.

Usage:
    python3 scripts/sync-triggers.py [path/to/claude]

If no path is given, the script auto-detects via `which claude`, following
shell shims like /usr/bin/claude -> /opt/claude-code/bin/claude.
"""
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from claude_auto import (  # noqa: E402
    PROMPT_ENTER_TRIGGERS,
    PROMPT_Y_TRIGGERS,
    PRESS_ENTER_TRIGGERS,
)

# Prompt patterns to scan for. Order matters — first match wins.
PROMPT_PATTERNS = [
    re.compile(r'^Do you (want|trust)\b.{2,80}\??$'),
    re.compile(r'^Would you like to\b.{2,80}\??$'),
    re.compile(r'^Are you sure\b.{2,80}\??$'),
    re.compile(r'^Press Enter to\b.{2,80}$'),
    re.compile(r'^(Allow|Approve|Continue|Confirm|Overwrite|Enable|Disable|Remove|Delete|Trust|Exit|Stop)\b.{0,80}\?$'),
    re.compile(r'^WARNING: Claude Code\b.{2,120}$'),
]


def find_binary(arg_path):
    """Locate the real claude executable, following one level of shell shim."""
    if arg_path:
        return arg_path

    p = shutil.which("claude")
    if not p:
        return None

    try:
        with open(p, "rb") as f:
            head = f.read(4)
        # If it's a shell script, parse out the exec target.
        if head[:2] == b"#!":
            with open(p, "r", errors="ignore") as f:
                for line in f:
                    m = re.match(r"\s*exec\s+(\S+)", line)
                    if m:
                        return m.group(1)
    except Exception:
        pass
    return p


def extract_prompts(path):
    try:
        out = subprocess.check_output(
            ["strings", path], text=True, errors="ignore"
        )
    except FileNotFoundError:
        sys.stderr.write("error: `strings` not installed (binutils package).\n")
        sys.exit(2)
    except subprocess.CalledProcessError as e:
        sys.stderr.write(f"error: strings failed: {e}\n")
        sys.exit(2)

    found = set()
    for line in out.splitlines():
        line = line.rstrip()
        if not line or len(line) > 140:
            continue
        # Skip regex source strings (e.g. `Continue\?`, `Overwrite\?`) — these
        # are internal patterns Claude compiles, not prompts shown to users.
        if "\\" in line:
            continue
        for pat in PROMPT_PATTERNS:
            if pat.match(line):
                found.add(line)
                break
    return sorted(found)


def is_covered(prompt):
    """Check if a prompt would be matched by current triggers (space-stripped)."""
    norm = prompt.replace(" ", "")
    all_triggers = (
        list(PROMPT_ENTER_TRIGGERS)
        + list(PRESS_ENTER_TRIGGERS)
        + list(PROMPT_Y_TRIGGERS)
    )
    return any(t in norm for t in all_triggers)


# Prompts deliberately excluded from auto-confirm — see claude_auto.py.
EXCLUDED = (
    "Exit plan mode?",
    "Stop ultraplan?",
    "Stop ultrareview?",
)


def main():
    arg_path = sys.argv[1] if len(sys.argv) > 1 else None
    bin_path = find_binary(arg_path)
    if not bin_path or not os.path.exists(bin_path):
        sys.stderr.write("error: claude binary not found.\n")
        sys.stderr.write("  pass the path explicitly: sync-triggers.py /path/to/claude\n")
        sys.exit(1)

    print(f"Scanning {bin_path}\n")
    prompts = extract_prompts(bin_path)
    if not prompts:
        print("No matching prompt strings found — binary may be stripped or packed.")
        sys.exit(1)

    covered, missing, excluded = [], [], []
    for p in prompts:
        if p in EXCLUDED:
            excluded.append(p)
        elif is_covered(p):
            covered.append(p)
        else:
            missing.append(p)

    print(f"  covered:  {len(covered)}")
    print(f"  missing:  {len(missing)}")
    print(f"  excluded: {len(excluded)} (deliberately not auto-confirmed)")
    print()

    if missing:
        print("=== NEW PROMPTS NOT YET COVERED ===")
        for p in missing:
            print(f"  ✗ {p}")
        print("\nAdd matching triggers to PROMPT_ENTER_TRIGGERS or PROMPT_Y_TRIGGERS")
        print("in claude_auto.py, then add a regression test.\n")
    else:
        print("✓ all detected prompts are covered.")

    if excluded:
        print("\n=== EXCLUDED (not auto-confirmed by design) ===")
        for p in excluded:
            print(f"  - {p}")

    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
