#!/usr/bin/env python3
import sys
import time
import tty
import termios

def prompt_1():
    sys.stdout.write("Some claude output...\r\n")
    sys.stdout.write("Approve? [y/N] ")
    sys.stdout.flush()
    ans = sys.stdin.read(1)
    if ans.lower() == 'y':
        sys.stdout.write("\r\nApproved 1!\r\n")
    else:
        sys.stdout.write("\r\nDeclined 1!\r\n")

def prompt_2():
    sys.stdout.write(" Do you want to proceed?\r\n")
    sys.stdout.write("   1. Yes\r\n")
    sys.stdout.write(" \x1b[32m❯\x1b[0m 2. Yes, and allow access to bin/ and pacman -Qo /usr/bin/time commands\r\n")
    sys.stdout.write("   3. No\r\n")
    sys.stdout.flush()
    ans = sys.stdin.read(1)
    if ans == '\r' or ans == '\n':
        sys.stdout.write("\r\nSelected default (2)!\r\n")
    elif ans == '1':
        sys.stdout.write("\r\nSelected 1!\r\n")
    else:
        sys.stdout.write(f"\r\nSelected {repr(ans)}\r\n")

def main():
    # Set to raw mode to simulate real interactive CLI reading a single char
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        sys.stdout.write("Starting mock claude...\r\n")
        time.sleep(0.5)
        prompt_1()
        time.sleep(0.5)
        prompt_2()
        sys.stdout.write("Done mock claude.\r\n")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

if __name__ == "__main__":
    main()
