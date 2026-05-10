# auto — Claude Code Permission Auto-Clicker

> Never manually press **Yes** on a Claude Code permission prompt again.

`auto` wraps any Claude CLI session and automatically accepts all permission prompts in the background — even while you're working on a completely different workspace.

![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-blue)
![Python](https://img.shields.io/badge/python-3.8%2B-green)
![Tests](https://img.shields.io/badge/tests-55%2F55%20passed-brightgreen)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## Install in 30 seconds

```bash
git clone https://github.com/Mohamedattiadev/auto-claude.git
cd auto-claude
python3 install.py
```

Restart your terminal. Done.

> **Windows?** Run `python install.py` in CMD or PowerShell. If prompted, install the one dependency: `pip install wexpect`

---

## Usage

Replace `claude` with `auto claude` — that's it.

```bash
# Start a new session
auto claude

# Resume a previous session
auto claude --resume 7980f143-df57-4945-94ba-ca71cd425dd5

# Skip permissions entirely (Claude's built-in flag)
auto claude --dangerously-skip-permissions
```

Works in **bash**, **zsh**, **fish**, **ksh**, **PowerShell**, **CMD**, and any other terminal.

---

## What it does

Claude Code CLI shows permission prompts like these dozens of times per session:

```
Do you want to create config.json?
❯ 1. Yes
  2. Yes, allow all edits during this session  (shift+tab)
  3. No

Esc to cancel · Tab to amend
```

```
Allow access to /etc/passwd? (y/N)
```

```
Approve? [y/N]
```

`auto` intercepts all of these at the operating system level and responds instantly — **without touching your keyboard, without switching workspaces, without interrupting your flow**.

---

## How it works

`auto` runs Claude inside a **Pseudo-Terminal (PTY)** — a fake terminal that the OS creates to perfectly mimic a real one. This means:

- Claude thinks it's talking to a real terminal (full color, animations, resizing — all work perfectly)
- `auto` reads every character Claude prints, strips invisible formatting codes, and scans for prompt patterns
- When a permission prompt is detected, it sends the correct keypress (`y` + Enter, or just Enter for menus)
- You stay on your current workspace — it all happens in the background at the process level

---

<div align="center">

### 🚧 Repository under active maintenance 🚧

</div>

---

## Supported prompt types

| Pattern | Example | Action |
|---|---|---|
| `[y/N]` brackets | `Approve? [y/N]` | Types `y` |
| `[Y/n]` brackets | `Overwrite? [Y/n]` | Types `y` |
| `(y/N)` parens | `Allow access? (y/N)` | Types `y` |
| `(y/n)` parens | `Continue? (y/n)` | Types `y` |
| `Allow?` plain | `Allow?` | Types `y` |
| `Do you want to...` menu | `❯ 1. Yes` | Presses Enter |
| `Press Enter to continue` | — | Presses Enter |

Prompts are detected even if they arrive split across multiple data chunks (a real edge case in PTY streams).

---

## Platform support

| Platform | Method | Dependencies |
|---|---|---|
| Linux (any distro) | Native `pty` | None |
| macOS | Native `pty` | None |
| Windows (CMD / PowerShell) | `wexpect` | `pip install wexpect` |
| WSL on Windows | Native `pty` | None |

---

## Uninstall

```bash
python3 install.py --uninstall
```

---

## Test results

The project ships with a 55-test suite covering every known prompt variant.

### Cross-platform unit tests (`tests/test_cross_platform.py`)
Runs on **any OS** — no PTY required.

```
============================================================
 CLAUDE_AUTO Cross-Platform Unit Tests
 Running on: Linux (linux)
 Python:     3.13.11
============================================================

── Y/N — Bracket Variants ──
[PASS] 01 [y/N] with ANSI jumps
[PASS] 02 [Y/n] with ANSI jumps
[PASS] 03 [y/n] lowercase
[PASS] 04 [Y/N] uppercase
[PASS] 05 Approve? [y/N]
[PASS] 06 Allow?

── Y/N — Parenthesis Variants ──
[PASS] 07 (y/N) paren
[PASS] 08 (Y/n) paren
[PASS] 09 (y/n) both lower

── Y/N — With Real Spaces ──
[PASS] 10 [y/N] real spaces
[PASS] 11 Allow? real spaces
[PASS] 12 (y/N) real spaces

── Y/N — Real-World Claude Prompts ──
[PASS] 13 Allow /etc/passwd
[PASS] 14 Allow ~/.ssh (y/N)
[PASS] 15 Apply patch [y/N]
[PASS] 16 Install deps (y/N)
[PASS] 17 Fix issues [y/N]
[PASS] 18 Override cache [Y/n]

── Y/N — After Long Preamble (Accumulated Buffer) ──
[PASS] 19 [y/N] after long preamble

── Menu — 'Do you want to...' Variants ──
[PASS] 20 proceed?
[PASS] 21 create file
[PASS] 22 run bash cmd
[PASS] 23 delete file
[PASS] 24 modify file
[PASS] 25 write file
[PASS] 26 overwrite file
[PASS] 27 execute script
[PASS] 28 install package
[PASS] 29 remove directory
[PASS] 30 rename file
[PASS] 31 move file
[PASS] 32 copy file
[PASS] 33 patch file
[PASS] 34 reset git
[PASS] 35 deploy app

── Menu — Real Spaces ──
[PASS] 36 proceed? real spaces
[PASS] 37 create real spaces

── Menu — Multi-Option ──
[PASS] 38 4-option menu
[PASS] 39 2-option menu

── Press Enter Prompts ──
[PASS] 40 Press Enter ANSI
[PASS] 41 Press Enter spaces

── Menu — Deep File Paths ──
[PASS] 42 deep path
[PASS] 43 path with spaces
[PASS] 44 long filename

── Edge Cases — No False Positives ──
[PASS] 45 plain text no trigger
[PASS] 46 partial word 'allow'
[PASS] 47 number 1 in text
[PASS] 48 word 'yes' in sentence

── Edge Cases — Split Buffers (Accumulated) ──
[PASS] 49 Prompt split across two chunks
[PASS] 50 [y/N] split across two chunks

── Stress: Rapid Unique Prompts ──
[PASS] 51 rapid Allow?
[PASS] 52 rapid [y/N]
[PASS] 53 rapid proceed menu
[PASS] 54 rapid create menu
[PASS] 55 rapid (y/N)

============================================================
 RESULTS ON Linux (linux): 55/55 PASSED
 ✓ ALL 55 TESTS PASSED — 100% cross-platform ready!
============================================================
```

### Run tests yourself

```bash
# Cross-platform unit tests (Linux / macOS / Windows — no PTY needed)
python3 tests/test_cross_platform.py

# Full PTY integration tests (Linux / macOS)
python3 claude_auto.py tests/mock_claude_comprehensive.py
```

---

## Project structure

```
auto-claude/
├── claude_auto.py          # Main script — the auto-clicker engine
├── install.py              # Universal installer (Linux / macOS / Windows)
├── README.md
└── tests/
    ├── test_cross_platform.py        # 55 unit tests — runs on any OS
    ├── mock_claude_comprehensive.py  # 55 PTY integration tests
    └── mock_claude.py                # Simple mock for manual testing
```

---

## License

MIT — free to use, modify, and distribute.
