"""Check every note under notes/: front matter, required sections, live links.

Usage: python scripts/check_notes.py [--timeout SECONDS] [--no-links] [--notes-dir DIR]

Per note (CONTRIBUTING.md, "Note format rules"):

- Front matter: the note opens with its H1 title ("# Title" on the first
  non-blank line) and the first section under the title is Summary.
  CONTRIBUTING.md defines no YAML block; the title and Summary are the
  required front of a note, so that is what is checked.
- Required sections: Summary, Motivation & Background, Sources and Eval are
  present, non-empty and in that order; Reading list is optional and, when
  present, sits between Sources and Eval. Sources carries an http(s) URL.
- Links: every http(s) URL in the Sources and Reading list sections (the
  note's reading list) must resolve: a HEAD request, falling back to GET when
  the server refuses HEAD, must end in a 2xx after redirects within
  --timeout seconds. A connection error, a timeout, a 5xx or a 429 is retried
  once; a second failure fails the note.

Sections are found with the header regexes and extract_section() of
evals/note-format_eval.py, loaded by path, so this script and the evals agree
on where a section starts and ends.

This is a network check, so it is not an eval: evals/run_all.py stays offline
and deterministic. --no-links runs the structural checks alone. Standard
library only. Exit 0 when every note passes, 1 when any check fails, 2 when
the notes directory or note-format_eval.py cannot be read.
"""

import argparse
import http.client
import importlib.util
import os
import re
import sys
import time
import urllib.error
import urllib.request
from types import ModuleType

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTES_DIR = os.path.join(ROOT, "notes")
NOTE_FORMAT_PATH = os.path.join(ROOT, "evals", "note-format_eval.py")

DEFAULT_TIMEOUT = 10.0
USER_AGENT = "agi-lab-notes-check (+https://github.com/ERC20s/agi-lab)"
# Worth one more try: the server or the path to it may be briefly unwell.
RETRY_STATUSES = {429, 500, 502, 503, 504}
# Servers that do not implement HEAD say so with one of these.
HEAD_REFUSED_STATUSES = {403, 405, 501}
RETRY_DELAY_SECONDS = 1.0

READING_LIST_HEADER_RE = re.compile(r"^Reading list\b[ \t]*:?[ \t]*", re.MULTILINE)
# Punctuation that ends a sentence rather than a URL.
URL_TRAILING = ".,;:!?"


def load_note_format(path: str = NOTE_FORMAT_PATH) -> ModuleType:
    """Import evals/note-format_eval.py by path (its name is not importable)."""
    spec = importlib.util.spec_from_file_location("note_format_eval", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_front_matter(text: str, nf: ModuleType) -> list[str]:
    """The note opens with a non-empty H1 title and Summary is its first section."""
    problems = []
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines or not re.match(r"#[ \t]+\S", lines[0]):
        problems.append("front matter: the first non-blank line is not an H1 title ('# Title')")
    summary = nf.SUMMARY_HEADER_RE.search(text)
    if summary is None:
        problems.append("front matter: no Summary section")
    else:
        others = [
            m.start()
            for m in (
                nf.MOTIVATION_HEADER_RE.search(text),
                nf.SOURCES_HEADER_RE.search(text),
                READING_LIST_HEADER_RE.search(text),
                nf.EVAL_HEADER_RE.search(text),
            )
            if m is not None
        ]
        if any(pos < summary.start() for pos in others):
            problems.append("front matter: Summary is not the first section under the title")
    return problems


def check_sections(text: str, nf: ModuleType) -> list[str]:
    """Required sections present, non-empty and in CONTRIBUTING.md's order."""
    required = (
        ("Summary", nf.SUMMARY_HEADER_RE),
        ("Motivation & Background", nf.MOTIVATION_HEADER_RE),
        ("Sources", nf.SOURCES_HEADER_RE),
        ("Eval", nf.EVAL_HEADER_RE),
    )
    problems = []
    positions = []
    for name, header_re in required:
        m = header_re.search(text)
        if m is None:
            problems.append(f"missing required section {name!r}")
            continue
        positions.append((m.start(), name))
        body = nf.extract_section(text, header_re)
        if body is None or not body.strip():
            problems.append(f"section {name!r} is empty")
    found = [name for _, name in positions]
    in_text_order = [name for _, name in sorted(positions)]
    if in_text_order != found:
        problems.append(
            "sections out of order: expected " + " -> ".join(found)
            + ", found " + " -> ".join(in_text_order)
        )

    reading = READING_LIST_HEADER_RE.search(text)
    sources = nf.SOURCES_HEADER_RE.search(text)
    evals = nf.EVAL_HEADER_RE.search(text)
    if reading is not None:
        if sources is not None and reading.start() < sources.start():
            problems.append("'Reading list' comes before 'Sources'")
        if evals is not None and reading.start() > evals.start():
            problems.append("'Reading list' comes after 'Eval'")

    sources_body = nf.extract_section(text, nf.SOURCES_HEADER_RE)
    if sources_body is not None and sources_body.strip() and not nf.URL_RE.search(sources_body):
        problems.append("the 'Sources' section contains no http(s) URL")
    return problems


def reading_list_urls(text: str, nf: ModuleType) -> list[str]:
    """Unique URLs from the Sources and Reading list sections, in note order."""
    urls: list[str] = []
    for header_re in (nf.SOURCES_HEADER_RE, READING_LIST_HEADER_RE):
        body = nf.extract_section(text, header_re)
        if not body:
            continue
        for raw in nf.URL_RE.findall(body):
            url = raw.rstrip(URL_TRAILING)
            if url not in urls:
                urls.append(url)
    return urls


def _request(url: str, method: str, timeout: float) -> int:
    """Return the final HTTP status of one request (redirects followed)."""
    req = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status)
    except urllib.error.HTTPError as e:
        return int(e.code)


