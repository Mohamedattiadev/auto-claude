#!/usr/bin/env python3
import sys
import os
import time
import re

# Universal triggers — spaces are stripped from buffer to defeat CLI cursor-jump formatting.
#
# IMPORTANT: Menu (Enter) triggers are checked FIRST to prevent a Y-prompt buried
# inside a menu from firing the wrong response.
PROMPT_ENTER_TRIGGERS = [
    "Doyouwanttoproceed?",
    "Doyouwanttocreate",
    "Doyouwanttorun",
    "Doyouwantto",
    "PressEntertocontinue",
]

PROMPT_Y_TRIGGERS = [
    "(Y/n)", "(y/n)", "(y/N)", "[y/N]", "[Y/n]", "[y/n]", "[Y/N]",
    "Approve?[y/N]", "Allow?"
]

def process_buffer(buffer, log_file):
    """Checks the rolling text buffer. Menu triggers are evaluated before Y triggers."""
    # Check menu triggers first — these render multi-line menus that end with '1.Yes'
    # so we need a small settle delay to let the full menu arrive before responding.
    if any(trigger in buffer for trigger in PROMPT_ENTER_TRIGGERS):
        if log_file:
            log_file.write("--- TRIGGERED ENTER ---\n")
            log_file.flush()
        return b"\r", True, 0.35   # extra settle time for menus
    elif any(trigger in buffer for trigger in PROMPT_Y_TRIGGERS):
        if log_file:
            log_file.write("--- TRIGGERED Y ---\n")
            log_file.flush()
        return b"y\r", True, 0.1
    return None, False, 0

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

    old_tty = termios.tcgetattr(sys.stdin)
    pid, fd = pty.fork()

    if pid == 0:
        os.execvp(command[0], command)
    else:
        def set_winsize(fd):
            try:
                s = struct.pack("HHHH", 0, 0, 0, 0)
                a = fcntl.ioctl(sys.stdin.fileno(), termios.TIOCGWINSZ, s)
                fcntl.ioctl(fd, termios.TIOCSWINSZ, a)
            except Exception:
                pass
                
        set_winsize(fd)
        signal.signal(signal.SIGWINCH, lambda sig, data: set_winsize(fd))

        try:
            tty.setraw(sys.stdin.fileno())
            buffer = ""
            try:
                log_file = open("/tmp/claude_auto.log", "w")
            except Exception:
                log_file = None

            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

            raw_buffer = ""
            while True:
                r, w, e = select.select([fd, sys.stdin], [], [])

                if fd in r:
                    try:
                        output = os.read(fd, 1024)
                    except OSError:
                        break

                    if not output:
                        break

                    sys.stdout.buffer.write(output)
                    sys.stdout.buffer.flush()

                    decoded = output.decode('utf-8', errors='ignore')

                    if log_file:
                        log_file.write("RAW: " + repr(output) + "\n")

                    # Keep raw (un-stripped) tail so ANSI escapes split across reads
                    # reassemble before regex runs. Per-chunk stripping would leave
                    # an orphan ESC in chunk N and literal "[1Cword" in chunk N+1,
                    # breaking trigger substrings.
                    raw_buffer += decoded
                    if len(raw_buffer) > 4096:
                        raw_buffer = raw_buffer[-4096:]

                    buffer = ansi_escape.sub('', raw_buffer).replace(' ', '')

                    response, triggered, settle = process_buffer(buffer, log_file)
                    if triggered:
                        time.sleep(settle)
                        os.write(fd, response)
                        raw_buffer = ""
                        buffer = ""
                        
                if sys.stdin in r:
                    input_data = os.read(sys.stdin.fileno(), 1024)
                    if not input_data:
                        break
                    os.write(fd, input_data)
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

    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    
    # Thread to constantly read output from the process
    def read_output():
        raw_buffer = ""
        while True:
            try:
                char = child.read_nonblocking(size=1, timeout=None)
                sys.stdout.write(char)
                sys.stdout.flush()

                # Buffer raw bytes; strip ANSI on whole buffer each pass so escapes
                # split across reads (e.g. ESC then "[1C") reassemble before regex.
                raw_buffer += char
                if len(raw_buffer) > 4096:
                    raw_buffer = raw_buffer[-4096:]

                buffer = ansi_escape.sub('', raw_buffer).replace(' ', '')

                response, triggered, settle = process_buffer(buffer, None)
                if triggered:
                    time.sleep(settle)
                    child.send(response.decode('utf-8'))
                    raw_buffer = ""
            except wexpect.EOF:
                break
            except Exception:
                break

    t = threading.Thread(target=read_output)
    t.daemon = True
    t.start()

    # Main loop to pass user input to the process
    try:
        while t.is_alive():
            if msvcrt.kbhit():
                char = msvcrt.getch()
                if char in (b'\x00', b'\xe0'): # Handle arrow keys
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
    
    # Allow testing other OSs by passing --fake-os=win32 or --fake-os=darwin
    if command and command[0].startswith("--fake-os="):
        platform = command[0].split("=")[1]
        command = command[1:]

    # Detect the operating system and run the appropriate implementation
    if platform == "win32":
        run_windows(command)
    else:
        run_posix(command)

if __name__ == "__main__":
    main()
