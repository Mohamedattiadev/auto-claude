#!/usr/bin/env python3
"""Internal-helper tests — ANSI strip, raw-buffer trim, arg parsing,
signature stability, response shape. Cross-platform, no PTY required.
"""
import codecs
import contextlib
import io
import os
import random
import stat
import sys
import tempfile
import unittest
import unittest.mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_auto import (
    ANSI_ESCAPE,
    MENU_INDICATOR,
    PROMPT_ENTER_TRIGGERS,
    PROMPT_Y_TRIGGERS,
    PRESS_ENTER_TRIGGERS,
    TAIL_WINDOW,
    THROTTLE_SIG_LEN,
    _build_opts,
    _fire_signature,
    _open_log,
    _parse_args,
    _trim_raw_buffer,
    process_buffer,
    __version__,
)


def strip(text):
    return ANSI_ESCAPE.sub("", text).replace(" ", "")


class TestAnsiEscape(unittest.TestCase):
    def test_csi_cursor_forward_stripped(self):
        self.assertEqual(ANSI_ESCAPE.sub("", "Foo\x1b[1Cbar"), "Foobar")

    def test_csi_sgr_color_stripped(self):
        self.assertEqual(ANSI_ESCAPE.sub("", "\x1b[31mred\x1b[0m"), "red")

    def test_osc_terminal_title_stripped_bel(self):
        # OSC 0 ; title BEL — sets terminal title. Common content has trigger phrases.
        s = "\x1b]0;Do you want to proceed?\x07actual prompt"
        self.assertEqual(ANSI_ESCAPE.sub("", s), "actual prompt")

    def test_osc_hyperlink_stripped_st(self):
        # OSC 8 ; ; URL ST text OSC 8 ; ; ST — terminal hyperlink.
        s = "\x1b]8;;https://x.com\x1b\\link\x1b]8;;\x1b\\"
        self.assertEqual(ANSI_ESCAPE.sub("", s), "link")

    def test_dcs_sequence_stripped(self):
        s = "before\x1bPdevice-control-string\x1b\\after"
        self.assertEqual(ANSI_ESCAPE.sub("", s), "beforeafter")

    def test_apc_sequence_stripped(self):
        s = "x\x1b_application-cmd\x1b\\y"
        self.assertEqual(ANSI_ESCAPE.sub("", s), "xy")

    def test_single_char_esc_stripped(self):
        self.assertEqual(ANSI_ESCAPE.sub("", "x\x1bMy"), "xy")

    def test_terminal_title_does_not_false_fire(self):
        """Trigger phrase inside OSC title must not fire — gets stripped."""
        text = "\x1b]0;Do you want to proceed?\x07I am working..."
        buf = strip(text)
        _, trig, _ = process_buffer(buf, None)
        self.assertFalse(trig)

    def test_hyperlink_title_does_not_false_fire(self):
        text = "\x1b]8;;file:///x?[y/N]\x1b\\hello\x1b]8;;\x1b\\"
        buf = strip(text)
        _, trig, _ = process_buffer(buf, None)
        self.assertFalse(trig)


class TestTrimRawBuffer(unittest.TestCase):
    def test_short_buffer_unchanged(self):
        s = "short"
        self.assertEqual(_trim_raw_buffer(s), s)

    def test_huge_buffer_trimmed_to_target(self):
        s = "a" * 20000
        out = _trim_raw_buffer(s, soft_max=8192, target=4096)
        self.assertLessEqual(len(out), 4096)

    def test_trim_prefers_newline_boundary(self):
        head = "garbage" * 2000  # ~14000 chars — exceeds soft_max
        body = "\nclean line one\nclean line two\n"
        out = _trim_raw_buffer(head + body, soft_max=8192, target=4096)
        # Whatever survives must start cleanly after a newline, not
        # mid-CSI like "[1Cfoo".
        self.assertFalse(out.startswith("garbage"))

    def test_trim_no_newline_falls_back_to_target(self):
        s = "x" * 20000
        out = _trim_raw_buffer(s, soft_max=8192, target=4096)
        self.assertEqual(len(out), 4096)


