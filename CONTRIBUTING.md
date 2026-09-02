Purpose and scope

This repository is an open research notebook on paths to general intelligence — notes, reading list and runnable evals.

This CONTRIBUTING.md establishes concise conventions for notes, small runnable eval scripts, and the PR checklist so contributors and reviewers share a minimal common format.

Note format rules

- Location and filename: notes/<topic>.md (lowercase, dash-separated words preferred).
- Required top sections (in this order):
  - Title (H1, the note's short descriptive title)
  - Summary (2–4 sentences explaining the idea and main claim)
  - Motivation & Background (context and why the idea matters)
  - Sources (numbered list with full URLs; at least one URL required)
  - Reading list (optional annotated list of important references)
  - Eval (optional): a short line linking to any matching evals/<topic>_eval.py

Minimal note template (copyable):

# My Topic Title

Summary: Two to four sentences summarizing the idea and claim.

Motivation & Background:

- ...

Sources:
1. https://example.org/paper

Reading list:
- Author (Year). Paper title. Short note.

Eval:
- See evals/my-topic_eval.py (if provided)

Eval script rules

- Location and filename: evals/<topic>_eval.py
- Must run with python3 and use only the Python standard library.
- Include a module-level docstring that explains purpose and usage.
- Must exit with status 0 on success and non-zero on failure.
- New per-note evals import the shared checks instead of copying them: put the
  eval's own directory on sys.path and call `from note_checks import check_note`,
  then `sys.exit(check_note("<topic>.md"))`. Change a check once, in
  evals/note_checks.py, and every note eval picks it up.
- Provide a safe main() harness; example:

"""Example eval harness
Usage: python3 evals/example_eval.py
"""

def main():
    # run a small check, print results, and use sys.exit(0) on success
    print("OK")
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())

PR checklist for contributors

- Add or modify files only under notes/ or evals/ and follow the naming rules above.
- Notes include the required sections and at least one URL in Sources.
- Evals include module docstring, a main() harness, and run locally with python3.
- The PR description includes a short sentence matching the README phrasing: "Open research notebook on paths to general intelligence — notes, reading list and runnable evals."
- Provide run instructions in the PR body (how to run the eval locally).

How reviewers should verify

- Confirm CONTRIBUTING.md is present at repo root and follows the rules above.
- Confirm README.md links to CONTRIBUTING.md.
- For changed or added notes/evals, verify the checklist items in a quick local run.

Notes

Keep this short and example-driven; update later if templates or CI are added.