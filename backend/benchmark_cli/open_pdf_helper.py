#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _request_host_open(path: Path) -> bool:
    request_file = os.environ.get("P4SYMTEST_OPEN_REQUEST_FILE")
    requested_via_env = True
    if not request_file:
        request_file = "/app/workspace/.benchmark_open_requests"
        requested_via_env = False

    try:
        request_path = Path(request_file)
        request_path.parent.mkdir(parents=True, exist_ok=True)
        with request_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{path}\n")
        if requested_via_env:
            print("Open request sent to host.")
        else:
            print(
                "Open request logged at /app/workspace/.benchmark_open_requests. "
                "To open automatically on host, run via ./run benchmark on host."
            )
        return True
    except Exception as exc:
        print(f"Warning: could not send open request to host: {exc}")
        return False


def try_open_file(path: Path) -> None:
    target = path.resolve()

    try:
        if sys.platform == "darwin":
            subprocess.run(["open", str(target)], check=False)
            return

        if sys.platform.startswith("linux"):
            opener = shutil.which("xdg-open")
            if opener:
                result = subprocess.run([opener, str(target)], check=False)
                if result.returncode == 0:
                    return
            if _request_host_open(target):
                return
            print("Warning: could not auto-open (xdg-open unavailable in container).")
            return

        if sys.platform.startswith("win"):
            import os as _os

            _os.startfile(str(target))  # type: ignore[attr-defined]
            return

        print(f"Warning: platform does not support auto-open ({sys.platform}).")
    except Exception as exc:
        if _request_host_open(target):
            return
        print(f"Warning: could not open PDF automatically: {exc}")
