"""
Live existence checks for role="input_file"/role="output_file" paths, shared by
web_gui/server.py (marking files in the UI) and ExecutionEngine (refusing to run
a task whose input files are missing).
"""
from concurrent.futures import ThreadPoolExecutor, wait
from pathlib import Path
from typing import Dict, Iterable

# Statuses that mean "this file can't be used as an input right now".
PROBLEM_STATUSES = ("missing", "no_access")

# Each check on a network drive is a round trip to the file server (measured
# ~0.1-1.4 s per path on a mapped share, worse for "Access is denied"), and
# os.stat has no timeout of its own -- so checks run in parallel on a shared
# pool, and whatever hasn't answered within FILE_CHECK_DEADLINE_S is reported
# as "unknown" rather than holding up the caller. A check that hangs keeps its
# pool thread until the OS gives up; the pool is shared (not per call) so hung
# checks can't pile up unbounded threads.
FILE_CHECK_DEADLINE_S = 5
_file_check_pool = ThreadPoolExecutor(max_workers=32, thread_name_prefix="file-check")


def file_status(path: Path) -> str:
    """"exists", "missing", or "no_access" -- the last when even stat()-ing the
    path fails (e.g. WinError 5 "Access is denied" on a restricted network
    share), which Path.exists() raises rather than reporting as False."""
    try:
        return "exists" if path.exists() else "missing"
    except OSError:
        return "no_access"


def file_statuses(paths: Iterable, deadline: float = None) -> Dict[str, str]:
    """{str(Path(p)): status} for every path, checked concurrently (see above);
    status is file_status's, or "unknown" if it didn't finish within
    `deadline` seconds (default FILE_CHECK_DEADLINE_S, read at call time)."""
    unique = {str(Path(p)): Path(p) for p in paths}
    futures = {key: _file_check_pool.submit(file_status, path) for key, path in unique.items()}
    wait(futures.values(), timeout=FILE_CHECK_DEADLINE_S if deadline is None else deadline)
    return {key: future.result() if future.done() else "unknown" for key, future in futures.items()}
