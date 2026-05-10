#!/usr/bin/env python3
import sys
import os
import time
import re
import codecs

# Universal triggers — spaces are stripped from buffer to defeat CLI cursor-jump formatting.
#
# Detection is TAIL-ANCHORED: only the last TAIL_WINDOW chars of the rolling
# buffer are scanned. Two reasons:
#   1. Real prompts always sit at the bottom of the screen waiting for input.
#      Trigger phrases that appeared earlier (in Claude's own prose, code
#      blocks, READMEs it printed, terminal title strings, etc.) must NOT
#      re-fire after they scroll out of the input region.
#   2. Bounds the false-positive window for short triggers like "Allow?".
#
# Menu (Enter) prompts are additionally gated on the actual menu having
# rendered — `1.Yes` must be present alongside the "Do you want to..." phrase.
# This kills false fires on prose like "Do you want to know more about X".
# Trigger strings sourced from the actual `claude` binary (v2.1.128) via
# `strings | grep`. Buffer has spaces stripped before matching.
PROMPT_ENTER_TRIGGERS = [
    "Doyouwanttoproceed?",
    "Doyouwanttocreate",
    "Doyouwanttorun",
    "Doyouwanttomake",          # "Do you want to make this edit to <file>?"
    "Doyouwanttocontinue?",     # "Do you want to continue?"
    "Doyouwanttoallow",         # "...allow Claude to fetch", "...allow this connection"
    "Doyouwanttouse",           # "Do you want to use this API key?"
    "Doyouwantto",              # generic catch-all
    "Doyoutrustthefiles",       # legacy "Do you trust the files in this folder?"
    "Trustthisdirectory?",      # current (2.1.x) trust prompt
    "Doyoutrust",               # catch-all for trust dialogs
    "BypassPermissionsmode",    # --dangerously-skip-permissions launch warning
    "Wouldyouliketo",           # "Would you like to install/create/proceed..."
    "Areyousureyouwantto",      # "Are you sure you want to delete this permission rule?"
    "AllowexternalCLAUDE.md",   # "Allow external CLAUDE.md file imports?"
    "Enableautomode?",
    "Removedirectoryfromworkspace?",
    "Removeserver?",
    "Removetask?",
    "Deleteitalongwith",        # "Delete it along with the plugin?"
    "Disableitjustforyou",      # "Disable it just for you in .claude/settings.local.json?"
    "Overwrite?",
]
# NOTE: "Exit plan mode?" / "Stop ultraplan?" / "Stop ultrareview?" are
# deliberately NOT auto-confirmed — they abort/exit user work flows.

# Press-Enter prompts — single-line, fire without menu indicator.
PRESS_ENTER_TRIGGERS = (
    "PressEntertocontinue",
    "PressEntertotryagain",     # "Press Enter to try again, or any other key to cancel"
)

PROMPT_Y_TRIGGERS = [
    "(Y/n)", "(y/n)", "(y/N)", "[y/N]", "[Y/n]", "[y/n]", "[Y/N]",
    "Approve?[y/N]", "Allow?"
]

MENU_INDICATOR = "1.Yes"
TAIL_WINDOW = 600

# Minimum interval between two identical fires. Guards against terminal
# redraws (resize, scroll) that re-render the same prompt within a few
# milliseconds and would otherwise cause double-keypress.
THROTTLE_INTERVAL_S = 0.5


def process_buffer(buffer, log_file):
    """Checks the tail of the rolling text buffer.

    Returns (response_bytes, triggered, settle_seconds).
    """
    tail = buffer[-TAIL_WINDOW:]

    # "Press Enter to..." — single-line prompts, no menu rendered.
    if any(t in tail for t in PRESS_ENTER_TRIGGERS):
        if log_file:
            log_file.write("--- TRIGGERED ENTER (press-enter) ---\n")
            log_file.flush()
        return b"\r", True, 0.35

    # Menu prompts — require BOTH the question phrase AND a rendered menu
    # indicator (`1.Yes`). Without the indicator, "Do you want to..." text
    # is just prose (Claude explaining something, README content, etc.).
    if MENU_INDICATOR in tail:
        for trigger in PROMPT_ENTER_TRIGGERS:
            if trigger in tail:
                if log_file:
                    log_file.write("--- TRIGGERED ENTER (menu) ---\n")
                    log_file.flush()
                return b"\r", True, 0.35

    # Y/N prompts.
    if any(t in tail for t in PROMPT_Y_TRIGGERS):
        if log_file:
            log_file.write("--- TRIGGERED Y ---\n")
            log_file.flush()
        return b"y\r", True, 0.1

    return None, False, 0


