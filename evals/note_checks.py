"""Shared structure checks for notes/<topic>.md, used by the per-note evals.

Usage (as a library, from evals/<topic>_eval.py):

    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from note_checks import check_note
    sys.exit(check_note("my-topic.md"))

Usage (standalone): python3 evals/note_checks.py
    Runs a self-test of the helpers against two in-memory sample notes
    (one valid, one missing a URL in Sources) and exits 0 when the helpers
    behave as documented, non-zero otherwise. This keeps the module honest
    when evals/run_all.py discovers and executes it like any other eval.

Checks performed by check_note():
- File exists at notes/<filename>
- Contains an H1 title (line starting with '# ')
- Contains a 'Summary' section
- Contains a 'Motivation' section (CONTRIBUTING.md: 'Motivation & Background')
- Contains a 'Sources' section with at least one http(s):// URL

check_note() returns 0 on success, 1 on a failed check, 2 when the note
cannot be read. Standard library only; no third-party imports.
"""

import os
import re
import sys

NOTES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "notes")


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


def check_text(text):
    """Run every structural check against note text. Returns 0 or 1."""
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

    if not has_section(text, "Motivation"):
        print("FAIL: missing 'Motivation' section")
        ok = False
    else:
        print("OK: found 'Motivation' section")

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


def check_note(filename):
    """Check notes/<filename>. Returns 0 (pass), 1 (failed check) or 2 (unreadable)."""
    path = os.path.join(NOTES_DIR, filename)
    text = read_note(path)
    if text is None:
        return 2
    print(f"Checking {os.path.join('notes', filename)}")
    return check_text(text)


VALID_SAMPLE = """# Sample Topic

Summary: A short summary of the sample idea and its main claim.

Motivation & Background:

- Why the sample idea matters.

Sources:
1. https://example.org/paper
"""

INVALID_SAMPLE = """# Sample Topic

Summary: A short summary of the sample idea and its main claim.

Motivation & Background:

- Why the sample idea matters.

Sources:
1. A book with no link at all.
"""


def _self_test():
    """Exercise the helpers against in-memory samples. Returns 0 or 1."""
    failures = []

    def expect(label, actual, wanted):
        if actual != wanted:
            failures.append(f"{label}: expected {wanted!r}, got {actual!r}")
            print(f"FAIL: {label}")
        else:
            print(f"OK: {label}")

    expect("has_h1 accepts a titled note", has_h1(VALID_SAMPLE), True)
    expect("has_h1 rejects a note with no H1", has_h1("no title here\n"), False)
    expect("has_section finds Summary", has_section(VALID_SAMPLE, "Summary"), True)
    expect("has_section finds Motivation", has_section(VALID_SAMPLE, "Motivation"), True)
    expect("has_section finds Sources", has_section(VALID_SAMPLE, "Sources"), True)
    expect("has_section rejects an absent section", has_section(VALID_SAMPLE, "Appendix"), False)
    expect("sources_have_url accepts a linked source", sources_have_url(VALID_SAMPLE), True)
    expect("sources_have_url rejects an unlinked source", sources_have_url(INVALID_SAMPLE), False)
    print("-- check_text against the valid sample (all lines below should be OK) --")
    expect("check_text passes the valid sample", check_text(VALID_SAMPLE), 0)
    print("-- check_text against the unlinked sample (one FAIL line below is expected) --")
    expect("check_text fails the unlinked sample", check_text(INVALID_SAMPLE), 1)

    if failures:
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        return 1
    return 0


def main():
    print("note_checks self-test")
    return _self_test()


if __name__ == "__main__":
    sys.exit(main())
