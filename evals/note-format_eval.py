"""Check note format: top-level sections and Eval references.

Usage: python3 evals/note-format_eval.py

Per-note checks (standard library only):
- Title: a H1 ("# ...") must appear
- Summary: a non-empty "Summary:" section
- Motivation & Background: a non-empty "Motivation & Background" section
- Sources: when a "Sources:" section is present it must contain at least one http(s) URL; when there is no Sources section a URL anywhere in the note is accepted but a warning is emitted suggesting moving it into Sources
- Eval: the note's Eval: section must name evals/<topic>_eval.py and the file must exist on disk

Section bodies are read in both of the styles CONTRIBUTING.md allows: the label and
the text on one line ("Summary: two sentences ...") and the label on its own line
with the text below it. The body is the remainder of the header line joined with
everything up to the next section header; a section whose body is blank either way
is still reported as empty.

Before the notes are checked the script runs self_check(), a set of fixture strings
that exercise extract_section (inline header, header with body below, header at end
of file, multi-line inline body, missing header). A wrong extraction fails the run
before any note is judged by it.

Prints one OK/FAIL line per note and a short summary; returns 0 on success, 1 on failures, 2 on layout errors or a failed self-check.
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
SECTION_END_RE = re.compile(r"^(#\s|[A-Z][A-Za-z &]*:\s*$)", re.MULTILINE)

# Header matchers for the required sections. Each one matches the LABEL and its
# colon only - never the rest of the line - so that an inline section
# ("Summary: one sentence.") keeps its text instead of being read as empty.
TITLE_RE = re.compile(r"^#\s+.+$", re.MULTILINE)
SUMMARY_HEADER_RE = re.compile(r"^Summary\b[ \t]*:?[ \t]*", re.MULTILINE)
MOTIVATION_HEADER_RE = re.compile(r"^Motivation[ \t]*&[ \t]*Background\b[ \t]*:?[ \t]*", re.MULTILINE)
SOURCES_HEADER_RE = re.compile(r"^Sources\b[ \t]*:?[ \t]*", re.MULTILINE)
EVAL_HEADER_RE = re.compile(r"^Eval\b[ \t]*:?[ \t]*", re.MULTILINE)

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
    """Return a section body, or None when the header is absent.

    The header regexes match the label and its colon only, so text[m.end():]
    already begins with whatever was written after "Summary:" on the same line.
    The body therefore covers both styles CONTRIBUTING.md allows: the inline
    form, where the prose sits on the label's own line, and the block form,
    where the label stands alone and the prose follows underneath.

    The body ends at the next section header (SECTION_END_RE) or at the end of
    the note. An empty string is a real answer - the section exists and is
    blank - and is distinct from None.
    """
    m = header_re.search(text)
    if not m:
        return None
    rest = text[m.end():]
    end = SECTION_END_RE.search(rest)
    return rest[: end.start()] if end else rest


def eval_section(text):
    body = extract_section(text, EVAL_HEADER_RE)
    return body if body is not None else ""


# (label, note text, header regex, expected body after .strip(); None = no section)
SELF_CHECK_CASES = (
    (
        "inline header",
        "# T\n\nSummary: inline body text.\n\nMotivation & Background:\n\n- x\n",
        SUMMARY_HEADER_RE,
        "inline body text.",
    ),
    (
        "header with body below",
        "# T\n\nSummary:\n\nblock body text.\n\nSources:\n- https://example.com\n",
        SUMMARY_HEADER_RE,
        "block body text.",
    ),
    (
        "header at end of file",
        "# T\n\nSummary:",
        SUMMARY_HEADER_RE,
        "",
    ),
    (
        "inline header with more lines under it",
        "# T\n\nSummary: first part.\nsecond part.\n\nSources:\n- https://example.com\n",
        SUMMARY_HEADER_RE,
        "first part.\nsecond part.",
    ),
    (
        "missing header",
        "# T\n\nMotivation & Background:\n\n- x\n",
        SUMMARY_HEADER_RE,
        None,
    ),
    (
        "inline Sources header",
        "# T\n\nSources: https://example.com\n\nEval:\n- See evals/t_eval.py\n",
        SOURCES_HEADER_RE,
        "https://example.com",
    ),
    (
        "inline Motivation header",
        "# T\n\nMotivation & Background: why it matters.\n\nSources:\n- https://example.com\n",
        MOTIVATION_HEADER_RE,
        "why it matters.",
    ),
    (
        "inline Eval header",
        "# T\n\nEval: See evals/t_eval.py\n",
        EVAL_HEADER_RE,
        "See evals/t_eval.py",
    ),
)


def self_check():
    """Exercise extract_section on fixtures. Return a list of failure strings."""
    failures = []
    for label, text, header_re, expected in SELF_CHECK_CASES:
        try:
            body = extract_section(text, header_re)
        except Exception as exc:  # a broken regex must not look like a note problem
            failures.append("%s: extract_section raised %r" % (label, exc))
            continue
        if expected is None:
            if body is not None:
                failures.append("%s: expected None, got %r" % (label, body))
            continue
        if body is None:
            failures.append("%s: expected %r, got None" % (label, expected))
        elif body.strip() != expected:
            failures.append("%s: expected %r, got %r" % (label, expected, body.strip()))
    return failures


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
    check_failures = self_check()
    if check_failures:
        print("ERROR: extract_section self-check failed - not judging notes with a broken extractor", file=sys.stderr)
        for failure in check_failures:
            print("  - %s" % failure, file=sys.stderr)
        return 2
    print("self-check: %d extract_section case(s) OK" % len(SELF_CHECK_CASES))

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
