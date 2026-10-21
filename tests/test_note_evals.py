"""Tests for the note-eval code on main: the three per-note evals and note-format_eval.py.

Each per-note eval is a self-contained copy of the same checks (evals/README.md:
the shared-module route was voted down), so every test here runs once per
per-note eval via the `note_eval` fixture.
"""

import re
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent

GOOD_NOTE = (
    "# Title\n\n"
    "Summary: Two sentences. About a thing.\n\n"
    "Motivation & Background:\n\n- why\n\n"
    "Sources:\n1. https://example.org/paper\n\n"
    "Reading list:\n- Someone (2020). A paper.\n\n"
    "Eval:\n- See evals/title_eval.py\n"
)


def test_self_check_passes(note_eval: ModuleType) -> None:
    assert note_eval.self_check() == []


def test_self_check_catches_a_broken_section_end(
    note_eval: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A section-end regex that never matches lets the Sources body run to the
    # end of the note; the self-check must notice and main() must refuse (2).
    monkeypatch.setattr(note_eval, "SECTION_END_RE", re.compile(r"(?!)"))
    failures = note_eval.self_check()
    assert any("empty Sources with a URL in a later section" in f for f in failures)
    assert note_eval.main() == 2
    assert "self-check failed" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("# T\n\nSources:\n1. https://example.org/a\n", True),
        ("# T\n\nSources: https://example.org/a\n", True),
        ("# T\n\nSources:\n- printed handout\n\nReading list:\n- https://example.org/a\n", False),
        ("# T\n\nSummary: see https://example.org/a\n", False),
    ],
)
def test_sources_have_url_only_counts_the_sources_section(
    note_eval: ModuleType, text: str, expected: bool
) -> None:
    assert note_eval.sources_have_url(text) is expected


def test_extract_section_stops_at_the_next_header(note_eval: ModuleType) -> None:
    body = note_eval.extract_section(GOOD_NOTE, note_eval.SOURCES_HEADER_RE)
    assert body.strip() == "1. https://example.org/paper"
    assert note_eval.extract_section("# T\n\nSummary: x\n", note_eval.SOURCES_HEADER_RE) is None


@pytest.mark.parametrize(
    ("text", "code", "message"),
    [
        (GOOD_NOTE, 0, "OK: 'Sources' contains a URL"),
        (GOOD_NOTE.replace("# Title\n", "Title\n"), 1, "FAIL: missing H1 title"),
        (GOOD_NOTE.replace("Summary:", "Overview:"), 1, "FAIL: missing 'Summary' section"),
        (GOOD_NOTE.replace("Sources:", "Refs:"), 1, "FAIL: missing 'Sources' section"),
        (
            GOOD_NOTE.replace("1. https://example.org/paper", "1. a printed handout"),
            1,
            "FAIL: the 'Sources' section itself contains no http(s):// URL",
        ),
    ],
)
def test_main_judges_the_note(
    note_eval: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    text: str,
    code: int,
    message: str,
) -> None:
    note = tmp_path / "note.md"
    note.write_text(text, encoding="utf-8")
    monkeypatch.setattr(note_eval, "NOTE_PATH", str(note))
    assert note_eval.main() == code
    assert message in capsys.readouterr().out


def test_main_returns_2_when_the_note_is_missing(
    note_eval: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(note_eval, "NOTE_PATH", str(tmp_path / "absent.md"))
    assert note_eval.main() == 2


def test_each_per_note_eval_checks_its_own_note(note_eval: ModuleType) -> None:
    assert note_eval.__file__ is not None
    topic = Path(note_eval.__file__).name[: -len("_eval.py")]
    assert Path(note_eval.NOTE_PATH).resolve() == ROOT / "notes" / f"{topic}.md"


def test_section_end_pattern_is_identical_across_note_evals(
    note_eval: ModuleType, note_format: ModuleType
) -> None:
    # evals/README.md: the pattern "is written identically in all five note
    # evals"; a drifted copy would split sections differently.
    assert note_eval.SECTION_END_RE.pattern == note_format.SECTION_END_RE.pattern
    assert note_eval.URL_RE.pattern == note_format.URL_RE.pattern


def test_note_format_self_check_passes(note_format: ModuleType) -> None:
    assert note_format.self_check() == []


def test_note_format_reads_inline_and_block_sections(note_format: ModuleType) -> None:
    summary = note_format.extract_section(GOOD_NOTE, note_format.SUMMARY_HEADER_RE)
    motivation = note_format.extract_section(GOOD_NOTE, note_format.MOTIVATION_HEADER_RE)
    assert summary.strip() == "Two sentences. About a thing."
    assert motivation.strip() == "- why"
    assert note_format.eval_section(GOOD_NOTE).strip() == "- See evals/title_eval.py"
    assert note_format.eval_section("# T\n\nSummary: x\n") == ""
