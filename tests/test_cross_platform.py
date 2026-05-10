#!/usr/bin/env python3
"""
Cross-platform unit tests for claude_auto.py

Tests the core trigger detection logic (process_buffer) which is IDENTICAL
across Linux, macOS, and Windows — no PTY required, runs everywhere.

Usage:
    python3 test_cross_platform.py
"""
import sys
import os

# Allow importing from the project root (one level up from tests/)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Import the core logic from claude_auto ──────────────────────────────────
try:
    from claude_auto import process_buffer, PROMPT_Y_TRIGGERS, PROMPT_ENTER_TRIGGERS
except ImportError as e:
    print(f"ERROR: Could not import claude_auto.py: {e}")
    sys.exit(1)

# ── Test runner ─────────────────────────────────────────────────────────────
PASS = 0
FAIL = 0

def check(label, raw_text, expected_action):
    """
    Simulate what claude_auto does with a chunk of raw terminal output.
    expected_action: 'y'  → script should type 'y'
                     'enter' → script should press Enter
                     'none'  → script should do nothing
    """
    global PASS, FAIL
    import re

    # Exactly replicates what claude_auto.py does internally
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean = ansi_escape.sub('', raw_text)
    buf = clean.replace(' ', '')

    response, triggered, _ = process_buffer(buf, None)

    if expected_action == 'y':
        ok = triggered and response == b'y\r'
    elif expected_action == 'enter':
        ok = triggered and response == b'\r'
    elif expected_action == 'none':
        ok = not triggered
    else:
        ok = False

    status = "\033[32m[PASS]\033[0m" if ok else "\033[31m[FAIL]\033[0m"
    print(f"{status} {label}")
    if ok:
        PASS += 1
    else:
        FAIL += 1
        got = 'y' if (triggered and response == b'y\r') else \
              'enter' if (triggered and response == b'\r') else 'none'
        print(f"       expected={expected_action!r}  got={got!r}  buffer={buf[:60]!r}")

def section(title):
    print(f"\n\033[33m── {title} ──\033[0m")

# ── OS DETECTION ─────────────────────────────────────────────────────────────
def detect_os():
    if sys.platform == "win32":
        return "Windows"
    elif sys.platform == "darwin":
        return "macOS"
    else:
        return f"Linux ({sys.platform})"

