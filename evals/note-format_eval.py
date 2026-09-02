"""Check every notes/*.md follows CONTRIBUTING.md's required note format.

Usage: python3 evals/note-format_eval.py

This meta-eval runs over every notes/<topic>.md (skipping readme.md) and checks
- an H1 title (a line starting with '# ')
- a non-empty Summary section
- a Motivation & Background section (present)
- a Sources section that contains at least one http(s):// URL, where the URL
  must appear inside the Sources section only (bounded by the next header)
- an Eval section that names the note's matching evals/<topic>_eval.py

It prints one OK/FAIL line per note and a final summary. Exit codes: 0 on
success, 1 on any per-note failure, 2 if the notes/ or evals/ layout cannot be
read.
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTES_DIR = os.path.join(ROOT, "notes")
EVALS_DIR = os.path.join(ROOT, "evals")

# Files under notes/ that are not notes.
NOT_NOTES = {"readme.md"}

# Section boundary heuristic used elsewhere in the repo.
SECTION_END_RE = re.compile(r"^(#\s|[A-Z][A-Za-z &]*:\s*$)", re.MULTILINE)

URL_RE = re.compile(r"https?://\S+")


def read_text(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def note_topics():
    topics = {}
    try:
        entries = sorted(os.listdir(NOTES_DIR))
    except OSError as exc:
        print("ERROR: could not read notes/ directory: %s" % exc, file=sys.stderr)
        return None
    for fn in entries:
        if not fn.endswith(".md"):
            continue
        if fn.lower() in NOT_NOTES:
            continue
        topics[fn[: -len(".md")]] = os.path.join(NOTES_DIR, fn)
    return topics


def section_body(text, header_name):
    """Return the body of the named section (text after the header), or '' if
    the header is not found. Header matching is case-insensitive and matches a
    line that starts with the header name (e.g. 'Summary:' or 'Summary')."""
    pattern = re.compile(rf"^{re.escape(header_name)}\b", re.IGNORECASE | re.MULTILINE)
    m = pattern.search(text)
    if not m:
        return ""
    rest = text[m.end():]
    end = SECTION_END_RE.search(rest)
    return rest[: end.start()] if end else rest


def has_h1(text):
    for line in text.splitlines():
        if line.strip().startswith("# "):
            return True
    return False


def check_note(topic, path):
    reasons = []
    try:
        text = read_text(path)
    except OSError as exc:
        return [f"could not read notes/{topic}.md: {exc}"]

    if not has_h1(text):
        reasons.append("missing H1 title (line starting with '# ')")

    summary = section_body(text, "Summary")
    if not summary.strip():
        reasons.append("missing or empty 'Summary' section")

    motiv = section_body(text, "Motivation & Background")
    if not motiv.strip():
        reasons.append("missing 'Motivation & Background' section")

    sources = section_body(text, "Sources")
    if not sources.strip():
        reasons.append("missing 'Sources' section")
    else:
        if not URL_RE.search(sources):
            reasons.append("'Sources' section does not contain an http(s):// URL")

    # Eval: must name evals/<topic>_eval.py inside the Eval section only
    eval_section = section_body(text, "Eval")
    expected = f"evals/{topic}_eval.py"
    if not eval_section.strip():
        reasons.append("missing 'Eval' section")
    else:
        if expected not in eval_section:
            reasons.append(f"'Eval' section does not name {expected}")

    return reasons


def main():
    # quick sanity checks on repository layout
    if not os.path.isdir(NOTES_DIR):
        print("ERROR: expected directory notes/ at the repository root", file=sys.stderr)
        return 2
    if not os.path.isdir(EVALS_DIR):
        print("ERROR: expected directory evals/ at the repository root", file=sys.stderr)
        return 2

    topics = note_topics()
    if topics is None:
        return 2
    if not topics:
        print("ERROR: no notes found under notes/", file=sys.stderr)
        return 2

    problems = []

    for topic, path in sorted(topics.items()):
        reasons = check_note(topic, path)
        if reasons:
            print(f"FAIL: {topic} - {"; ".join(reasons)}")
            problems.append(topic)
        else:
            print(f"OK: {topic} - notes/{topic}.md conforms to note format")

    print("")
    print("notes: %d, problems: %d" % (len(topics), len(problems)))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
