"""Fixture eval that passes, beside one that fails. Used by tests/test_run_all.py."""

import sys


def main():
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
