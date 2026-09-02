"""Check note format: top-level sections and Eval references.

Usage: python3 evals/note-format_eval.py

Per-note checks (standard library only):
- Title: a H1 ("# ...") must appear
- Summary: a non-empty "Summary:" section
- Motivation & Background: a non-empty "Motivation & Background" section
- Sources: when a "Sources:" section is present it must contain at least one http(s) URL; when there is no Sources section a URL anywhere in the note is accepted but a warning is emitted suggesting moving it into Sources
- Eval: the note's Eval: section must name evals/<topic>_eval.py and the file must exist on disk

Prints one OK/FAIL line per note and a short summary; returns 0 on success, 1 on failures, 2 on layout errors.
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTES_DIR = os.path.join(ROOT, "notes")
EVALS_DIR = os.path.join(ROOT, "evals")

NOT_NOTES = {"readme.md"}

# Heuristics reused from note-coverage_eval.py
EVAL_REF_RE = re.compile(r"evals/[A-Za-z0-9._-]+\.py")
EVAL_HEADER_RE = re.compile(r"^Eval\b[^\n]*$", re.MULTILINE)
SECTION_END_RE = re.compile(r"^(#\s|[A-Z][A-Za-z &]*:\s*$)", re.MULTILINE)

# Helpful header matchers for the required sections
TITLE_RE = re.compile(r"^#\s+.+$", re.MULTILINE)
SUMMARY_HEADER_RE = re.compile(r"^Summary\b.*$", re.MULTILINE)
MOTIVATION_HEADER_RE = re.compile(r"^Motivation\s*&\s*Background\b.*$", re.MULTILINE)
SOURCES_HEADER_RE = re.compile(r"^Sources\b.*$", re.MULTILINE)

URL_RE = re.compile(r"https?://[^\s)\]\">']+", re.IGNORECASE)


def read_text(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def note_topics():
    topics = {}
    for fn in sorted(os.listdir(NOTES_DIR)):
        if not fn.endswith(".md"):
            continue
        if fn.lower() in NOT_NOTES:
            continue
        topics[fn[: -len(".md")]] = os.path.join(NOTES_DIR, fn)
    return topics


def extract_section(text, header_re):
    m = header_re.search(text)
    if not m:
        return None
    rest = text[m.end():]
    end = SECTION_END_RE.search(rest)
    return rest[: end.start()] if end else rest


def eval_section(text):
    m = EVAL_HEADER_RE.search(text)
    if not m:
        return ""
    rest = text[m.end():]
    end = SECTION_END_RE.search(rest)
    return rest[: end.start()] if end else rest


def check_note(topic, path, problems, warnings):
    try:
        text = read_text(path)
    except OSError as exc:
        print("FAIL: %s - could not read notes/%s.md: %s" % (topic, topic, exc))
        problems.append(topic)
        return

    reasons = []

    # Title
    if not TITLE_RE.search(text):
        reasons.append("missing Title (H1 '# ...')")

    # Summary
    summary_body = extract_section(text, SUMMARY_HEADER_RE)
    if summary_body is None:
        reasons.append("missing Summary section")
    else:
        if not summary_body.strip():
            reasons.append("empty Summary section")

    # Motivation & Background
    mot_body = extract_section(text, MOTIVATION_HEADER_RE)
    if mot_body is None:
        reasons.append("missing Motivation & Background section")
    else:
        if not mot_body.strip():
            reasons.append("empty Motivation & Background section")

    # Sources
    sources_body = extract_section(text, SOURCES_HEADER_RE)
    if sources_body is not None:
        # explicit Sources section must contain at least one URL
        if not URL_RE.search(sources_body):
            reasons.append("Sources section has no http(s) URL")
    else:
        # no Sources section: accept a URL anywhere but warn, else fail
        if URL_RE.search(text):
            warnings.append((topic, "no Sources section: found URL elsewhere; consider moving it into Sources"))
        else:
            reasons.append("missing Sources section and no URL found in note")

    # Eval: section must list the matching evals/<topic>_eval.py
    ebody = eval_section(text)
    refs = sorted(set(EVAL_REF_RE.findall(ebody)))
    expected = "evals/%s_eval.py" % topic
    if expected in refs:
        # ensure file exists on disk
        target = os.path.join(ROOT, expected.replace("/", os.sep))
        if not os.path.isfile(target):
            reasons.append("Eval section names %s but the file does not exist" % expected)
    else:
        reasons.append("Eval section does not name %s" % expected)

    if reasons:
        print("FAIL: %s - %s" % (topic, "; ".join(reasons)))
        problems.append(topic)
    else:
        warn_text = ""
        for t, w in warnings:
            if t == topic:
                warn_text = " (warning: %s)" % w
        print("OK: %s - notes/%s.md%s" % (topic, topic, warn_text))


def main():
    for label, path in (("notes/", NOTES_DIR), ("evals/", EVALS_DIR)):
        if not os.path.isdir(path):
            print("ERROR: expected directory %s at the repository root" % label, file=sys.stderr)
            return 2

    notes = note_topics()
    if not notes:
        print("ERROR: no notes found under notes/", file=sys.stderr)
        return 2

    problems = []
    warnings = []

    for topic, path in sorted(notes.items()):
        check_note(topic, path, problems, warnings)

    print("")
    print("notes: %d, problems: %d, warnings: %d" % (len(notes), len(problems), len(warnings)))

    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
