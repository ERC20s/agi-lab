"""Check that every note and every eval stay paired.

Usage: python3 evals/note-coverage_eval.py

Every other eval in this repository validates one hard-coded note. Nothing
checked the set as a whole, so a note added without an eval, an eval whose
note was renamed, or a note pointing at an eval file that no longer exists
all passed a green run. This eval closes that gap.

Checks performed (all repository-wide, standard library only):
- Every notes/<topic>.md has a matching evals/<topic>_eval.py
- Every evals/<topic>_eval.py has a matching notes/<topic>.md
- Every evals/... path named in a note's "Eval:" section exists on disk

Meta-evals — evals that validate the repository rather than one note, listed
in META_EVALS below — are exempt from the second rule: they are not asked for
a note of their own.

Topic matching is exact and case-sensitive on the dash-separated filename:
notes/chain-of-thought.md pairs with evals/chain-of-thought_eval.py and with
nothing else.

The "Eval:" section is read in both of the styles CONTRIBUTING.md allows: the
label and the text on one line ("Eval: See evals/foo_eval.py") and the label on
its own line with the reference below it. EVAL_HEADER_RE matches the label and
its colon only - never the rest of the line - so the section body starts with
whatever was written after the colon and an inline reference is scanned like any
other. This mirrors the fix already made in note-format_eval.py.

Before any note is judged the script runs self_check(), a set of fixture strings
that exercise eval_section (inline Eval line, block Eval header with the
reference below, header at end of file, inline header followed by a later
section, missing header). A wrong extraction fails the run instead of quietly
passing notes whose references were never looked at.

Returns 0 on success, 1 on a coverage failure, 2 if the layout cannot be read or
the self-check fails.
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTES_DIR = os.path.join(ROOT, "notes")
EVALS_DIR = os.path.join(ROOT, "evals")

EVAL_SUFFIX = "_eval.py"

# Evals that check the repository as a whole, not a single note. They pair
# with no note and must not be reported as orphans.
META_EVALS = {"note-coverage_eval.py", "note-format_eval.py", "eval-conformance_eval.py", "stdlib_imports_eval.py", "runner_eval.py"}

# Files under notes/ that are not notes.
NOT_NOTES = {"readme.md"}

# A reference to an eval script as a note writes it: "See evals/foo_eval.py".
EVAL_REF_RE = re.compile(r"evals/[A-Za-z0-9._-]+\.py")

# The "Eval:" section header, and the shape of any following section header
# ("Sources:", "Reading list:", or a new H1) that ends it. The header matcher
# covers the LABEL and its colon only, so text[m.end():] already begins with
# whatever follows "Eval:" on the same line; an inline reference is therefore
# part of the section body instead of being skipped past.
EVAL_HEADER_RE = re.compile(r"^Eval\b[ \t]*:?[ \t]*", re.MULTILINE)
SECTION_END_RE = re.compile(r"^(#\s|[A-Z][A-Za-z &]*:\s*$)", re.MULTILINE)


def read_text(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def note_topics():
    """Return {topic: absolute path} for every note under notes/."""
    topics = {}
    for fn in sorted(os.listdir(NOTES_DIR)):
        if not fn.endswith(".md"):
            continue
        if fn.lower() in NOT_NOTES:
            continue
        topics[fn[: -len(".md")]] = os.path.join(NOTES_DIR, fn)
    return topics


def eval_topics():
    """Return ({topic: absolute path}, [meta eval filenames]) for evals/."""
    topics = {}
    metas = []
    for fn in sorted(os.listdir(EVALS_DIR)):
        if not fn.endswith(EVAL_SUFFIX):
            continue
        if fn in META_EVALS:
            metas.append(fn)
            continue
        topics[fn[: -len(EVAL_SUFFIX)]] = os.path.join(EVALS_DIR, fn)
    return topics, metas


def eval_section(text):
    """Return the body of the note's 'Eval:' section, or '' when there is none."""
    m = EVAL_HEADER_RE.search(text)
    if not m:
        return ""
    rest = text[m.end():]
    end = SECTION_END_RE.search(rest)
    return rest[: end.start()] if end else rest


