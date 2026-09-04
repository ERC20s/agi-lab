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

Meta-evals — evals that validate the repository rather than one note — are
exempt from the second rule: they are not asked for a note of their own. A
meta-eval DECLARES ITSELF by assigning

    META_EVAL = True

at the top level of its module. The flag is read by parsing the file with ast
(declares_meta_eval below); the file is never imported or executed. The old
hand-maintained META_EVALS set is kept as a fallback so a file that predates the
flag, or one whose flag is written some way ast cannot see, still passes, but
nothing new has to be registered there.

Two guards keep the flag honest:
- Pairing wins. If notes/<topic>.md exists for a file that claims the flag, the
  file is treated as an ordinary per-note eval and a warning is printed, so the
  flag cannot be used to dodge a pairing that already exists.
- A file that will not parse is reported as a warning and treated as non-meta;
  eval-conformance_eval.py is the eval that fails syntax errors outright.

Topic matching is exact and case-sensitive on the dash-separated filename:
notes/chain-of-thought.md pairs with evals/chain-of-thought_eval.py and with
nothing else.

The "Eval:" section is read in both of the styles CONTRIBUTING.md allows: the
label and the text on one line ("Eval: See evals/foo_eval.py") and the label on
its own line with the reference below it. EVAL_HEADER_RE matches the label and
its colon only - never the rest of the line - so the section body starts with
whatever was written after the colon and an inline reference is scanned like any
other. This mirrors the fix already made in note-format_eval.py.

The section ends at the next section header: an H1/H2 line, a bare label alone on
its line (digits, hyphens, commas, slashes, apostrophes and parentheses allowed,
so "Practical suggestions (short checklist):" ends it) or one of the labels
CONTRIBUTING.md names written inline with text after the colon ("Sources: see
evals/z_eval.py"). References written outside the Eval section are therefore not
scanned.

Before any note is judged the script runs self_check(), two sets of fixture
strings: SELF_CHECK_CASES exercises eval_section (inline Eval line, block Eval
header with the reference below, header at end of file, inline header followed by
a later section, missing header) and META_FLAG_CASES exercises
declares_meta_eval (flag present, flag after a docstring and imports, annotated
flag, flag set to False, flag assigned inside a function, flag absent, a file
that will not parse). A wrong extraction or a wrong detection fails the run
instead of quietly passing notes whose references were never looked at, or
exempting a file that never claimed the flag.

Returns 0 on success, 1 on a coverage failure, 2 if the layout cannot be read or
the self-check fails.
"""

import ast
import os
import re
import sys

# This eval checks the repository as a whole, so it declares itself the same way
# it asks every other meta-eval to: a top-level META_EVAL = True.
META_EVAL = True

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTES_DIR = os.path.join(ROOT, "notes")
EVALS_DIR = os.path.join(ROOT, "evals")

EVAL_SUFFIX = "_eval.py"

# The name a meta-eval assigns at module level to declare itself.
META_FLAG_NAME = "META_EVAL"

# Fallback only. Evals that check the repository as a whole declare themselves
# with META_EVAL = True; these names are still honoured so a file that predates
# the flag is not suddenly reported as an orphan. Nothing new needs adding here.
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

# A section ends at the next section header. Three shapes count, and the
# pattern is kept identical in every eval on purpose:
#   - a markdown heading line ("# ...", "## ...");
#   - a bare label alone on its line, which may carry digits, hyphens, commas,
#     slashes, apostrophes and parentheses ("Practical suggestions (short
#     checklist):");
#   - one of the labels CONTRIBUTING.md names, written inline with text after
#     the colon ("Sources: see evals/z_eval.py in the repo").
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


def declares_meta_eval(source):
    """Return True when `source` assigns META_EVAL = True at module level.

    The text is PARSED, never executed: a file only counts as a meta-eval when
    its module body contains `META_EVAL = True` (or `META_EVAL: bool = True`) as
    a top-level statement. An assignment inside a function or class body, a
    value other than the literal True, and a missing name all return False.

    Raises SyntaxError when `source` will not parse; the caller decides what to
    do about that.
    """
    tree = ast.parse(source)
    for node in tree.body:  # top level only - no ast.walk
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if node.value is None:
            continue
        if not any(isinstance(t, ast.Name) and t.id == META_FLAG_NAME
                   for t in targets):
            continue
        value = node.value
        # `True` is an ast.Constant on modern Python, ast.NameConstant before.
        if isinstance(value, ast.Constant) and value.value is True:
            return True
    return False


def eval_topics(note_names=()):
    """Sort evals/ into per-note evals and meta-evals.

    Returns ({topic: absolute path}, [meta filenames], [warning strings]).

    A file is a meta-eval when it declares META_EVAL = True or is named in the
    META_EVALS fallback - UNLESS notes/<topic>.md exists, in which case pairing
    wins and the file is judged as an ordinary per-note eval.
    """
    note_names = set(note_names)
    topics = {}
    metas = []
    warnings = []
    for fn in sorted(os.listdir(EVALS_DIR)):
        if not fn.endswith(EVAL_SUFFIX):
            continue
        topic = fn[: -len(EVAL_SUFFIX)]
        path = os.path.join(EVALS_DIR, fn)
        declared = False
        try:
            declared = declares_meta_eval(read_text(path))
        except SyntaxError as exc:
            warnings.append("%s does not parse (%s) - treated as a per-note "
                            "eval; eval-conformance_eval.py reports the syntax "
                            "error" % (fn, exc))
        except OSError as exc:
            warnings.append("%s could not be read (%s) - treated as a per-note "
                            "eval" % (fn, exc))
        listed = fn in META_EVALS
        if declared or listed:
            if topic in note_names:
                warnings.append("%s claims to be a meta-eval but notes/%s.md "
                                "exists - pairing wins, it is checked as a "
                                "per-note eval" % (fn, topic))
            else:
                metas.append(fn)
                continue
        topics[topic] = path
    return topics, metas, warnings


def eval_section(text):
    """Return the body of the note's 'Eval:' section, or '' when there is none."""
    m = EVAL_HEADER_RE.search(text)
    if not m:
        return ""
    rest = text[m.end():]
    end = section_end(rest)
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
    (
        "inline Eval followed by an inline Sources header",
        "# T\n\nEval: See evals/t_eval.py\nSources: see evals/z_eval.py in the repo\n",
        ["evals/t_eval.py"],
        "See evals/t_eval.py",
    ),
    (
        "Eval section ended by a punctuated bare header",
        "# T\n\nEval:\n- See evals/t_eval.py\n\nPractical suggestions (short checklist):\n"
        "- also evals/z_eval.py\n",
        ["evals/t_eval.py"],
        "- See evals/t_eval.py",
    ),
)