def check_link(url: str, timeout: float = DEFAULT_TIMEOUT, retries: int = 1) -> str | None:
    """Return None when `url` resolves to a 2xx, else a reason it did not."""
    reason = "not checked"
    for attempt in range(retries + 1):
        if attempt:
            time.sleep(RETRY_DELAY_SECONDS)
        try:
            status = _request(url, "HEAD", timeout)
            if status in HEAD_REFUSED_STATUSES:
                status = _request(url, "GET", timeout)
        except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as e:
            # A timeout surfaces bare while reading, or wrapped in URLError
            # while connecting; either way it is reported as a timeout.
            # http.client raises HTTPException (not OSError) for a malformed
            # response or a URL it cannot parse, such as a non-numeric port:
            # that is a dead link too, not a reason to abort every note.
            cause = getattr(e, "reason", e)
            if isinstance(cause, TimeoutError):
                reason = f"timed out after {timeout:g}s"
            else:
                # BadStatusLine carries the raw line, CRLF included.
                reason = f"{type(e).__name__}: {str(cause).strip()}"
            continue
        if 200 <= status < 300:
            return None
        reason = f"HTTP {status}"
        if status not in RETRY_STATUSES:
            return reason
    return reason


def note_paths(notes_dir: str) -> list[str]:
    """notes/*.md, sorted; a README is documentation, not a note."""
    return [
        os.path.join(notes_dir, fn)
        for fn in sorted(os.listdir(notes_dir))
        if fn.endswith(".md") and fn.lower() != "readme.md"
    ]


def check_note(
    path: str, nf: ModuleType, links: bool = True, timeout: float = DEFAULT_TIMEOUT
) -> list[str]:
    """Every problem found in one note; an empty list means it passes."""
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    problems = check_front_matter(text, nf) + check_sections(text, nf)
    if links:
        for url in reading_list_urls(text, nf):
            reason = check_link(url, timeout=timeout)
            if reason is not None:
                problems.append(f"link does not resolve: {url} ({reason})")
    return problems


def positive_float(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number of seconds: {value!r}")
    if seconds <= 0:
        raise argparse.ArgumentTypeError("timeout must be greater than 0 seconds")
    return seconds


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--timeout",
        type=positive_float,
        default=DEFAULT_TIMEOUT,
        metavar="SECONDS",
        help=f"per-request timeout for each link (default: {DEFAULT_TIMEOUT:g})",
    )
    parser.add_argument("--no-links", action="store_true", help="skip the network link check")
    parser.add_argument("--notes-dir", default=NOTES_DIR, help="directory of notes to check")
    args = parser.parse_args(argv)

    try:
        nf = load_note_format()
        paths = note_paths(args.notes_dir)
    except (OSError, ImportError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    if not paths:
        print(f"ERROR: no notes (*.md) under {args.notes_dir}", file=sys.stderr)
        return 2

    failed = 0
    for path in paths:
        rel = os.path.relpath(path, ROOT)
        problems = check_note(path, nf, links=not args.no_links, timeout=args.timeout)
        if problems:
            failed += 1
            print(f"FAIL: {rel}")
            for problem in problems:
                print(f"  - {problem}")
        else:
            print(f"OK: {rel}")
    mode = "structure only (--no-links)" if args.no_links else "structure and links"
    print(f"{len(paths)} note(s) checked, {failed} failed [{mode}]")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
