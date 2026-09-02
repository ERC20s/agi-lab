"""Validate notes/in-context-learning.md adheres to minimal note conventions.

Usage: python3 evals/in-context-learning_eval.py

The checks themselves live in evals/note_checks.py, which is shared by every
per-note eval:
- File exists at notes/in-context-learning.md
- Contains an H1 title (line starting with '# ')
- Contains a 'Summary' section
- Contains a 'Motivation' section
- Contains a 'Sources' section with at least one http(s):// URL

Returns 0 on success, non-zero on failure.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from note_checks import check_note  # noqa: E402


def main():
    return check_note("in-context-learning.md")


if __name__ == "__main__":
    sys.exit(main())
