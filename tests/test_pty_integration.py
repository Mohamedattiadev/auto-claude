#!/usr/bin/env python3
"""Real-PTY integration tests for claude_auto.py.

Spawns claude_auto.py inside a real PTY (`pty.fork`) wrapping the
mock target. The mock writes each scripted prompt to its stdout, the
auto-clicker reads it through the PTY, fires a keypress, and the mock
records what it received back on stdin.

Exercises the full run loop end-to-end — quiescence settle, signature
throttle, ANSI strip, dry-run mode, --skip-trigger — which the pure
process_buffer unit tests can't reach.

POSIX-only — pty.fork is unavailable on Windows, so the suite is
skipped there. The Windows wexpect path is verified manually.
"""
import json
import os
import pty
import select
import signal
import subprocess
import sys
import tempfile
import time
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTO = os.path.join(REPO, "claude_auto.py")
MOCK = os.path.join(REPO, "tests", "_mock_target.py")

POSIX = sys.platform != "win32"


def _drain_pty(pid, master_fd, timeout):
    """Read everything the child writes until EOF or timeout. Returns exit code."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r, _, _ = select.select([master_fd], [], [], 0.2)
        if r:
            try:
                data = os.read(master_fd, 4096)
                if not data:
                    break
            except OSError:
                break
        try:
            wpid, status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            return 0
        if wpid:
            return os.waitstatus_to_exitcode(status)
    # Timeout — kill child.
    try:
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
    except (ProcessLookupError, ChildProcessError):
        pass
    return -1


def run_auto_session(script, extra_auto_args=None, timeout=15):
    """Run auto wrapping the mock under a real PTY.
    Returns the list of strings the mock received."""
    extra_auto_args = extra_auto_args or []

    sf, script_path = tempfile.mkstemp(suffix="_script.json", prefix="auto_test_")
    rf, result_path = tempfile.mkstemp(suffix="_result.json", prefix="auto_test_")
    os.close(sf)
    os.close(rf)
    os.remove(result_path)  # mock will create it

    try:
        with open(script_path, "w") as f:
            json.dump(script, f)

        argv = [
            sys.executable, AUTO,
            *extra_auto_args,
            sys.executable, MOCK, script_path, result_path,
        ]

        pid, master_fd = pty.fork()
        if pid == 0:
            # Child — exec auto. stderr inherited so any crash surfaces.
            try:
                os.execvp(argv[0], argv)
            except Exception as e:
                sys.stderr.write(f"exec failed: {e}\n")
                os._exit(127)

        rc = _drain_pty(pid, master_fd, timeout)
        try:
            os.close(master_fd)
        except OSError:
            pass

        if not os.path.exists(result_path):
            return None, rc
        with open(result_path) as f:
            return json.load(f), rc
    finally:
        for p in (script_path, result_path):
            try:
                os.remove(p)
            except OSError:
                pass


@unittest.skipUnless(POSIX, "PTY tests are POSIX-only")
class TestPtyIntegration(unittest.TestCase):
    def test_yn_prompt_fires_y(self):
        result, rc = run_auto_session([{"prompt": "Continue? [y/N]"}])
        self.assertIsNotNone(result, "mock target produced no result file")
        self.assertEqual(len(result), 1)
        self.assertIn("y", result[0])

    def test_menu_prompt_fires_enter(self):
        result, rc = run_auto_session([
            {"prompt": "Do you want to proceed?\r\n❯ 1. Yes\r\n  2. No"},
        ])
        self.assertIsNotNone(result)
        self.assertTrue("\r" in result[0] or "\n" in result[0])

    def test_press_enter_to_continue(self):
        result, rc = run_auto_session([{"prompt": "Press Enter to continue"}])
        self.assertIsNotNone(result)
        self.assertTrue("\r" in result[0] or "\n" in result[0])

    def test_two_distinct_yn_prompts_both_fire(self):
        # Signature throttle regression — same response b"y\r" but
        # different prompts → both must fire.
        result, rc = run_auto_session([
            {"prompt": "First question? [y/N]"},
            {"prompt": "Second question? [y/N]"},
        ])
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 2)
        self.assertIn("y", result[0])
        self.assertIn("y", result[1])

    def test_no_false_fire_on_prose(self):
        # Mock waits 3 s, gets nothing, returns "".
        result, rc = run_auto_session([
            {"prompt": "Just working on your request, no prompt here..."},
        ])
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "")

    def test_no_false_fire_on_doyouwant_prose(self):
        # The trigger phrase appears but no menu rendered → must NOT fire.
        result, rc = run_auto_session([
            {"prompt": "Sometimes I'll ask: Do you want to know more about X?"},
        ])
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "")

    def test_dry_run_does_not_fire(self):
        # --dry-run logs to stderr, never writes to PTY.
        result, rc = run_auto_session(
            [{"prompt": "Continue? [y/N]"}],
            extra_auto_args=["--dry-run"],
        )
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "")

    def test_skip_trigger_silences_specific_prompt(self):
        result, rc = run_auto_session(
            [{"prompt": "Overwrite?\r\n❯ 1. Yes\r\n  2. No"}],
            extra_auto_args=["--skip-trigger", "Overwrite?"],
        )
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "")

    def test_version_flag(self):
        # --version exits before forking. Run directly via subprocess.
        out = subprocess.check_output(
            [sys.executable, AUTO, "--version"], text=True, timeout=5,
        )
        self.assertIn("auto ", out)
        self.assertRegex(out, r"\d+\.\d+\.\d+")


if __name__ == "__main__":
    if not POSIX:
        print("Skipped — PTY tests are POSIX-only.")
        sys.exit(0)
    unittest.main(verbosity=2)
