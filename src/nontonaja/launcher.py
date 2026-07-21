from __future__ import annotations

import os
import pty
import re
import select
import subprocess
import sys


def fzf_select(options: list[str], prompt: str = "> ", header: str = "") -> str | None:
    args = ["fzf", "--prompt", prompt, "--reverse"]
    if header:
        args += ["--header", header]

    master_fd, slave_fd = pty.openpty()
    try:
        proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=slave_fd,
            stderr=subprocess.DEVNULL,
        )
        os.close(slave_fd)

        proc.stdin.write(("\n".join(options)).encode())
        proc.stdin.close()

        output = b""
        while proc.poll() is None:
            r, _, _ = select.select([master_fd], [], [], 0.1)
            if r:
                try:
                    data = os.read(master_fd, 8192)
                    if not data:
                        break
                    output += data
                except OSError:
                    break

        try:
            remaining = os.read(master_fd, 8192)
            output += remaining
        except OSError:
            pass

        proc.wait()
    finally:
        try:
            os.close(master_fd)
        except OSError:
            pass

    text = output.decode(errors="ignore")
    clean = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)
    clean = re.sub(r"\x1b\].*?\x07", "", clean)
    lines = [l.strip() for l in clean.split("\n") if l.strip()]
    return lines[-1] if lines else None


def rofi_select(options: list[str], prompt: str = "Select") -> str | None:
    args = ["rofi", "-dmenu", "-p", prompt, "-i"]
    proc = subprocess.run(
        args,
        input="\n".join(options),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return proc.stdout.strip()


def _fallback_select(options: list[str], header: str = "") -> str | None:
    """Simple numbered list fallback when fzf/rofi unavailable."""
    if header:
        print(header, file=sys.stderr)
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}", file=sys.stderr)
    try:
        choice = input("Pilih nomor: ").strip()
        idx = int(choice) - 1
        if 0 <= idx < len(options):
            return options[idx]
    except (ValueError, EOFError):
        pass
    return None


def launcher(
    options: list[str], prompt: str = "> ", use_rofi: bool = False, header: str = ""
) -> str | None:
    if use_rofi:
        result = rofi_select(options, prompt)
        if result:
            return result

    result = fzf_select(options, prompt, header)
    if result:
        return result

    return _fallback_select(options, header)
