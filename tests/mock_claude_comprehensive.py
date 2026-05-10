#!/usr/bin/env python3
"""
MEGA test suite for claude_auto.py — 55 tests covering every
known Claude CLI prompt variant, edge cases, and stress scenarios.

Usage:
    python3 claude_auto.py ./mock_claude_comprehensive.py
"""
import sys
import time
import termios
import tty
import os
import select

PASS = 0
FAIL = 0

def write_ansi(text):
    """Simulate Claude CLI: replace spaces with ANSI cursor-right jumps."""
    sys.stdout.write(text.replace(" ", "\x1b[1C"))
    sys.stdout.flush()

def write_raw(text):
    """Write text with real spaces (for edge-case testing)."""
    sys.stdout.write(text)
    sys.stdout.flush()

def drain(timeout=0.08):
    """Drain any leftover characters from stdin."""
    while True:
        r, _, _ = select.select([sys.stdin], [], [], timeout)
        if not r:
            break
        os.read(sys.stdin.fileno(), 256)

def read_one():
    """Read exactly one meaningful character."""
    while True:
        c = os.read(sys.stdin.fileno(), 1).decode('utf-8', errors='ignore')
        if c:
            return c

def test_y(label, prompt_text, use_ansi=True):
    """Assert that the auto-clicker sends 'y' in response to this prompt."""
    global PASS, FAIL
    drain()
    if use_ansi:
        write_ansi(prompt_text + "\r\n")
    else:
        write_raw(prompt_text + "\r\n")
    ans = read_one()
    drain()
    if ans.lower() == 'y':
        sys.stdout.write(f"\x1b[32m[PASS]\x1b[0m {label}\r\n")
        PASS += 1
    else:
        sys.stdout.write(f"\x1b[31m[FAIL]\x1b[0m {label}: expected 'y', got {repr(ans)}\r\n")
        FAIL += 1

def test_enter(label, prompt_text, options, use_ansi=True, pause=0.0):
    """Assert that the auto-clicker presses Enter for a menu prompt."""
    global PASS, FAIL
    drain()
    if pause:
        time.sleep(pause)
    if use_ansi:
        write_ansi(prompt_text + "\r\n")
    else:
        write_raw(prompt_text + "\r\n")
    for i, opt in enumerate(options):
        prefix = "\x1b[32m\xe2\x9d\xaf\x1b[0m " if i == 0 else "  "
        if use_ansi:
            write_ansi(prefix + str(i+1) + ". " + opt + "\r\n")
        else:
            write_raw(prefix + str(i+1) + ". " + opt + "\r\n")
    sys.stdout.flush()
    ans = read_one()
    drain()
    if ans in ('\r', '\n'):
        sys.stdout.write(f"\x1b[32m[PASS]\x1b[0m {label}\r\n")
        PASS += 1
    else:
        sys.stdout.write(f"\x1b[31m[FAIL]\x1b[0m {label}: expected Enter, got {repr(ans)}\r\n")
        FAIL += 1

def section(title):
    sys.stdout.write(f"\r\n\x1b[33m── {title} ──\x1b[0m\r\n")