class TestUtf8Decoder(unittest.TestCase):
    """Multi-byte UTF-8 split across read() chunks must reassemble cleanly."""

    def test_utf8_split_two_byte(self):
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        # "é" = 0xC3 0xA9 split across reads
        first = decoder.decode(b"\xc3")
        second = decoder.decode(b"\xa9")
        self.assertEqual(first + second, "é")

    def test_utf8_split_four_byte_emoji(self):
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        # "🚀" = 0xF0 0x9F 0x9A 0x80
        out = decoder.decode(b"\xf0\x9f") + decoder.decode(b"\x9a\x80")
        self.assertEqual(out, "🚀")

    def test_utf8_split_around_box_drawing(self):
        # ❯ = U+276F = 0xE2 0x9D 0xAF (3 bytes) — appears in claude menu.
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        out = decoder.decode(b"\xe2\x9d") + decoder.decode(b"\xaf")
        self.assertEqual(out, "❯")


class TestProcessBufferReturnShape(unittest.TestCase):
    def test_returns_tuple_of_three(self):
        r = process_buffer("nothing here", None)
        self.assertEqual(len(r), 3)

    def test_y_response_settle_is_short(self):
        _, _, settle = process_buffer("Allow?", None)
        self.assertLess(settle, 0.2)

    def test_enter_response_settle_is_longer(self):
        buf = strip("Do you want to proceed?\r\n❯ 1. Yes\r\n  2. No")
        _, _, settle = process_buffer(buf, None)
        self.assertGreaterEqual(settle, 0.3)

    def test_press_enter_priority_over_y(self):
        # Both "Press Enter" and "[y/N]" present — press-enter wins.
        buf = strip("Press Enter to continue [y/N]")
        response, _, _ = process_buffer(buf, None)
        self.assertEqual(response, b"\r")

    def test_no_trigger_returns_zero_settle(self):
        _, _, settle = process_buffer("idle", None)
        self.assertEqual(settle, 0)


class TestTailWindowBoundary(unittest.TestCase):
    def test_trigger_just_inside_tail_fires(self):
        head = "x" * (TAIL_WINDOW - 10)
        buf = head + "[y/N]"
        _, trig, _ = process_buffer(buf, None)
        self.assertTrue(trig)

    def test_trigger_just_outside_tail_does_not_fire(self):
        # [y/N] then 700 chars of unrelated text → trigger scrolled out.
        buf = "[y/N]" + ("x" * 700)
        _, trig, _ = process_buffer(buf, None)
        self.assertFalse(trig)


class TestFireSignature(unittest.TestCase):
    def test_signature_only_uses_tail(self):
        # Identical THROTTLE_SIG_LEN tail → same sig regardless of head.
        tail = "z" * THROTTLE_SIG_LEN
        a = ("a" * 1000) + tail
        b = ("b" * 1000) + tail
        self.assertEqual(_fire_signature(a), _fire_signature(b))

    def test_signature_window_size(self):
        # Different beyond THROTTLE_SIG_LEN → same sig.
        head_diff = "X" + ("z" * THROTTLE_SIG_LEN)
        head_same = "Y" + ("z" * THROTTLE_SIG_LEN)
        self.assertEqual(_fire_signature(head_diff), _fire_signature(head_same))

    def test_signature_short_buffer(self):
        # No crash on buffers shorter than the window.
        _fire_signature("")
        _fire_signature("hi")

    def test_signature_int_type(self):
        self.assertIsInstance(_fire_signature("anything"), int)


class TestParseArgs(unittest.TestCase):
    def test_multiple_skip_triggers_collected(self):
        cmd, skips, dry, _ = _parse_args(
            ["--skip-trigger", "Allow?", "--skip-trigger", "Overwrite?", "claude"]
        )
        self.assertEqual(skips, ["Allow?", "Overwrite?"])
        self.assertEqual(cmd, ["claude"])

    def test_fake_os_overrides_platform(self):
        _, _, _, plat = _parse_args(["--fake-os=win32", "echo"])
        self.assertEqual(plat, "win32")

    def test_skip_trigger_missing_arg_exits(self):
        with self.assertRaises(SystemExit) as ctx:
            _parse_args(["--skip-trigger"])
        self.assertEqual(ctx.exception.code, 2)

    def test_version_exits_zero(self):
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                _parse_args(["--version"])
        self.assertEqual(ctx.exception.code, 0)

    def test_help_exits_zero(self):
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                _parse_args(["-h"])
        self.assertEqual(ctx.exception.code, 0)

    def test_dry_run_default_false(self):
        _, _, dry, _ = _parse_args(["claude"])
        self.assertFalse(dry)

    def test_command_double_dash_passthrough(self):
        # Wrapped command with its own flags: stop consuming auto-flags.
        cmd, _, _, _ = _parse_args(["claude", "--resume", "abc-123"])
        self.assertEqual(cmd, ["claude", "--resume", "abc-123"])