# Strips ANSI/VT control sequences. Covers:
#   CSI  : ESC [ … final-byte
#   single-char ESC: ESC @ … _
#   OSC  : ESC ] … (BEL | ESC \)         — terminal title, hyperlinks
#   DCS/APC/PM/SOS : ESC P|^|_|X … ESC \  — device strings
ANSI_ESCAPE = re.compile(
    r'\x1B\][^\x07\x1B]*(?:\x07|\x1B\\)'
    r'|\x1B[P^_X][^\x1B]*\x1B\\'
    r'|\x1B\[[0-?]*[ -/]*[@-~]'
    r'|\x1B[@-Z\\-_]'
)


def _open_log():
    """Open the debug log in the user's cache dir, mode 0600. Best-effort."""
    try:
        cache_dir = os.path.join(
            os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"),
            "claude_auto",
        )
        os.makedirs(cache_dir, exist_ok=True)
        path = os.path.join(cache_dir, "claude_auto.log")
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags, 0o600)
        return os.fdopen(fd, "w")
    except Exception:
        return None


def _trim_raw_buffer(raw_buffer, soft_max=8192, target=4096):
    """Trim cumulative raw buffer without slicing mid-ANSI escape.

    Cuts at the last newline before `target` chars from the end when possible,
    so a partial CSI/OSC sequence never gets left as a literal `[1C` after
    the next strip pass.
    """
    if len(raw_buffer) <= soft_max:
        return raw_buffer
    cutoff = len(raw_buffer) - target
    nl = raw_buffer.rfind('\n', 0, cutoff)
    if nl != -1:
        return raw_buffer[nl + 1:]
    return raw_buffer[-target:]


# ==========================================
# MAC / LINUX (POSIX) IMPLEMENTATION
# ==========================================
def run_posix(command):
    import pty
    import select
    import termios
    import tty
    import struct
    import fcntl
    import signal
    import errno

    # If stdin isn't a TTY (piped, nohup, systemd, CI), termios.tcgetattr
    # would raise. Auto-clicking is meaningless without a TTY anyway, so
    # become transparent: replace ourselves with the target command.
    if not sys.stdin.isatty():
        try:
            os.execvp(command[0], command)
        except FileNotFoundError:
            sys.stderr.write(f"auto: command not found: {command[0]}\n")
            sys.exit(127)
        except Exception as e:
            sys.stderr.write(f"auto: exec failed: {e}\n")
            sys.exit(1)

    old_tty = termios.tcgetattr(sys.stdin)

    try:
        pid, fd = pty.fork()
    except OSError as e:
        sys.stderr.write(f"auto: pty.fork failed: {e}\n")
        sys.exit(1)

    if pid == 0:
        try:
            os.execvp(command[0], command)
        except FileNotFoundError:
            sys.stderr.write(f"auto: command not found: {command[0]}\n")
            os._exit(127)
        except Exception as e:
            sys.stderr.write(f"auto: exec failed: {e}\n")
            os._exit(1)
    else:
        def set_winsize(target_fd):
            try:
                s = struct.pack("HHHH", 0, 0, 0, 0)
                a = fcntl.ioctl(sys.stdin.fileno(), termios.TIOCGWINSZ, s)
                fcntl.ioctl(target_fd, termios.TIOCSWINSZ, a)
            except Exception:
                pass

        set_winsize(fd)
        signal.signal(signal.SIGWINCH, lambda sig, data: set_winsize(fd))

        try:
            tty.setraw(sys.stdin.fileno())
            buffer = ""
            log_file = _open_log()

            decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
            raw_buffer = ""
            last_fire_time = 0.0
            last_fire_response = None

            while True:
                try:
                    r, _, _ = select.select([fd, sys.stdin], [], [])
                except (InterruptedError, OSError) as e:
                    # SIGWINCH or similar — retry. PEP 475 normally handles
                    # this on Py3.5+ but custom handlers can still surface it.
                    if isinstance(e, OSError) and e.errno != errno.EINTR:
                        raise
                    continue

                if fd in r:
                    try:
                        output = os.read(fd, 1024)
                    except OSError:
                        break

                    if not output:
                        break

                    sys.stdout.buffer.write(output)
                    sys.stdout.buffer.flush()

                    # Stateful UTF-8 decode: multi-byte chars split across
                    # reads no longer get truncated by `errors=ignore`.
                    decoded = decoder.decode(output)

                    if log_file:
                        log_file.write("RAW: " + repr(output) + "\n")

                    # Keep raw (un-stripped) tail so ANSI escapes split across
                    # reads reassemble before regex runs.
                    raw_buffer = _trim_raw_buffer(raw_buffer + decoded)

                    buffer = ANSI_ESCAPE.sub('', raw_buffer).replace(' ', '')

                    response, triggered, settle = process_buffer(buffer, log_file)
                    if triggered:
                        now = time.monotonic()
                        if (response == last_fire_response and
                                now - last_fire_time < THROTTLE_INTERVAL_S):
                            # Same prompt re-rendered within the throttle
                            # window — terminal redraw, not a real new prompt.
                            if log_file:
                                log_file.write("--- THROTTLED ---\n")
                                log_file.flush()
                            raw_buffer = ""
                            buffer = ""
                            continue
                        time.sleep(settle)
                        try:
                            os.write(fd, response)
                        except OSError:
                            break
                        last_fire_time = time.monotonic()
                        last_fire_response = response
                        raw_buffer = ""
                        buffer = ""

                if sys.stdin in r:
                    try:
                        input_data = os.read(sys.stdin.fileno(), 1024)
                    except OSError:
                        break
                    if not input_data:
                        break
                    try:
                        os.write(fd, input_data)
                    except OSError:
                        break
        except Exception:
            pass
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_tty)
            try:
                os.waitpid(pid, 0)
            except ChildProcessError:
                pass

