# auto — Claude Code Permission Auto-Clicker

> Never manually press **Yes** on a Claude Code permission prompt again.

`auto` wraps any Claude CLI session and automatically accepts all permission prompts in the background — even while you're working on a completely different workspace.

![CI](https://github.com/Mohamedattiadev/auto-claude/actions/workflows/test.yml/badge.svg)
![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-blue)
![Python](https://img.shields.io/badge/python-3.8%2B-green)
![Tests](https://img.shields.io/badge/tests-89%2F89%20passed-brightgreen)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## Install

### Option A — pip (recommended)

```bash
pip install git+https://github.com/Mohamedattiadev/auto-claude.git
```

This drops `auto` and `auto-claude` on your PATH. Done.

> **Windows?** Add the wexpect extra: `pip install "auto-claude[windows] @ git+https://github.com/Mohamedattiadev/auto-claude.git"`

### Option B — bespoke installer (no pip)

```bash
git clone https://github.com/Mohamedattiadev/auto-claude.git
cd auto-claude
python3 install.py
```

Restart your terminal. Done.

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

### Auto-flags

Flags consumed by `auto` itself (must precede the wrapped command):

```bash
# Verify what would fire without actually pressing keys
auto --dry-run claude

# Disable specific triggers (repeatable, spaces ignored)
auto --skip-trigger 'Overwrite?' --skip-trigger 'Allow?' claude

# See full flag list
auto --help
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
| `Do you want to make this edit?` | `❯ 1. Yes` | Presses Enter |
| `Do you trust the files in this folder?` | `❯ 1. Yes, proceed` | Presses Enter |
| `Trust this directory?` | `❯ 1. Yes, proceed` | Presses Enter |
| `Do you want to allow Claude to fetch this content?` | `❯ 1. Yes` | Presses Enter |
| `Do you want to allow this connection?` | `❯ 1. Yes` | Presses Enter |
| `Do you want to use this API key?` | `❯ 1. Yes` | Presses Enter |
| `Would you like to install/create/proceed…?` | `❯ 1. Yes` | Presses Enter |
| `Are you sure you want to delete this permission rule?` | `❯ 1. Yes` | Presses Enter |
| `Allow external CLAUDE.md file imports?` | `❯ 1. Yes` | Presses Enter |
| `Enable auto mode?` / `Remove server?` / `Overwrite?` | `❯ 1. Yes` | Presses Enter |
| `WARNING: Bypass Permissions mode` | `❯ 1. Yes, I accept` | Presses Enter |
| `Press Enter to continue` / `Press Enter to try again` | — | Presses Enter |

Prompts are detected even if they arrive split across multiple data chunks (a real edge case in PTY streams).

### False-positive guards

`auto` ignores trigger-shaped text that isn't an actual prompt:

- **Triggers extracted from the actual `claude` binary** — strings sourced via `strings /opt/claude-code/bin/claude` against v2.1.128 ensure coverage matches what the real CLI prints, not guesswork.
- **Destructive prompts are deliberately excluded** — `Exit plan mode?`, `Stop ultraplan?`, `Stop ultrareview?` are not auto-confirmed because firing Enter would discard work.
- **Tail-anchored matching** — only the last ~600 chars of the screen are scanned, so phrases that scrolled out (or appeared in earlier prose / code blocks) won't re-fire.
- **Menu indicator gate** — `Do you want to…` only fires Enter when the rendered menu (`1. Yes`) is also on screen, so prose like *"Do you want to know more"* is ignored.
- **Extended ANSI stripping** — OSC (terminal title), DCS, APC, PM and SOS sequences are stripped alongside CSI, so a window-title update containing trigger text can't fire a key.
- **Stateful UTF-8 decoding** — multi-byte characters split across PTY reads survive intact instead of getting silently dropped.
- **Boundary-safe buffer trim** — the rolling raw buffer is trimmed at newline boundaries, never mid-escape, so no orphan `[1C` literals can leak into the matcher.

### Robustness

- **Non-TTY stdin** (piped input, `nohup`, systemd, CI) — `auto` becomes transparent and execs the target command directly instead of crashing in `termios.tcgetattr`.
- **PTY fork / exec failures** print a clear `auto: …` error instead of leaving the terminal in raw mode.
- **`SIGWINCH` during `select`** is retried instead of bubbling up as `InterruptedError`.
- **Debug log** lives at `~/.cache/claude_auto/claude_auto.log` (mode `0600`, `O_NOFOLLOW`) instead of a world-readable path in `/tmp`.
- **Signature-aware throttle** — identical fires within 500 ms are suppressed using a `(response, hash(tail))` key, so a terminal redraw cannot cause double-keypress, but two genuinely different prompts that happen to share the same response (e.g. two back-to-back `[y/N]`) are not suppressed.
- **Quiescence settle** — instead of a fixed sleep, the clicker waits until the PTY has been silent for 120 ms (capped at 600 ms) before sending the keypress, so slow-rendering menus finish painting first and the highlighted default doesn't shift mid-fire.
- **Dry-run mode** — `auto --dry-run claude` logs every fire to stderr without writing to the PTY, useful for verifying detection on an unfamiliar Claude version.
- **Per-trigger opt-out** — `auto --skip-trigger 'Overwrite?' claude` disables a specific trigger without editing source.

### Keeping triggers fresh

When Claude Code ships a new prompt string, our trigger list goes stale silently. Run the drift-detection script after each Claude release:

```bash
python3 scripts/sync-triggers.py
```

It scans the installed `claude` binary for prompt-shaped strings, normalizes them, and reports any that aren't matched by the current trigger list. Exit code is non-zero when new prompts are detected — perfect for hooking into CI.

---

## Platform support

| Platform | Method | Dependencies |
|---|---|---|
| Linux (any distro) | Native `pty` | None |
| macOS | Native `pty` | None |
| Windows (CMD / PowerShell) | `wexpect` | `pip install wexpect` |
| WSL on Windows | Native `pty` | None |

---

## Version

```bash
auto --version
# auto 0.3.0
```

---

## Uninstall

```bash
# pip install
pip uninstall auto-claude

# bespoke installer
python3 install.py --uninstall
```

---

## Test results

The project ships with a 89-test suite covering every known prompt variant plus regression tests for false-positive guards.

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
[PASS] 48a prose 'Do you want to know'
[PASS] 48b old trigger out of tail
[PASS] 48c markdown example no menu

── Real-World Prompts (from Claude Code GitHub issues) ──
[PASS] R1 'Do you want to make this edit to <file>?'
[PASS] R2 'Do you trust the files in this folder?'
[PASS] R3 'Yes, during this session' menu
[PASS] R4 'Yes, allow reading from' menu
[PASS] R5 trust phrase in prose, no menu

── Binary-Confirmed Prompts (claude v2.1.128 strings) ──
[PASS] B1 'Do you want to continue?'
[PASS] B2 'Do you want to allow Claude to fetch this content?'
[PASS] B3 'Do you want to allow this connection?'
[PASS] B4 'Do you want to use this API key?'
[PASS] B5 'Trust this directory?' (current trust prompt)
[PASS] B6 'Press Enter to try again' (variant of press-enter)
[PASS] B7 'Bypass Permissions mode' launch warning
[PASS] B8 'Yes, and allow Claude to edit its own settings' menu
[PASS] B9 'Yes, and bypass permissions' menu
[PASS] B10 'Would you like to install it?'
[PASS] B11 'Would you like to install this LSP plugin?'
[PASS] B12 'Are you sure you want to delete this permission rule?'
[PASS] B13 'Allow external CLAUDE.md file imports?'
[PASS] B14 'Enable auto mode?'
[PASS] B15 'Remove server?'
[PASS] B16 'Overwrite?' menu
[PASS] B17 'Delete it along with the plugin?'
[PASS] B18 'Exit plan mode?' must NOT fire
[PASS] B19 'Stop ultrareview?' must NOT fire

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
 RESULTS ON Linux (linux): 89/89 PASSED
 (sourced from anthropics/claude-code issues #12367, #3366, #6797, #2147)
 ✓ ALL 89 TESTS PASSED — 100% cross-platform ready!
============================================================
```

### Run tests yourself

```bash
# Cross-platform unit tests (Linux / macOS / Windows — no PTY needed)
python3 tests/test_cross_platform.py

# Real-PTY integration tests (Linux / macOS) — exercises the full run
# loop end-to-end: quiescence settle, signature throttle, ANSI strip,
# --dry-run and --skip-trigger flags.
python3 tests/test_pty_integration.py

# Drift detection — diff installed `claude` binary against trigger list.
python3 scripts/sync-triggers.py
```

CI runs the cross-platform suite on Linux / macOS / Windows × Python 3.8 / 3.11 / 3.13, and the PTY integration suite on Linux / macOS. Every push and PR is verified.

---

## Project structure

```
auto-claude/
├── claude_auto.py          # Main module — the auto-clicker engine
├── pyproject.toml          # pip install / build metadata
├── install.py              # Bespoke installer (pip-free alternative)
├── README.md
├── .github/workflows/
│   └── test.yml            # CI: Linux/macOS/Windows × Python 3.8/3.11/3.13
├── scripts/
│   └── sync-triggers.py    # Diff installed claude binary against trigger list
└── tests/
    ├── test_cross_platform.py        # 89 unit tests — runs on any OS
    ├── test_pty_integration.py       # 9 real-PTY end-to-end tests (POSIX)
    ├── _mock_target.py               # Helper used by integration tests
    ├── mock_claude_comprehensive.py  # Legacy interactive PTY harness
    └── mock_claude.py                # Simple mock for manual testing
```

---

## License

MIT — free to use, modify, and distribute.
