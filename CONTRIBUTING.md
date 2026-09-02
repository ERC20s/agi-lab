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
  - Eval (required): a short line linking to the matching evals/<topic>_eval.py

Pairing rule (notes and evals come in pairs)

- Every notes/<topic>.md must have a matching evals/<topic>_eval.py, and every
  evals/<topic>_eval.py must have a matching notes/<topic>.md. The topic is the
  filename, matched exactly and case-sensitively: notes/chain-of-thought.md
  pairs with evals/chain-of-thought_eval.py and with nothing else.
- Any evals/... path a note names in its Eval section must exist in the repository.
- Exemption: a meta-eval — an eval that checks the repository as a whole rather
  than one note — needs no note of its own. Meta-evals are listed by filename in
  the META_EVALS set of evals/note-coverage_eval.py; add a new one there.
- evals/note-coverage_eval.py enforces all three rules and runs as part of
  `python evals/run_all.py`, so a note added without its eval, or an eval whose
  note was renamed, turns the run red and names the topic.
- evals/note-format_eval.py is an additional repository-wide meta-eval that
  validates each note's internal structure (H1, Summary, Motivation & Background,
  Sources with at least one URL bounded to the Sources section, and an Eval line
  pointing at evals/<topic>_eval.py). It is listed in META_EVALS and runs with
  the other evals.

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
- A new note ships with its evals/<topic>_eval.py in the same pull request (and a
  new eval ships with its note), so evals/note-coverage_eval.py stays green.
- Evals include module docstring, a main() harness, and run locally with python3.
- The PR description includes a short sentence matching the README phrasing: "Open research notebook on paths to general intelligence — notes, reading list and runnable evals."
- Provide run instructions in the PR body (how to run the eval locally).

How reviewers should verify

- Confirm CONTRIBUTING.md is present at repo root and follows the rules above.
- Confirm README.md links to CONTRIBUTING.md.
- For changed or added notes/evals, verify the checklist items in a quick local run.

Notes

Keep this short and example-driven; update later if templates or CI are added.