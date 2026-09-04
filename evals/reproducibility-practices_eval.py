"""Validate notes/reproducibility-practices.md adheres to minimal note conventions.

Usage: python3 evals/reproducibility-practices_eval.py

Checks performed:
- File exists at notes/reproducibility-practices.md
- Contains an H1 title (line starting with '# ')
- Contains a 'Summary' section
- Contains a 'Sources' section that itself contains at least one http(s):// URL

The Sources section is read in both of the styles CONTRIBUTING.md's template
allows: the label and the text on one line ("Sources: https://example.org/paper")
and the label on its own line with the sources listed below it. The section body
is the remainder of the header line joined with everything up to the next section
header, so a URL that appears further down the note (in a Reading list, say)
no longer counts as a source.

A section header is an H1/H2 line, a bare label alone on its line (digits,
hyphens, commas, slashes, apostrophes and parentheses allowed, so "Practical
suggestions (short checklist):" ends a section) or one of the labels
CONTRIBUTING.md names written inline with text after the colon ("Reading list:
Author (2020) https://example.org/x").

Before the note is judged the script runs self_check() over fixture strings; a
wrong extraction returns 2 instead of passing or failing the note.

Returns 0 on success, 1 on a failed check, 2 on a read error or failed self-check.
"""

import re
import sys
import os

NOTE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "notes", "reproducibility-practices.md")

# Header matcher for the Sources section. It matches the LABEL and its colon
# only - never the rest of the line - so an inline section keeps its text
# instead of being read as absent. Same shape as note-format_eval.py's
# SOURCES_HEADER_RE, with IGNORECASE so it agrees with has_section() below.
SOURCES_HEADER_RE = re.compile(r"^Sources\b[ \t]*:?[ \t]*", re.IGNORECASE | re.MULTILINE)

# A section ends at the next section header. Three shapes count, and the
# pattern is kept identical in every eval on purpose:
#   - a markdown heading line ("# ...", "## ...");
#   - a bare label alone on its line, which may carry digits, hyphens, commas,
#     slashes, apostrophes and parentheses ("Practical suggestions (short
#     checklist):");
#   - one of the labels CONTRIBUTING.md names, written inline with text after
#     the colon ("Reading list: Author (2020) https://example.org/x").
# The inline form is deliberately restricted to the known labels so an ordinary
# prose line that happens to end in a colon does not cut a section short.
SECTION_LABELS = ("Summary", r"Motivation[ \t]*&[ \t]*Background", "Sources", "Reading list", "Eval")
SECTION_END_RE = re.compile(
    r"^(?:#\s"
    r"|[A-Z][A-Za-z0-9 &,'()/-]*:[ \t]*$"
    r"|(?:" + "|".join(SECTION_LABELS) + r")\b[ \t]*:)",
    re.MULTILINE,
)


def section_end(rest):
    """Return the first section header in `rest`, ignoring one at offset 0.

    A body starts immediately after its own header, so a header matching at
    offset 0 would end the section where it begins and always yield an empty
    body.
    """
    for m in SECTION_END_RE.finditer(rest):
        if m.start() == 0:
            continue
        return m
    return None


URL_RE = re.compile(r"https?://[^\s)\]\">']+", re.IGNORECASE)


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


def extract_section(text, header_re):
    """Return a section body, or None when the header is absent.

    The header regex matches the label and its colon only, so text[m.end():]
    already begins with whatever was written after "Sources:" on the same line.
    The body ends at the next section header or at the end of the note. An
    empty string is a real answer - the section exists and is blank - and is
    distinct from None.
    """
    m = header_re.search(text)
    if not m:
        return None
    rest = text[m.end():]
    end = section_end(rest)
    return rest[: end.start()] if end else rest


def sources_have_url(text):
    """True when the note's Sources section itself contains an http(s) URL."""
    body = extract_section(text, SOURCES_HEADER_RE)
    if body is None:
        return False
    return bool(URL_RE.search(body))


# (label, note text, expected sources_have_url result)
SELF_CHECK_CASES = (
    (
        "inline Sources with a URL",
        "# T\n\nSources: https://example.org/paper\n\nEval:\n- See evals/t_eval.py\n",
        True,
    ),
    (
        "block Sources with URLs below",
        "# T\n\nSources:\n1. https://example.org/a\n2. https://example.org/b\n\nReading list:\n- x\n",
        True,
    ),
    (
        "empty Sources with a URL in a later section",
        "# T\n\nSources:\n\nReading list:\n- https://example.org/elsewhere\n",
        False,
    ),
    (
        "no Sources section at all",
        "# T\n\nSummary: text with https://example.org/inline in it.\n",
        False,
    ),
    (
        "Sources with prose only and a URL under a later heading",
        "# T\n\nSources: see the printed handout\n\n# Appendix\n\nhttps://example.org/late\n",
        False,
    ),
    (
        "empty Sources followed by an inline Reading list header",
        "# T\n\nSources:\n\nReading list: Author (2020) https://example.org/x\n",
        False,
    ),
    (
        "empty Sources followed by a punctuated bare header",
        "# T\n\nSources:\n\nPractical suggestions (short checklist):\n- https://example.org/y\n",
        False,
    ),
)

# (label, note text, expected extract_section body after .strip(); None = no section)
SECTION_CASES = (
    ("header at end of file", "# T\n\nSources:", ""),
    ("missing header", "# T\n\nSummary: x\n", None),
    (
        "inline body with more lines under it",
        "# T\n\nSources: https://example.org/a\nhttps://example.org/b\n\nEval:\n- x\n",
        "https://example.org/a\nhttps://example.org/b",
    ),
    (
        "an inline following header ends the body",
        "# T\n\nSources: https://example.org/a\nReading list: x https://example.org/b\n",
        "https://example.org/a",
    ),
    (
        "a punctuated bare header ends the body",
        "# T\n\nSources: https://example.org/a\n\nPractical suggestions (short checklist):\n- x\n",
        "https://example.org/a",
    ),
)


def self_check():
    """Exercise the Sources extraction on fixtures. Return failure strings."""
    failures = []
    for label, text, expected in SELF_CHECK_CASES:
        try:
            got = sources_have_url(text)
        except Exception as exc:  # a broken regex must not look like a note problem
            failures.append("%s: sources_have_url raised %r" % (label, exc))
            continue
        if got != expected:
            failures.append("%s: expected %r, got %r" % (label, expected, got))
    for label, text, expected in SECTION_CASES:
        try:
            body = extract_section(text, SOURCES_HEADER_RE)
        except Exception as exc:
            failures.append("%s: extract_section raised %r" % (label, exc))
            continue
        if expected is None:
            if body is not None:
                failures.append("%s: expected None, got %r" % (label, body))
        elif body is None:
            failures.append("%s: expected %r, got None" % (label, expected))
        elif body.strip() != expected:
            failures.append("%s: expected %r, got %r" % (label, expected, body.strip()))
    return failures


def main():
    check_failures = self_check()
    if check_failures:
        print("ERROR: Sources self-check failed - not judging the note with a broken extractor", file=sys.stderr)
        for failure in check_failures:
            print("  - %s" % failure, file=sys.stderr)
        return 2
    print("self-check: %d Sources case(s) OK" % (len(SELF_CHECK_CASES) + len(SECTION_CASES)))

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
            print("FAIL: the 'Sources' section itself contains no http(s):// URL")
            ok = False
        else:
            print("OK: 'Sources' contains a URL")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