class TestBuildOpts(unittest.TestCase):
    def test_build_opts_full_when_no_skips(self):
        opts = _build_opts([], False)
        self.assertEqual(len(opts["enter_triggers"]), len(PROMPT_ENTER_TRIGGERS))
        self.assertEqual(len(opts["y_triggers"]), len(PROMPT_Y_TRIGGERS))
        self.assertEqual(len(opts["press_enter_triggers"]), len(PRESS_ENTER_TRIGGERS))
        self.assertFalse(opts["dry_run"])

    def test_build_opts_dry_run_propagates(self):
        opts = _build_opts([], True)
        self.assertTrue(opts["dry_run"])

    def test_build_opts_skips_press_enter(self):
        opts = _build_opts(["PressEntertocontinue"], False)
        self.assertNotIn("PressEntertocontinue", opts["press_enter_triggers"])

    def test_press_enter_triggers_is_tuple_for_immutability(self):
        opts = _build_opts([], False)
        self.assertIsInstance(opts["press_enter_triggers"], tuple)


class TestVersion(unittest.TestCase):
    def test_version_string_format(self):
        import re
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")


class TestNoFalseFire(unittest.TestCase):
    """Cases that historically produced false fires."""

    def test_empty_buffer(self):
        _, trig, _ = process_buffer("", None)
        self.assertFalse(trig)

    def test_only_whitespace(self):
        _, trig, _ = process_buffer("   \n\t  ", None)
        self.assertFalse(trig)

    def test_lone_question_mark(self):
        _, trig, _ = process_buffer("?", None)
        self.assertFalse(trig)

    def test_yn_inside_code_block_no_menu_fires_y(self):
        # "[y/N]" anywhere in tail fires y — by design, no menu gating.
        # Documents current behavior so regression is visible.
        _, trig, _ = process_buffer("example: [y/N]", None)
        self.assertTrue(trig)

    def test_menu_indicator_alone_no_question(self):
        # "1.Yes" alone without any "Do you want..." trigger → no fire.
        buf = strip("Some output 1. Yes here")
        _, trig, _ = process_buffer(buf, None)
        self.assertFalse(trig)

    def test_destructive_exit_plan_does_not_fire(self):
        buf = strip("Exit plan mode?\r\n❯ 1. Yes\r\n  2. No")
        _, trig, _ = process_buffer(buf, None)
        self.assertFalse(trig)