def main():
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        sys.stdout.write("\r\n\x1b[1m=== CLAUDE_AUTO.PY — 55 PROMPT TEST SUITE ===\x1b[0m\r\n\r\n")
        time.sleep(0.3)

        # ─────────────────────────────────────────
        # BLOCK 1: Y/N bracket variants
        # ─────────────────────────────────────────
        section("BLOCK 1: Y/N Bracket Variants")
        test_y("01 [y/N] standard",           "Continue? [y/N]")
        test_y("02 [Y/n] inverted",            "Continue? [Y/n]")
        test_y("03 [y/n] both lower",          "Continue? [y/n]")
        test_y("04 [Y/N] both upper",          "Continue? [Y/N]")
        test_y("05 Approve?[y/N] compact",     "Approve? [y/N]")
        test_y("06 Allow? plain",              "Allow?")

        # ─────────────────────────────────────────
        # BLOCK 2: Y/N parenthesis variants
        # ─────────────────────────────────────────
        section("BLOCK 2: Y/N Parenthesis Variants")
        test_y("07 (y/N) paren",              "Confirm? (y/N)")
        test_y("08 (Y/n) paren",              "Confirm? (Y/n)")
        test_y("09 (y/n) paren lower",        "Confirm? (y/n)")

        # ─────────────────────────────────────────
        # BLOCK 3: Y/N with real-world context
        # ─────────────────────────────────────────
        section("BLOCK 3: Y/N in Real-World Context")
        test_y("10 Allow access (y/N)",        "Allow access to /etc/passwd? (y/N)")
        test_y("11 Allow read file (y/N)",     "Allow read of ~/.ssh/id_rsa? (y/N)")
        test_y("12 Allow write file [y/N]",    "Allow write to /usr/local/bin? [y/N]")
        test_y("13 Allow network (y/N)",       "Allow network access? (y/N)")
        test_y("14 Allow shell (y/N)",         "Allow shell execution? (y/N)")
        test_y("15 Proceed? (y/N)",            "Proceed with changes? (y/N)")
        test_y("16 Apply patch? [y/N]",        "Apply this patch? [y/N]")
        test_y("17 Install deps? (y/N)",       "Install dependencies? (y/N)")

        # ─────────────────────────────────────────
        # BLOCK 4: Y/N with long preamble
        # ─────────────────────────────────────────
        section("BLOCK 4: Y/N After Long Output")
        write_ansi("Reading 1000 files...\r\n")
        write_ansi("Analyzing code...\r\n")
        write_ansi("Found 42 issues.\r\n")
        test_y("18 [y/N] after long preamble", "Fix all issues? [y/N]")

        write_ansi("Compiling project...\r\n" * 5)
        test_y("19 [Y/n] after repeated output","Override cache? [Y/n]")

        # ─────────────────────────────────────────
        # BLOCK 5: Y/N with real spaces (not ANSI jumps)
        # ─────────────────────────────────────────
        section("BLOCK 5: Y/N With Real Spaces")
        test_y("20 [y/N] real spaces",         "Approve? [y/N]", use_ansi=False)
        test_y("21 Allow? real spaces",        "Allow?",         use_ansi=False)
        test_y("22 (y/n) real spaces",         "Sure? (y/n)",    use_ansi=False)

        # separator between Y and menu tests
        time.sleep(0.6)
        drain()

        # ─────────────────────────────────────────
        # BLOCK 6: "Do you want to..." menu prompts
        # ─────────────────────────────────────────
        section("BLOCK 6: Do You Want To... Menu Prompts")
        test_enter("23 proceed?",              "Do you want to proceed?",
                   ["Yes", "Yes, and allow access", "No"])
        test_enter("24 create file",           "Do you want to create config.json?",
                   ["Yes", "Yes, allow all edits (shift+tab)", "No"])
        test_enter("25 run bash cmd",          "Do you want to run bash command `ls -la`?",
                   ["Yes", "No"])
        test_enter("26 delete file",           "Do you want to delete old_file.txt?",
                   ["Yes", "No"])
        test_enter("27 modify file",           "Do you want to modify package.json?",
                   ["Yes", "Yes, allow all edits", "No"])
        test_enter("28 update file",           "Do you want to update README.md?",
                   ["Yes", "No"])
        test_enter("29 write file",            "Do you want to write to output.log?",
                   ["Yes", "No"])
        test_enter("30 overwrite file",        "Do you want to overwrite dist/bundle.js?",
                   ["Yes", "No"])
        test_enter("31 execute script",        "Do you want to execute setup.sh?",
                   ["Yes", "No"])
        test_enter("32 install package",       "Do you want to install lodash?",
                   ["Yes", "No"])
        test_enter("33 remove directory",      "Do you want to remove node_modules/?",
                   ["Yes", "No"])
        test_enter("34 read file",             "Do you want to read .env?",
                   ["Yes", "No"])
        test_enter("35 rename file",           "Do you want to rename app.js to index.js?",
                   ["Yes", "No"])
        test_enter("36 move file",             "Do you want to move src/ to lib/?",
                   ["Yes", "No"])
        test_enter("37 copy file",             "Do you want to copy template.html?",
                   ["Yes", "No"])
        test_enter("38 patch file",            "Do you want to patch Makefile?",
                   ["Yes", "No"])
        test_enter("39 reset git",             "Do you want to reset the git history?",
                   ["Yes", "No"])
        test_enter("40 push changes",          "Do you want to push changes to origin?",
                   ["Yes", "No"])
        test_enter("41 deploy app",            "Do you want to deploy the application?",
                   ["Yes", "No"])

        # ─────────────────────────────────────────
        # BLOCK 7: Menus with many options
        # ─────────────────────────────────────────
        section("BLOCK 7: Menus With Many Options")
        test_enter("42 4-option menu",         "Do you want to proceed?",
                   ["Yes", "Yes, allow all edits (shift+tab)",
                    "Yes, and allow access to bin/ folder",
                    "No"])
        test_enter("43 2-option menu",         "Do you want to create test.txt?",
                   ["Yes", "No"])
        test_enter("44 deep path menu",        "Do you want to write to /home/user/.config/app/settings.json?",
                   ["Yes", "No"])

        # ─────────────────────────────────────────
        # BLOCK 8: "Press Enter to continue"
        # ─────────────────────────────────────────
        section("BLOCK 8: Press Enter Prompts")
        test_enter("45 Press Enter to continue",       "Press Enter to continue", [])
        test_enter("46 Press Enter real spaces",       "Press Enter to continue", [], use_ansi=False)

        # ─────────────────────────────────────────
        # BLOCK 9: Rapid-fire stress tests
        # ─────────────────────────────────────────
        section("BLOCK 9: Rapid-Fire Stress Tests")
        time.sleep(0.5)  # drain any leftover \r from menu block
        drain()
        for i in range(47, 52):
            test_y(f"{i} rapid Y/N #{i-46}", f"Quick confirm #{i-46}? [y/N]")

        # ─────────────────────────────────────────
        # BLOCK 10: Edge cases
        # ─────────────────────────────────────────
        section("BLOCK 10: Edge Cases")
        time.sleep(0.5)
        drain()
        test_enter("52 menu after Y block bleed",     "Do you want to proceed?",
                   ["Yes", "No"])
        test_enter("53 long filename in prompt",      "Do you want to create very-long-filename-that-exceeds-normal-limits-2024.min.js?",
                   ["Yes", "No"])
        test_enter("54 spaces in filename",           "Do you want to modify My Project File.txt?",
                   ["Yes", "No"])
        test_y(    "55 Allow at end of sentence",    "Access requires your approval. Allow?")

        # ─────────────────────────────────────────
        # FINAL SUMMARY
        # ─────────────────────────────────────────
        total = PASS + FAIL
        sys.stdout.write(f"\r\n\x1b[1m=== FINAL RESULTS: {PASS}/{total} PASSED ===\x1b[0m\r\n")
        if FAIL == 0:
            sys.stdout.write("\x1b[32m✓ ALL 55 TESTS PASSED — Script is 100% ready!\x1b[0m\r\n")
        else:
            sys.stdout.write(f"\x1b[31m✗ {FAIL} test(s) FAILED — see above for details.\x1b[0m\r\n")

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

if __name__ == "__main__":
    main()
