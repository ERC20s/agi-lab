"""A simple long-running scheduler for the eval runner.

This script runs evals/run_all.py once at startup and then again on a
fixed interval (24h by default). It is intentionally dependency-free and
uses the same Python interpreter that launched it.

Usage:
  python evals/scheduled_runner.py              # run forever, once now then every 24h
  python evals/scheduled_runner.py --once       # run once and exit (useful for CI)
  python evals/scheduled_runner.py --interval 60  # run every 60 seconds (testing)

The process respects SIGINT and SIGTERM: a signal will stop scheduling new
runs but will let a currently-running eval finish (or be killed by the
runner's own timeout policy).
"""
import argparse
import subprocess
import sys
import time
import datetime
import threading
import signal

DEFAULT_INTERVAL_SECONDS = 24 * 60 * 60  # 24 hours

stop_requested = False
stop_lock = threading.Lock()


def mark_stop(signum, frame):
    global stop_requested
    with stop_lock:
        stop_requested = True
    print(f"scheduled_runner: signal {signum} received — will stop after current run")


def should_stop():
    with stop_lock:
        return stop_requested


def run_once():
    """Invoke the eval runner and return its subprocess return code."""
    # Use --strip-outputs for scheduled runs so per-eval stdout/stderr are omitted
    # from the committed evals/last_run.json. This keeps the artifact compact and
    # avoids repeatedly committing large logs; contributors can still run the
    # runner locally without the flag to capture full outputs.
    cmd = [
        sys.executable,
        "evals/run_all.py",
        "--json-output",
        "evals/last_run.json",
        "--strip-outputs",
    ]
    started = datetime.datetime.utcnow().isoformat() + "Z"
    print(f"scheduled_runner: starting run at {started}: {cmd}")
    try:
        proc = subprocess.run(cmd)
        rc = proc.returncode
    except Exception as e:
        print(f"scheduled_runner: runner failed to start: {e}")
        rc = 1
    finished = datetime.datetime.utcnow().isoformat() + "Z"
    print(f"scheduled_runner: finished run at {finished} (rc={rc})")
    return rc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL_SECONDS,
        help="Seconds between runs (default 86400 = 24h)",
    )
    args = parser.parse_args()

    signal.signal(signal.SIGINT, mark_stop)
    signal.signal(signal.SIGTERM, mark_stop)

    # First run immediately
    rc = run_once()
    if args.once:
        # Exit with the runner's return code to make CI checks simple.
        sys.exit(0 if rc == 0 else 1)

    interval = float(args.interval)
    if interval <= 0:
        print("scheduled_runner: non-positive interval — exiting")
        return

    while True:
        # Sleep in small increments so signals are responsive.
        slept = 0.0
        while slept < interval:
            if should_stop():
                print("scheduled_runner: stop requested; exiting before next run")
                return
            time.sleep(min(1.0, interval - slept))
            slept += min(1.0, interval - slept)
        if should_stop():
            print("scheduled_runner: stop requested; exiting before scheduled run")
            return
        rc = run_once()
        # Loop continues until killed; we don't escalate on non-zero rc so the
        # process stays up to attempt fresh runs later.


if __name__ == "__main__":
    main()