# ==========================================
# WINDOWS IMPLEMENTATION
# ==========================================
def run_windows(command):
    try:
        import wexpect
    except ImportError:
        print("="*60)
        print("WINDOWS COMPATIBILITY MODE REQUIRED")
        print("="*60)
        print("Because Windows lacks native Unix pseudo-terminals (PTYs),")
        print("this script requires the 'wexpect' library to run on Windows.")
        print("\nPlease install it by running this command in your terminal:")
        print("    pip install wexpect")
        print("\nThen run this script again!")
        print("="*60)
        sys.exit(1)

    import threading
    import msvcrt

    try:
        child = wexpect.spawn(command[0], command[1:])
    except Exception as e:
        print(f"Failed to start command: {e}")
        sys.exit(1)

    def read_output():
        decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        raw_buffer = ""
        last_fire_time = 0.0
        last_fire_response = None
        while True:
            try:
                char = child.read_nonblocking(size=1, timeout=None)
                sys.stdout.write(char)
                sys.stdout.flush()

                if isinstance(char, bytes):
                    decoded = decoder.decode(char)
                else:
                    decoded = char

                raw_buffer = _trim_raw_buffer(raw_buffer + decoded)
                buffer = ANSI_ESCAPE.sub('', raw_buffer).replace(' ', '')

                response, triggered, settle = process_buffer(buffer, None)
                if triggered:
                    now = time.monotonic()
                    if (response == last_fire_response and
                            now - last_fire_time < THROTTLE_INTERVAL_S):
                        raw_buffer = ""
                        continue
                    time.sleep(settle)
                    child.send(response.decode('utf-8'))
                    last_fire_time = time.monotonic()
                    last_fire_response = response
                    raw_buffer = ""
            except wexpect.EOF:
                break
            except Exception:
                break

    t = threading.Thread(target=read_output)
    t.daemon = True
    t.start()

    try:
        while t.is_alive():
            if msvcrt.kbhit():
                char = msvcrt.getch()
                if char in (b'\x00', b'\xe0'):
                    char += msvcrt.getch()
                child.send(char.decode('utf-8', errors='ignore'))
            time.sleep(0.01)
    except KeyboardInterrupt:
        child.terminate()
    except Exception:
        pass

    child.wait()

# ==========================================
# ENTRY POINT
# ==========================================
def main():
    if len(sys.argv) < 2:
        print("Usage:   auto <command> [args...]")
        print()
        print("Examples:")
        print("  auto claude")
        print("  auto claude --resume <session-id>")
        print("  auto claude --dangerously-skip-permissions")
        print("  auto ./my_script.py")
        sys.exit(1)

    command = sys.argv[1:]
    platform = sys.platform

    if command and command[0].startswith("--fake-os="):
        platform = command[0].split("=")[1]
        command = command[1:]

    if platform == "win32":
        run_windows(command)
    else:
        run_posix(command)

if __name__ == "__main__":
    main()