class TestOpenLog(unittest.TestCase):
    """_open_log — secure log creation in XDG cache dir."""

    def test_creates_log_with_mode_0600(self):
        with tempfile.TemporaryDirectory() as td:
            with unittest.mock.patch.dict(os.environ, {"XDG_CACHE_HOME": td}):
                f = _open_log()
                try:
                    self.assertIsNotNone(f)
                    log_path = os.path.join(td, "claude_auto", "claude_auto.log")
                    self.assertTrue(os.path.exists(log_path))
                    if os.name == "posix":
                        mode = stat.S_IMODE(os.stat(log_path).st_mode)
                        self.assertEqual(mode, 0o600)
                finally:
                    if f:
                        f.close()

    def test_returns_none_when_dir_unwritable(self):
        # Point XDG_CACHE_HOME at a path that can't be created (a regular file).
        with tempfile.NamedTemporaryFile() as nf:
            with unittest.mock.patch.dict(os.environ, {"XDG_CACHE_HOME": nf.name}):
                f = _open_log()
                self.assertIsNone(f)

    def test_truncates_existing_log(self):
        with tempfile.TemporaryDirectory() as td:
            cache = os.path.join(td, "claude_auto")
            os.makedirs(cache)
            log_path = os.path.join(cache, "claude_auto.log")
            with open(log_path, "w") as preset:
                preset.write("OLD CONTENT\n")
            with unittest.mock.patch.dict(os.environ, {"XDG_CACHE_HOME": td}):
                f = _open_log()
                try:
                    self.assertIsNotNone(f)
                    f.write("new\n")
                    f.flush()
                    with open(log_path) as r:
                        content = r.read()
                    self.assertEqual(content, "new\n")
                finally:
                    if f:
                        f.close()

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW") and os.name == "posix",
                         "O_NOFOLLOW POSIX only")
    def test_refuses_symlink_target(self):
        with tempfile.TemporaryDirectory() as td:
            cache = os.path.join(td, "claude_auto")
            os.makedirs(cache)
            log_path = os.path.join(cache, "claude_auto.log")
            sink = os.path.join(td, "elsewhere")
            with open(sink, "w"):
                pass
            os.symlink(sink, log_path)
            with unittest.mock.patch.dict(os.environ, {"XDG_CACHE_HOME": td}):
                f = _open_log()
                # O_NOFOLLOW makes symlink open fail → returns None.
                self.assertIsNone(f)


class TestProcessBufferFuzz(unittest.TestCase):
    """Random garbage must never crash process_buffer."""

    def test_random_bytes_no_crash(self):
        rng = random.Random(0xC0FFEE)
        for _ in range(500):
            n = rng.randint(0, 2000)
            blob = bytes(rng.randint(0, 255) for _ in range(n))
            text = blob.decode("utf-8", errors="replace")
            cleaned = ANSI_ESCAPE.sub("", text).replace(" ", "")
            response, triggered, settle = process_buffer(cleaned, None)
            self.assertIsInstance(triggered, bool)
            if triggered:
                self.assertIn(response, (b"y\r", b"\r"))
            else:
                self.assertIsNone(response)

    def test_random_ansi_garbage_no_crash(self):
        rng = random.Random(0xFEEDFACE)
        for _ in range(200):
            chunks = []
            for _ in range(rng.randint(0, 30)):
                chunks.append("\x1b[" + str(rng.randint(0, 99)) + "C")
                chunks.append("".join(chr(rng.randint(32, 126))
                                      for _ in range(rng.randint(0, 50))))
            text = "".join(chunks)
            cleaned = ANSI_ESCAPE.sub("", text).replace(" ", "")
            process_buffer(cleaned, None)

    def test_pathological_long_input(self):
        # 1 MB of unrelated data — must complete fast and not fire.
        big = "lorem ipsum dolor sit amet " * 40000
        cleaned = ANSI_ESCAPE.sub("", big).replace(" ", "")
        _, trig, _ = process_buffer(cleaned, None)
        self.assertFalse(trig)


class TestTrimRawBufferStability(unittest.TestCase):
    """Repeated trims converge — buffer stays bounded under stress."""

    def test_repeated_appends_stay_bounded(self):
        buf = ""
        for _ in range(200):
            buf = _trim_raw_buffer(buf + ("x" * 500))
            self.assertLessEqual(len(buf), 8192)

    def test_trim_preserves_tail_content(self):
        head = "h" * 10000
        marker = "MARKER_AT_END\n"
        out = _trim_raw_buffer(head + marker)
        self.assertIn("MARKER_AT_END", out)


class TestSkipTriggerCoverage(unittest.TestCase):
    """--skip-trigger must work for every trigger category."""

    def test_skip_y_trigger(self):
        opts = _build_opts(["[y/N]"], False)
        self.assertNotIn("[y/N]", opts["y_triggers"])
        # Other variants still present.
        self.assertIn("[Y/n]", opts["y_triggers"])

    def test_skip_press_enter_trigger(self):
        opts = _build_opts(["PressEntertocontinue"], False)
        self.assertNotIn("PressEntertocontinue", opts["press_enter_triggers"])
        self.assertIn("PressEntertotryagain", opts["press_enter_triggers"])

    def test_skipping_y_trigger_silences_y_prompt(self):
        opts = _build_opts(["[y/N]"], False)
        buf = "Continue?[y/N]"
        _, trig, _ = process_buffer(
            buf, None,
            y_triggers=opts["y_triggers"],
        )
        # Other y triggers absent → no fire.
        self.assertFalse(trig)

    def test_skipping_press_enter_silences_press_enter(self):
        opts = _build_opts(["PressEntertocontinue"], False)
        buf = "PressEntertocontinue"
        _, trig, _ = process_buffer(
            buf, None,
            press_enter_triggers=opts["press_enter_triggers"],
        )
        self.assertFalse(trig)


