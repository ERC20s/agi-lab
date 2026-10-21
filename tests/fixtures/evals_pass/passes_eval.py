"""Fixture eval that always passes. Used by tests/test_run_all.py."""

import sys


def main():
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