# ── TEST CASES ───────────────────────────────────────────────────────────────
def run_tests():
    global PASS, FAIL
    print("=" * 60)
    print(f" CLAUDE_AUTO Cross-Platform Unit Tests")
    print(f" Running on: {detect_os()}")
    print(f" Python:     {sys.version.split()[0]}")
    print("=" * 60)

    section("Y/N — Bracket Variants")
    check("01 [y/N] with ANSI jumps", "Continue?\x1b[1C[y/N]",           "y")
    check("02 [Y/n] with ANSI jumps", "Continue?\x1b[1C[Y/n]",           "y")
    check("03 [y/n] lowercase",       "Continue?\x1b[1C[y/n]",           "y")
    check("04 [Y/N] uppercase",       "Continue?\x1b[1C[Y/N]",           "y")
    check("05 Approve? [y/N]",        "Approve?\x1b[1C[y/N]",            "y")
    check("06 Allow?",                "Allow?",                           "y")

    section("Y/N — Parenthesis Variants")
    check("07 (y/N) paren",           "Confirm?\x1b[1C(y/N)",            "y")
    check("08 (Y/n) paren",           "Confirm?\x1b[1C(Y/n)",            "y")
    check("09 (y/n) both lower",      "Confirm?\x1b[1C(y/n)",            "y")

    section("Y/N — With Real Spaces")
    check("10 [y/N] real spaces",     "Approve? [y/N]",                   "y")
    check("11 Allow? real spaces",    "Allow?",                           "y")
    check("12 (y/N) real spaces",     "Sure? (y/N)",                      "y")

    section("Y/N — Real-World Claude Prompts")
    check("13 Allow /etc/passwd",     "Allow\x1b[1Caccess\x1b[1Cto\x1b[1C/etc/passwd?\x1b[1C(y/N)", "y")
    check("14 Allow ~/.ssh (y/N)",    "Allow\x1b[1Cread\x1b[1Cof\x1b[1C~/.ssh/id_rsa?\x1b[1C(y/N)", "y")
    check("15 Apply patch [y/N]",     "Apply\x1b[1Cthis\x1b[1Cpatch?\x1b[1C[y/N]",                 "y")
    check("16 Install deps (y/N)",    "Install\x1b[1Cdependencies?\x1b[1C(y/N)",                    "y")
    check("17 Fix issues [y/N]",      "Fix\x1b[1Call\x1b[1Cissues?\x1b[1C[y/N]",                   "y")
    check("18 Override cache [Y/n]",  "Override\x1b[1Ccache?\x1b[1C[Y/n]",                          "y")

    section("Y/N — After Long Preamble (Accumulated Buffer)")
    long_text = "Reading files...\r\nAnalyzing code...\r\nFound 42 issues.\r\nAllow\x1b[1Cfix?\x1b[1C[y/N]"
    check("19 [y/N] after long preamble", long_text, "y")

    section("Menu — 'Do you want to...' Variants")
    check("20 proceed?",            "Do\x1b[1Cyou\x1b[1Cwant\x1b[1Cto\x1b[1Cproceed?\r\n❯\x1b[1C1.\x1b[1CYes",  "enter")
    check("21 create file",         "Do\x1b[1Cyou\x1b[1Cwant\x1b[1Cto\x1b[1Ccreate\x1b[1Cconfig.json?\r\n❯\x1b[1C1.\x1b[1CYes", "enter")
    check("22 run bash cmd",        "Do\x1b[1Cyou\x1b[1Cwant\x1b[1Cto\x1b[1Crun\x1b[1Cbash\x1b[1Ccmd?\r\n❯\x1b[1C1.\x1b[1CYes", "enter")
    check("23 delete file",         "Do\x1b[1Cyou\x1b[1Cwant\x1b[1Cto\x1b[1Cdelete\x1b[1Cold.txt?\r\n❯\x1b[1C1.\x1b[1CYes", "enter")
    check("24 modify file",         "Do\x1b[1Cyou\x1b[1Cwant\x1b[1Cto\x1b[1Cmodify\x1b[1Cpkg.json?\r\n❯\x1b[1C1.\x1b[1CYes", "enter")
    check("25 write file",          "Do\x1b[1Cyou\x1b[1Cwant\x1b[1Cto\x1b[1Cwrite\x1b[1Cto\x1b[1Clog?\r\n❯\x1b[1C1.\x1b[1CYes", "enter")
    check("26 overwrite file",      "Do\x1b[1Cyou\x1b[1Cwant\x1b[1Cto\x1b[1Coverwrite\x1b[1Cfile?\r\n❯\x1b[1C1.\x1b[1CYes", "enter")
    check("27 execute script",      "Do\x1b[1Cyou\x1b[1Cwant\x1b[1Cto\x1b[1Cexecute\x1b[1Csetup.sh?\r\n❯\x1b[1C1.\x1b[1CYes", "enter")
    check("28 install package",     "Do\x1b[1Cyou\x1b[1Cwant\x1b[1Cto\x1b[1Cinstall\x1b[1Clodash?\r\n❯\x1b[1C1.\x1b[1CYes", "enter")
    check("29 remove directory",    "Do\x1b[1Cyou\x1b[1Cwant\x1b[1Cto\x1b[1Cremove\x1b[1Cnode_modules/?\r\n❯\x1b[1C1.\x1b[1CYes", "enter")
    check("30 rename file",         "Do\x1b[1Cyou\x1b[1Cwant\x1b[1Cto\x1b[1Crename\x1b[1Capp.js?\r\n❯\x1b[1C1.\x1b[1CYes", "enter")
    check("31 move file",           "Do\x1b[1Cyou\x1b[1Cwant\x1b[1Cto\x1b[1Cmove\x1b[1Csrc/?\r\n❯\x1b[1C1.\x1b[1CYes", "enter")
    check("32 copy file",           "Do\x1b[1Cyou\x1b[1Cwant\x1b[1Cto\x1b[1Ccopy\x1b[1Ctemplate?\r\n❯\x1b[1C1.\x1b[1CYes", "enter")
    check("33 patch file",          "Do\x1b[1Cyou\x1b[1Cwant\x1b[1Cto\x1b[1Cpatch\x1b[1CMakefile?\r\n❯\x1b[1C1.\x1b[1CYes", "enter")
    check("34 reset git",           "Do\x1b[1Cyou\x1b[1Cwant\x1b[1Cto\x1b[1Creset\x1b[1Cgit?\r\n❯\x1b[1C1.\x1b[1CYes", "enter")
    check("35 deploy app",          "Do\x1b[1Cyou\x1b[1Cwant\x1b[1Cto\x1b[1Cdeploy?\r\n❯\x1b[1C1.\x1b[1CYes", "enter")

    section("Menu — Real Spaces")
    check("36 proceed? real spaces", "Do you want to proceed?\r\n❯ 1. Yes\r\n  2. No", "enter")
    check("37 create real spaces",   "Do you want to create file.txt?\r\n❯ 1. Yes\r\n  2. No", "enter")

    section("Menu — Multi-Option")
    four_opt = "Do\x1b[1Cyou\x1b[1Cwant\x1b[1Cto\x1b[1Cproceed?\r\n❯\x1b[1C1.\x1b[1CYes\r\n2.\x1b[1CYes,allow\r\n3.\x1b[1CYes,access\r\n4.\x1b[1CNo"
    check("38 4-option menu",       four_opt, "enter")
    two_opt = "Do\x1b[1Cyou\x1b[1Cwant\x1b[1Cto\x1b[1Ccreate\x1b[1Ctest.txt?\r\n❯\x1b[1C1.\x1b[1CYes\r\n2.\x1b[1CNo"
    check("39 2-option menu",       two_opt, "enter")

    section("Press Enter Prompts")
    check("40 Press Enter ANSI",    "Press\x1b[1CEnter\x1b[1Cto\x1b[1Ccontinue", "enter")
    check("41 Press Enter spaces",  "Press Enter to continue",                    "enter")

    section("Menu — Deep File Paths")
    check("42 deep path",           "Do\x1b[1Cyou\x1b[1Cwant\x1b[1Cto\x1b[1Cwrite\x1b[1Cto\x1b[1C/home/user/.config/app/settings.json?\r\n❯\x1b[1C1.\x1b[1CYes", "enter")
    check("43 path with spaces",    "Do\x1b[1Cyou\x1b[1Cwant\x1b[1Cto\x1b[1Cmodify\x1b[1CMy\x1b[1CProject.txt?\r\n❯\x1b[1C1.\x1b[1CYes", "enter")
    check("44 long filename",       "Do\x1b[1Cyou\x1b[1Cwant\x1b[1Cto\x1b[1Ccreate\x1b[1Cvery-long-filename-2024.min.js?\r\n❯\x1b[1C1.\x1b[1CYes", "enter")

    section("Edge Cases — No False Positives")
    check("45 plain text no trigger",   "I am working on your request...",  "none")
    check("46 partial word 'allow'",    "This will allow faster execution", "none")
    check("47 number 1 in text",        "Step 1. Configure the settings",   "none")
    check("48 word 'yes' in sentence",  "Yes, I understand your request",   "none")

    section("Edge Cases — Split Buffers (Accumulated)")
    # Simulating what happens when text comes in two chunks
    chunk1 = "Do\x1b[1Cyou\x1b[1Cwant\x1b[1Cto\x1b[1Cpr"
    chunk2 = "oceed?\r\n\u276f\x1b[1C1.\x1b[1CYes"
    import re
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    buf = (ansi_escape.sub('', chunk1) + ansi_escape.sub('', chunk2)).replace(' ', '')
    r, triggered, _ = process_buffer(buf, None)
    ok = triggered and r == b'\r'
    status = "\033[32m[PASS]\033[0m" if ok else "\033[31m[FAIL]\033[0m"
    print(f"{status} 49 Prompt split across two chunks")
    if ok: PASS += 1
    else:  FAIL += 1

    chunk1 = "Approve?"
    chunk2 = "\x1b[1C[y/N]"
    buf = (ansi_escape.sub('', chunk1) + ansi_escape.sub('', chunk2)).replace(' ', '')
    r, triggered, _ = process_buffer(buf, None)
    ok = triggered and r == b'y\r'
    status = "\033[32m[PASS]\033[0m" if ok else "\033[31m[FAIL]\033[0m"
    print(f"{status} 50 [y/N] split across two chunks")
    if ok: PASS += 1
    else:  FAIL += 1

    section("Stress: Rapid Unique Prompts")
    rapid = [
        ("51 rapid Allow?",        "Allow?",                   "y"),
        ("52 rapid [y/N]",         "Fast? [y/N]",              "y"),
        ("53 rapid proceed menu",  "Do\x1b[1Cyou\x1b[1Cwant\x1b[1Cto\x1b[1Cproceed?\r\n❯\x1b[1C1.\x1b[1CYes", "enter"),
        ("54 rapid create menu",   "Do\x1b[1Cyou\x1b[1Cwant\x1b[1Cto\x1b[1Ccreate\x1b[1Ca.js?\r\n❯\x1b[1C1.\x1b[1CYes", "enter"),
        ("55 rapid (y/N)",         "Quick? (y/N)",              "y"),
    ]
    for label, text, expected in rapid:
        check(label, text, expected)

    # ── SUMMARY ──────────────────────────────────────────────────────────────
    total = PASS + FAIL
    print(f"\n{'=' * 60}")
    print(f" RESULTS ON {detect_os()}: {PASS}/{total} PASSED")
    if FAIL == 0:
        print(f"\033[32m ✓ ALL {total} TESTS PASSED — 100% cross-platform ready!\033[0m")
    else:
        print(f"\033[31m ✗ {FAIL} tests FAILED — see output above.\033[0m")
    print("=" * 60)
    return FAIL

if __name__ == "__main__":
    failures = run_tests()
    sys.exit(1 if failures else 0)