class TestTriggerListIntegrity(unittest.TestCase):
    """Compile-time invariants on the trigger lists themselves."""

    def test_no_empty_triggers(self):
        for t in PROMPT_ENTER_TRIGGERS + PROMPT_Y_TRIGGERS + list(PRESS_ENTER_TRIGGERS):
            self.assertTrue(t)
            self.assertNotIn(" ", t, f"trigger {t!r} contains space — buffer is space-stripped")

    def test_destructive_prompts_excluded(self):
        excluded_substrings = ["Exitplanmode", "Stopultraplan", "Stopultrareview"]
        for forbidden in excluded_substrings:
            for t in PROMPT_ENTER_TRIGGERS:
                self.assertNotIn(forbidden, t,
                                 f"destructive prompt {forbidden!r} must not be auto-confirmed")

    def test_triggers_are_unique(self):
        self.assertEqual(len(PROMPT_ENTER_TRIGGERS), len(set(PROMPT_ENTER_TRIGGERS)))
        self.assertEqual(len(PROMPT_Y_TRIGGERS), len(set(PROMPT_Y_TRIGGERS)))
        self.assertEqual(len(PRESS_ENTER_TRIGGERS), len(set(PRESS_ENTER_TRIGGERS)))

    def test_press_enter_is_immutable_tuple(self):
        # Catches accidental list assignment that would make filtering at
        # runtime mutate module state.
        self.assertIsInstance(PRESS_ENTER_TRIGGERS, tuple)


class TestAnsiBoundaryCases(unittest.TestCase):
    def test_truncated_csi_at_end(self):
        # Mid-sequence at buffer end — strip leaves residue. Documents
        # current behavior so _trim_raw_buffer's newline-anchor matters.
        s = "hello\x1b[1"
        out = ANSI_ESCAPE.sub("", s)
        # No matching final byte — partial sequence stays. Caller relies
        # on _trim_raw_buffer + raw_buffer accumulation to repair next read.
        self.assertEqual(out, "hello\x1b[1")

    def test_complete_csi_with_intermediate_byte(self):
        # CSI with intermediate byte ' ' (space) before final.
        s = "x\x1b[1 qy"
        self.assertEqual(ANSI_ESCAPE.sub("", s), "xy")

    def test_nested_escapes(self):
        s = "\x1b[31m\x1b[1mbold red\x1b[0m"
        self.assertEqual(ANSI_ESCAPE.sub("", s), "bold red")

    def test_carriage_return_preserved(self):
        # \r is NOT an ANSI escape — must pass through (used by claude redraws).
        self.assertEqual(ANSI_ESCAPE.sub("", "line1\rline2"), "line1\rline2")

    def test_form_feed_preserved(self):
        self.assertEqual(ANSI_ESCAPE.sub("", "a\fb"), "a\fb")


class TestParseArgsExtra(unittest.TestCase):
    def test_skip_trigger_with_double_space_normalized(self):
        cmd, skips, _, _ = _parse_args(["--skip-trigger", "Allow ?  ", "claude"])
        self.assertEqual(skips, ["Allow?"])

    def test_fake_os_with_dry_run(self):
        cmd, skips, dry, plat = _parse_args(["--fake-os=darwin", "--dry-run", "claude"])
        self.assertEqual(plat, "darwin")
        self.assertTrue(dry)
        self.assertEqual(cmd, ["claude"])

    def test_empty_argv(self):
        cmd, skips, dry, plat = _parse_args([])
        self.assertEqual(cmd, [])
        self.assertEqual(skips, [])
        self.assertFalse(dry)


if __name__ == "__main__":
    unittest.main(verbosity=2)
