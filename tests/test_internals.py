#!/usr/bin/env python3
"""Internal-helper tests — ANSI strip, raw-buffer trim, arg parsing,
signature stability, response shape. Cross-platform, no PTY required.
"""
import codecs
import contextlib
import io
import os
import sys
import unittest

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
