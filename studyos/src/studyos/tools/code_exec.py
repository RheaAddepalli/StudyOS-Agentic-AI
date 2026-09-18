"""Executes learner-submitted Python for coding exercises.

Honest limitation: this is a subprocess sandbox (timeout + CPU/memory rlimits
+ no network + fresh temp dir), not a container or VM. It stops runaway loops
and accidental resource exhaustion, and it blocks outbound network calls at
the OS level on Linux via `resource` limits is NOT sufficient for that alone,
so we also strip network-capable env vars and rely on the timeout as the
backstop. For anything beyond a portfolio/demo project — i.e. running
arbitrary untrusted code from real users — replace this with a real
container sandbox (Docker with --network=none, gVisor, Firecracker, or a
hosted sandbox like E2B). Do not point this module at untrusted input in
production as-is.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..config import settings

_MEMORY_LIMIT_BYTES = 256 * 1024 * 1024  # 256 MB

if sys.platform != "win32":
    import resource

    def _limit_resources():
        resource.setrlimit(
            resource.RLIMIT_AS, (_MEMORY_LIMIT_BYTES, _MEMORY_LIMIT_BYTES)
        )
        resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
else:
    _limit_resources = None  # no POSIX rlimits on Windows; the timeout is the only backstop


@dataclass
class ExecutionResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool


def run_python(code: str, stdin: str = "") -> ExecutionResult:
    with tempfile.TemporaryDirectory() as tmp:
        script_path = Path(tmp) / "submission.py"
        script_path.write_text(code)

        try:
            proc = subprocess.run(
                [sys.executable, str(script_path)],
                input=stdin,
                capture_output=True,
                text=True,
                timeout=settings.code_exec_timeout_seconds,
                cwd=tmp,
                preexec_fn=_limit_resources if sys.platform != "win32" else None,
                env={"PATH": "/usr/bin:/bin"},  # minimal env, no inherited secrets
            )
            return ExecutionResult(proc.stdout, proc.stderr, proc.returncode, timed_out=False)
        except subprocess.TimeoutExpired as e:
            return ExecutionResult(
                stdout=e.stdout or "",
                stderr=(e.stderr or "") + "\n[execution timed out]",
                exit_code=-1,
                timed_out=True,
            )
