"""Run an external program and capture its output. Standard library only.

Every helper that starts a program takes a `Runner` (the type below), so tests replace it with a fake.
"""

import os
import signal
import subprocess
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

DRAIN_S = 5.0  # how long to wait for the output of a process that was just killed


@dataclass(frozen=True)
class Completed:
    """The result of a program run: its exit code (None means it timed out) and stdout and stderr, merged."""

    returncode: int | None
    output: str


Runner = Callable[[Sequence[str], Path, float], Completed]


def _decode(data: bytes | None) -> str:
    return (data or b"").decode("utf-8", errors="replace")


def _kill(proc: subprocess.Popen) -> None:
    """Kill the process and, on POSIX, the whole process group it leads (see `start_new_session` below)."""
    try:
        if hasattr(os, "killpg"):
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
    except OSError:
        pass  # already gone


def _guard_sigterm(children: list[subprocess.Popen]):
    """While a child runs, make SIGTERM kill the child's process group before it ends this process (POSIX, main thread).

    A child lives in its own session, so the signal that stops the caller (a dev container that kills its
    `postCreateCommand`) would otherwise leave it running. The handler kills the group, puts the previous handler
    back and sends the signal again, so the caller ends exactly as it would have without this guard. Nothing is
    installed when SIGTERM is ignored on purpose, or outside the main thread (signal.signal works only there).
    Returns the function that puts the previous handler back.
    """
    if os.name != "posix" or threading.current_thread() is not threading.main_thread():
        return lambda: None
    previous = signal.getsignal(signal.SIGTERM)
    if previous is None or previous == signal.SIG_IGN:  # not set from Python, or ignored on purpose
        return lambda: None

    def handler(signum, frame):
        for child in children:
            if child.returncode is None:  # still running, not collected: its process group id is not reused yet
                _kill(child)
        signal.signal(signum, previous)
        os.kill(os.getpid(), signum)

    signal.signal(signal.SIGTERM, handler)
    return lambda: signal.signal(signal.SIGTERM, previous)


def run_process(argv: Sequence[str], cwd: Path, timeout_s: float) -> Completed:
    """Run `argv` in `cwd` with stdin closed; stdout and stderr merged; decoded as UTF-8 (undecodable bytes replaced).

    After `timeout_s` seconds the process (and, on POSIX, its children) is killed and the result is
    `Completed(None, output + "\\n[timed out after N s]")`. A program that does not exist raises FileNotFoundError.
    """
    children: list[subprocess.Popen] = []
    restore_sigterm = _guard_sigterm(children)
    try:
        proc = subprocess.Popen(
            list(argv),
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            # a process group of its own, so that a timeout also reaches the children that hold the output pipe open
            start_new_session=os.name == "posix",
        )
        children.append(proc)
        try:
            data, _ = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired as expired:
            _kill(proc)
            try:
                data, _ = proc.communicate(timeout=DRAIN_S)
            except subprocess.TimeoutExpired as still:  # something outside the group keeps the pipe open
                data = still.output or expired.output
            return Completed(None, _decode(data) + f"\n[timed out after {timeout_s:g} s]")
        except BaseException:  # Ctrl-C and the like: the child lives in its own group and would be left behind
            _kill(proc)
            proc.wait()
            raise
        return Completed(proc.returncode, _decode(data))
    finally:
        children.clear()
        restore_sigterm()