# (label, module source, expected result: True, False or "error" for a file
# that will not parse)
META_FLAG_CASES = (
    ("bare flag", "META_EVAL = True\n", True),
    ("flag after a docstring and imports",
     '"""Doc."""\n\nimport os\n\nMETA_EVAL = True\n\nX = 1\n', True),
    ("annotated flag", "META_EVAL: bool = True\n", True),
    ("chained assignment", "META_EVAL = OTHER = True\n", True),
    ("flag set to False", "META_EVAL = False\n", False),
    ("flag set to a non-literal", "META_EVAL = 1 == 1\n", False),
    ("flag inside a function", "def f():\n    META_EVAL = True\n", False),
    ("flag inside a class", "class C:\n    META_EVAL = True\n", False),
    ("no flag at all", '"""Doc."""\nimport os\n\n\ndef main():\n    return 0\n', False),
    ("file that will not parse", "def (:\n", "error"),
)


def self_check():
    """Exercise eval_section and declares_meta_eval on fixtures.

    Returns a list of failure strings; an empty list means both extractors
    behave as this eval assumes they do.
    """
    failures = []
    for label, source, expected in META_FLAG_CASES:
        try:
            got = declares_meta_eval(source)
        except SyntaxError:
            got = "error"
        except Exception as exc:  # a broken detector must not look like a note problem
            failures.append("meta flag %s: declares_meta_eval raised %r"
                            % (label, exc))
            continue
        if got != expected:
            failures.append("meta flag %s: expected %r, got %r"
                            % (label, expected, got))
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
        print("ERROR: self-check failed - not judging notes with a broken "
              "extractor", file=sys.stderr)
        for failure in check_failures:
            print("  - %s" % failure, file=sys.stderr)
        return 2
    print("self-check: %d eval_section case(s) and %d META_EVAL flag case(s) OK"
          % (len(SELF_CHECK_CASES), len(META_FLAG_CASES)))

    for label, path in (("notes/", NOTES_DIR), ("evals/", EVALS_DIR)):
        if not os.path.isdir(path):
            print("ERROR: expected directory %s at the repository root" % label,
                  file=sys.stderr)
            return 2

    notes = note_topics()
    evals, metas, meta_warnings = eval_topics(notes)

    for warning in meta_warnings:
        print("WARN: %s" % warning)

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
        try:
            declared = declares_meta_eval(read_text(os.path.join(EVALS_DIR, fn)))
        except (SyntaxError, OSError):
            declared = False
        how = ("declares META_EVAL = True" if declared
               else "listed in the META_EVALS fallback - add META_EVAL = True "
                    "to the file")
        print("OK: %s - meta-eval (%s), exempt from the pairing rule"
              % (fn, how))

    print("")
    print("notes: %d, per-note evals: %d, meta-evals: %d, problems: %d"
          % (len(notes), len(evals), len(metas), len(problems)))

    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
