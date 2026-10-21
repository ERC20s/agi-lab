"""Validate notes/emergent-abilities.md adheres to minimal note conventions.

Usage: python3 evals/emergent-abilities_eval.py

Checks performed:
- File exists at notes/emergent-abilities.md
- Contains an H1 title (line starting with '# ')
- Contains a 'Summary' section
- Contains a 'Sources' section with at least one http(s):// URL

Returns 0 on success, non-zero on failure.
"""

import re
import sys
import os

NOTE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "notes", "emergent-abilities.md")


def read_note(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except Exception as e:
        print(f"ERROR: could not read note file {path}: {e}", file=sys.stderr)
        return None


def has_h1(text):
    for line in text.splitlines():
        if line.strip().startswith("# "):
            return True
    return False


def has_section(text, name):
    # Look for a line starting with the section name followed by ':' or '\n' titles
    pattern = re.compile(rf"^{re.escape(name)}\b", re.IGNORECASE | re.MULTILINE)
    return bool(pattern.search(text))


def sources_have_url(text):
    # Find the Sources section and check for an http(s) URL anywhere after it
    m = re.search(r"^Sources:\s*$", text, re.IGNORECASE | re.MULTILINE)
    if not m:
        return False
    after = text[m.end():]
    # Simple URL regex
    url_re = re.compile(r"https?://\S+")
    return bool(url_re.search(after))


def main():
    text = read_note(NOTE_PATH)
    if text is None:
        return 2

    ok = True

    if not has_h1(text):
        print("FAIL: missing H1 title (line starting with '# ')")
        ok = False
    else:
        print("OK: found H1 title")

    if not has_section(text, "Summary"):
        print("FAIL: missing 'Summary' section")
        ok = False
    else:
        print("OK: found 'Summary' section")

    if not has_section(text, "Sources"):
        print("FAIL: missing 'Sources' section")
        ok = False
    else:
        print("OK: found 'Sources' section")
        if not sources_have_url(text):
            print("FAIL: 'Sources' section does not contain an http(s):// URL")
            ok = False
        else:
            print("OK: 'Sources' contains a URL")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
