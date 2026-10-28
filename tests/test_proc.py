"""The process helper: one runner shape for every external program (the deck verification uses it too)."""

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from workshop.proc import DRAIN_S, Completed, run_process


def _py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_output_merges_stdout_and_stderr(tmp_path):
    done = run_process(_py("import sys; print('to-out', flush=True); print('to-err', file=sys.stderr, flush=True)"), tmp_path, 30)
    assert done.returncode == 0
    assert "to-out" in done.output and "to-err" in done.output


def test_exit_code_is_returned(tmp_path):
    assert run_process(_py("raise SystemExit(201)"), tmp_path, 30) == Completed(201, "")


def test_runs_in_the_given_folder(tmp_path):
    done = run_process(_py("import os; print(os.getcwd())"), tmp_path, 30)
    assert os.path.samefile(done.output.strip(), tmp_path)


def test_stdin_is_closed(tmp_path):
    done = run_process(_py("import sys; print(repr(sys.stdin.read()))"), tmp_path, 30)
    assert done.returncode == 0
    assert done.output.strip() == "''"


def test_output_is_decoded_as_utf8_and_never_raises(tmp_path):
    code = "import sys; sys.stdout.buffer.write('caf\\u00e9 '.encode('utf-8') + bytes([0xFF]) + b' end'); sys.stdout.flush()"
    done = run_process(_py(code), tmp_path, 30)
    assert done.output == "café � end"


def test_timeout_kills_and_returns_none(tmp_path):
    started = time.monotonic()
    done = run_process(_py("import time; print('started', flush=True); time.sleep(30)"), tmp_path, 1)
    assert time.monotonic() - started < 20
    assert done.returncode is None
    assert "started" in done.output  # what the child had printed is kept
    assert "[timed out after 1 s]" in done.output


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX")
def test_timeout_also_kills_the_childs_children(tmp_path):
    """A grandchild that inherited the output pipe must not keep the call waiting."""
    code = "import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); time.sleep(30)"
    started = time.monotonic()
    done = run_process(_py(code), tmp_path, 1)
    assert time.monotonic() - started < DRAIN_S - 1  # not the wait for the pipe that the grandchild still holds
    assert done.returncode is None


def test_missing_program_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_process(["definitely-not-installed-xyz"], tmp_path, 5)


def test_completed_is_frozen():
    done = Completed(0, "x")
    with pytest.raises(AttributeError):
        done.returncode = 1  # type: ignore[misc]


# SIGTERM: a killed `postCreateCommand` must not leave its children running

POSIX_ONLY = pytest.mark.skipif(os.name != "posix", reason="SIGTERM and process groups are POSIX")
ROOT = Path(__file__).resolve().parent.parent


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        state = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()[0]
    except (OSError, IndexError):
        return True
    return state != "Z"  # a zombie is dead, only not collected yet


def _wait_for(condition, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return condition()


@POSIX_ONLY
def test_sigterm_kills_the_child_and_the_caller_still_ends_by_the_signal(tmp_path):
    pidfile = tmp_path / "child.pid"
    child_code = f"import os, time; open({str(pidfile)!r}, 'w').write(str(os.getpid())); time.sleep(60)"
    driver_code = "; ".join(
        [
            "import sys",
            f"sys.path.insert(0, {str(ROOT)!r})",
            "from pathlib import Path",
            "from workshop.proc import run_process",
            f"run_process([sys.executable, '-c', {child_code!r}], Path.cwd(), 120)",
        ]
    )
    driver = subprocess.Popen([sys.executable, "-c", driver_code], cwd=tmp_path, stdin=subprocess.DEVNULL)
    child_pid = None
    try:
        assert _wait_for(lambda: pidfile.exists() and pidfile.read_text(encoding="utf-8").strip() != "", 20), "child did not start"
        child_pid = int(pidfile.read_text(encoding="utf-8"))
        assert _alive(child_pid)
        driver.send_signal(signal.SIGTERM)
        assert driver.wait(timeout=20) == -signal.SIGTERM  # the signal is delivered again: the caller ends as it would have
        assert _wait_for(lambda: not _alive(child_pid), 10), "the child was left running"
    finally:
        if driver.poll() is None:
            driver.kill()
        if child_pid is not None and _alive(child_pid):
            os.kill(child_pid, signal.SIGKILL)


@POSIX_ONLY
def test_the_sigterm_handler_exists_only_while_the_child_runs(tmp_path):
    before = signal.getsignal(signal.SIGTERM)
    seen = []
    timer = threading.Timer(0.7, lambda: seen.append(signal.getsignal(signal.SIGTERM)))
    timer.start()
    done = run_process(_py("import time; time.sleep(1.5)"), tmp_path, 30)
    timer.join()
    assert done.returncode == 0
    assert seen and seen[0] is not before and callable(seen[0])
    assert signal.getsignal(signal.SIGTERM) == before


@POSIX_ONLY
def test_an_ignored_sigterm_stays_ignored(tmp_path):
    before = signal.signal(signal.SIGTERM, signal.SIG_IGN)
    try:
        seen = []
        timer = threading.Timer(0.5, lambda: seen.append(signal.getsignal(signal.SIGTERM)))
        timer.start()
        run_process(_py("import time; time.sleep(1)"), tmp_path, 30)
        timer.join()
        assert seen == [signal.SIG_IGN]
        assert signal.getsignal(signal.SIGTERM) == signal.SIG_IGN
    finally:
        signal.signal(signal.SIGTERM, before)


def test_it_also_runs_in_a_thread(tmp_path):
    """signal.signal works only in the main thread: elsewhere no handler is installed, and nothing fails."""
    results = []
    worker = threading.Thread(target=lambda: results.append(run_process(_py("print('from a thread')"), tmp_path, 30)))
    worker.start()
    worker.join(timeout=30)
    assert [r.output.strip() for r in results] == ["from a thread"]