def section_refs(text):
    """Return the sorted evals/... paths named in a note's Eval: section."""
    return sorted(set(EVAL_REF_RE.findall(eval_section(text))))


# (label, note text, expected sorted refs, expected stripped section body)
SELF_CHECK_CASES = (
    (
        "inline Eval line",
        "# T\n\nSummary: s\n\nEval: See evals/t_eval.py\n",
        ["evals/t_eval.py"],
        "See evals/t_eval.py",
    ),
    (
        "block Eval header with the reference below",
        "# T\n\nEval:\n\n- See evals/t_eval.py\n",
        ["evals/t_eval.py"],
        "- See evals/t_eval.py",
    ),
    (
        "Eval header at end of file",
        "# T\n\nEval:",
        [],
        "",
    ),
    (
        "inline Eval followed by a later section",
        "# T\n\nEval: See evals/t_eval.py\n\nSources:\n- https://example.com/x_eval.py\n",
        ["evals/t_eval.py"],
        "See evals/t_eval.py",
    ),
    (
        "missing Eval header",
        "# T\n\nSummary: s\n\nSources:\n- https://example.com\n",
        [],
        "",
    ),
)


def self_check():
    """Exercise eval_section on fixtures. Return a list of failure strings."""
    failures = []
    for label, text, expected_refs, expected_body in SELF_CHECK_CASES:
        try:
            body = eval_section(text)
            refs = section_refs(text)
        except Exception as exc:  # a broken regex must not look like a note problem
            failures.append("%s: eval_section raised %r" % (label, exc))
            continue
        if body.strip() != expected_body:
            failures.append("%s: expected body %r, got %r"
                            % (label, expected_body, body.strip()))
        if refs != expected_refs:
            failures.append("%s: expected refs %r, got %r"
                            % (label, expected_refs, refs))
    return failures


def check_note_references(topic, path, problems):
    """Every evals/... path a note names in its Eval: section must exist."""
    try:
        text = read_text(path)
    except OSError as exc:
        print("FAIL: %s - could not read notes/%s.md: %s" % (topic, topic, exc))
        problems.append(topic)
        return
    refs = section_refs(text)
    for ref in refs:
        target = os.path.join(ROOT, ref.replace("/", os.sep))
        if not os.path.isfile(target):
            print("FAIL: %s - notes/%s.md points at %s, which does not exist"
                  % (topic, topic, ref))
            problems.append(topic)


def main():
    check_failures = self_check()
    if check_failures:
        print("ERROR: eval_section self-check failed - not judging notes with a "
              "broken extractor", file=sys.stderr)
        for failure in check_failures:
            print("  - %s" % failure, file=sys.stderr)
        return 2
    print("self-check: %d eval_section case(s) OK" % len(SELF_CHECK_CASES))

    for label, path in (("notes/", NOTES_DIR), ("evals/", EVALS_DIR)):
        if not os.path.isdir(path):
            print("ERROR: expected directory %s at the repository root" % label,
                  file=sys.stderr)
            return 2

    notes = note_topics()
    evals, metas = eval_topics()

    if not notes:
        print("ERROR: no notes found under notes/", file=sys.stderr)
        return 2

    problems = []

    for topic, path in sorted(notes.items()):
        if topic in evals:
            print("OK: %s - notes/%s.md and evals/%s%s"
                  % (topic, topic, topic, EVAL_SUFFIX))
        else:
            print("FAIL: %s - notes/%s.md has no evals/%s%s"
                  % (topic, topic, topic, EVAL_SUFFIX))
            problems.append(topic)
        check_note_references(topic, path, problems)

    for topic in sorted(evals):
        if topic not in notes:
            print("FAIL: %s - evals/%s%s has no notes/%s.md"
                  % (topic, topic, EVAL_SUFFIX, topic))
            problems.append(topic)

    for fn in metas:
        print("OK: %s - meta-eval, exempt from the pairing rule" % fn)

    print("")
    print("notes: %d, per-note evals: %d, meta-evals: %d, problems: %d"
          % (len(notes), len(evals), len(metas), len(problems)))

    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
