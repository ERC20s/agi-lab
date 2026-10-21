"""Fixture eval that deliberately fails.

tests/test_run_all.py runs the runner over this directory and requires the
run to exit 1 with this file reported as FAIL. Never make it pass.
"""

import sys


def main():
    print("deliberate failure: this fixture must be reported as failed", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
