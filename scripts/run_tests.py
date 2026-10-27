"""Run every pytest test with an independent deadline for native Qt hangs.

The parent process imports no Qt modules. It can terminate a test interpreter
even when a native extension prevents pytest's Python timeout thread from
running. Output and environment are inherited so CI retains live diagnostics.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence


def run_tests(arguments: Sequence[str] = (), *, timeout_seconds: float = 180) -> int:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-vv",
        "-o",
        "faulthandler_timeout=60",
        *arguments,
    ]
    try:
        subprocess.run(command, timeout=timeout_seconds, check=True)
    except subprocess.TimeoutExpired:
        print(
            f"Pytest exceeded the independent {timeout_seconds:g}-second deadline; "
            "the test interpreter was terminated. No tests were skipped.",
            file=sys.stderr,
            flush=True,
        )
        return 124
    except subprocess.CalledProcessError as exc:
        return exc.returncode
    return 0


def main(arguments: Sequence[str] | None = None) -> int:
    return run_tests(sys.argv[1:] if arguments is None else arguments)


if __name__ == "__main__":
    raise SystemExit(main())
