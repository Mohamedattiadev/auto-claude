#!/usr/bin/env python3
"""Mock prompt emitter for PTY integration tests.

Reads a JSON list of {"prompt": ...} steps from argv[1], emits each
prompt to stdout, captures whatever the auto-clicker writes back to
stdin (up to 3 s per prompt), and writes the captured strings as a
JSON list to argv[2].

Lives in tests/ alongside the integration test that drives it. Not
imported by the unit tests.
"""
import sys
import os
import json
import time
import select


def main():
    if len(sys.argv) < 3:
        sys.stderr.write("usage: _mock_target.py SCRIPT_JSON RESULT_JSON\n")
        sys.exit(2)

    script_path = sys.argv[1]
    result_path = sys.argv[2]

    with open(script_path) as f:
        script = json.load(f)

    received = []
    for step in script:
        prompt = step["prompt"]
        sys.stdout.write(prompt)
        sys.stdout.write("\r\n")
        sys.stdout.flush()

        # Wait up to 3 s for a response. Stop early on CR/LF — that's
        # how both b"y\r" and b"\r" terminate.
        deadline = time.time() + 3.0
        chars = []
        while time.time() < deadline:
            r, _, _ = select.select([sys.stdin], [], [], 0.1)
            if not r:
                continue
            try:
                data = os.read(sys.stdin.fileno(), 16)
            except OSError:
                break
            if not data:
                break
            chars.append(data.decode("utf-8", errors="replace"))
            if b"\r" in data or b"\n" in data:
                break
        received.append("".join(chars))
        # Give the auto-clicker time to clear its buffer and reset the
        # throttle window before the next prompt.
        time.sleep(0.6)

    with open(result_path, "w") as f:
        json.dump(received, f)


if __name__ == "__main__":
    main()
