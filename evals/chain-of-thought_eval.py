"""Validate notes/chain-of-thought.md against CONTRIBUTING.md's note format.

Usage: python3 evals/chain-of-thought_eval.py

Checks performed:
- File exists at notes/chain-of-thought.md
- Contains an H1 title (line starting with '# ')
- Contains a non-empty 'Summary' section
- Contains a non-empty 'Motivation & Background' section
- Contains a 'Sources' section with at least one http(s):// URL *inside it*
- Summary, Motivation & Background and Sources appear in that order

Section grammar (see "Note format rules" in CONTRIBUTING.md): a section label is
either a line starting at column 0 of the form 'Name:' (anything after the colon
is the first line of that section's content) or a markdown heading line
('# Name' through '###### Name'). A section's content runs to the next label.
Section names are compared case-insensitively and 'and' is accepted for '&'.

Returns 0 on success, 1 on a failed check, 2 if the note cannot be read.
"""

import re
import sys
import os

NOTE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "notes", "chain-of-thought.md")

REQUIRED_ORDER = ("Summary", "Motivation & Background", "Sources")

# A column-0 label: 'Name:' with no sentence punctuation in the name.
LABEL_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 &()'/\-]{0,78}):(?:\s|$)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
URL_RE = re.compile(r"https?://\S+")


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


def normalize(name):
    name = re.sub(r"\s+", " ", name).strip().rstrip(":").strip().lower()
    return name.replace(" and ", " & ")


def split_sections(text):
    """Slice the note into an ordered list of (normalized name, content) pairs."""
    sections = []
    current_name = None
    current_lines = []
    for line in text.splitlines():
        heading = HEADING_RE.match(line)
        label = LABEL_RE.match(line) if heading is None else None
        if heading is None and label is None:
            if current_name is not None:
                current_lines.append(line)
            continue
        if current_name is not None:
            sections.append((current_name, "\n".join(current_lines)))
        if heading is not None:
            current_name = normalize(heading.group(2))
            current_lines = []
        else:
            current_name = normalize(label.group(1))
            # Keep whatever followed the colon on the label line.
            current_lines = [line[label.end(1) + 1:]]
    if current_name is not None:
        sections.append((current_name, "\n".join(current_lines)))
    return sections


def find_section(sections, name):
    """Return (index, content) of the first section called name, else (-1, None)."""
    target = normalize(name)
    for index, (section_name, content) in enumerate(sections):
        if section_name == target:
            return index, content
    return -1, None


def main():
    text = read_note(NOTE_PATH)
    if text is None:
        return 2

    ok = True
    sections = split_sections(text)

    if not has_h1(text):
        print("FAIL: missing H1 title (line starting with '# ')")
        ok = False
    else:
        print("OK: found H1 title")

    positions = {}
    for label in REQUIRED_ORDER:
        index, content = find_section(sections, label)
        if index < 0:
            print(f"FAIL: missing '{label}' section")
            ok = False
            continue
        positions[label] = index
        if not content.strip():
            print(f"FAIL: '{label}' section is empty")
            ok = False
        else:
            print(f"OK: found non-empty '{label}' section")

    if len(positions) == len(REQUIRED_ORDER):
        order = [positions[label] for label in REQUIRED_ORDER]
        if order != sorted(order):
            print("FAIL: sections out of order (expected " + ", then ".join(REQUIRED_ORDER) + ")")
            ok = False
        else:
            print("OK: " + ", ".join(REQUIRED_ORDER) + " appear in that order")

    index, sources = find_section(sections, "Sources")
    if index >= 0:
        if URL_RE.search(sources or ""):
            print("OK: 'Sources' contains an http(s):// URL")
        else:
            print("FAIL: 'Sources' section does not contain an http(s):// URL")
            ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
