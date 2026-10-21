"""Tests for scripts/check_notes.py: front matter, sections and the link check.

Links are checked against a throwaway HTTP server on the loopback interface,
so these tests need no network.
"""

import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent

GOOD_NOTE = (
    "# Title\n\n"
    "Summary: Two sentences. About a thing.\n\n"
    "Motivation & Background:\n\n- why\n\n"
    "Sources:\n1. https://example.org/paper\n\n"
    "Reading list:\n- Someone (2020). https://example.org/reading.\n\n"
    "Eval:\n- See evals/title_eval.py\n"
)


def problems(check_notes: ModuleType, note_format: ModuleType, text: str) -> list[str]:
    return check_notes.check_front_matter(text, note_format) + check_notes.check_sections(
        text, note_format
    )


def test_good_note_has_no_problems(check_notes: ModuleType, note_format: ModuleType) -> None:
    assert problems(check_notes, note_format, GOOD_NOTE) == []


def test_reading_list_is_optional(check_notes: ModuleType, note_format: ModuleType) -> None:
    text = GOOD_NOTE.replace("Reading list:\n- Someone (2020). https://example.org/reading.\n\n", "")
    assert problems(check_notes, note_format, text) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Intro line\n\n" + GOOD_NOTE,
            "front matter: the first non-blank line is not an H1 title ('# Title')",
        ),
        (GOOD_NOTE.replace("# Title", "#"), "front matter: the first non-blank line is not an H1 title"),
        (GOOD_NOTE.replace("Summary:", "Overview:"), "front matter: no Summary section"),
        (
            GOOD_NOTE.replace("Summary: Two sentences. About a thing.\n\n", "").replace(
                "- why\n\n", "- why\n\nSummary: Late.\n\n"
            ),
            "front matter: Summary is not the first section under the title",
        ),
        (
            GOOD_NOTE.replace("Motivation & Background:\n\n- why\n\n", ""),
            "missing required section 'Motivation & Background'",
        ),
        (GOOD_NOTE.replace("Eval:\n- See evals/title_eval.py\n", ""), "missing required section 'Eval'"),
        (GOOD_NOTE.replace("- why\n", ""), "section 'Motivation & Background' is empty"),
        (
            GOOD_NOTE.replace("1. https://example.org/paper", "1. a printed handout"),
            "the 'Sources' section contains no http(s) URL",
        ),
        (
            "# Title\n\nSummary: s.\n\nMotivation & Background:\n- m\n\n"
            "Eval:\n- See evals/title_eval.py\n\nSources:\n1. https://example.org/p\n",
            "sections out of order: expected Summary -> Motivation & Background -> Sources -> Eval, "
            "found Summary -> Motivation & Background -> Eval -> Sources",
        ),
        (
            GOOD_NOTE.replace("Reading list:\n- Someone (2020). https://example.org/reading.\n\n", "")
            + "\nReading list:\n- later\n",
            "'Reading list' comes after 'Eval'",
        ),
    ],
)
def test_bad_notes_are_reported(
    check_notes: ModuleType, note_format: ModuleType, text: str, expected: str
) -> None:
    found = problems(check_notes, note_format, text)
    assert any(p.startswith(expected) for p in found), found


def test_reading_list_urls_come_from_sources_and_reading_list(
    check_notes: ModuleType, note_format: ModuleType
) -> None:
    text = GOOD_NOTE.replace("Summary: Two", "Summary: See https://example.org/summary. Two")
    text = text.replace("- why", "- why https://example.org/paper")
    urls = check_notes.reading_list_urls(text + "\n", note_format)
    # Sources then Reading list, trailing full stop stripped, Summary and
    # Motivation links not counted, duplicates listed once.
    assert urls == ["https://example.org/paper", "https://example.org/reading"]


def test_real_notes_pass_the_structural_check(check_notes: ModuleType) -> None:
    assert check_notes.main(["--no-links"]) == 0


def test_main_fails_on_a_bad_note(check_notes: ModuleType, tmp_path: Path) -> None:
    (tmp_path / "good.md").write_text(GOOD_NOTE, encoding="utf-8")
    (tmp_path / "bad.md").write_text(GOOD_NOTE.replace("Summary:", "Overview:"), encoding="utf-8")
    assert check_notes.main(["--no-links", "--notes-dir", str(tmp_path)]) == 1


def test_main_returns_2_without_notes(check_notes: ModuleType, tmp_path: Path) -> None:
    assert check_notes.main(["--no-links", "--notes-dir", str(tmp_path)]) == 2


# --- link check against a loopback server --------------------------------------


class Handler(BaseHTTPRequestHandler):
    hits: dict[str, int] = {}

    def log_message(self, format: str, *args: object) -> None:  # keep test output quiet
        pass

    def _reply(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _route(self, method: str) -> None:
        count = Handler.hits.get(self.path, 0) + 1
        Handler.hits[self.path] = count
        if self.path == "/ok":
            self._reply(200)
        elif self.path == "/missing":
            self._reply(404)
        elif self.path == "/redirect":
            self.send_response(301)
            self.send_header("Location", "/ok")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif self.path == "/no-head":
            self._reply(405 if method == "HEAD" else 200)
        elif self.path == "/flaky":
            self._reply(503 if count == 1 else 200)
        elif self.path == "/down":
            self._reply(503)
        elif self.path == "/slow":
            time.sleep(2)
            self._reply(200)
        else:
            self._reply(500)

    def do_HEAD(self) -> None:
        self._route("HEAD")

    def do_GET(self) -> None:
        self._route("GET")


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch, check_notes: ModuleType) -> Iterator[str]:
    # Requests to the loopback server must not be sent through any proxy the
    # environment configures.
    for var in ("NO_PROXY", "no_proxy"):
        monkeypatch.setenv(var, "127.0.0.1,localhost")
    monkeypatch.setattr(check_notes, "RETRY_DELAY_SECONDS", 0)
    Handler.hits = {}
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


@pytest.mark.parametrize("path", ["/ok", "/redirect", "/no-head", "/flaky"])
def test_link_that_resolves(check_notes: ModuleType, server: str, path: str) -> None:
    assert check_notes.check_link(server + path, timeout=5) is None


def test_flaky_link_is_retried_once(check_notes: ModuleType, server: str) -> None:
    assert check_notes.check_link(server + "/flaky", timeout=5) is None
    assert Handler.hits["/flaky"] == 2


@pytest.mark.parametrize(
    ("path", "reason"),
    [("/missing", "HTTP 404"), ("/down", "HTTP 503")],
)
def test_link_that_does_not_resolve(
    check_notes: ModuleType, server: str, path: str, reason: str
) -> None:
    assert check_notes.check_link(server + path, timeout=5) == reason


def test_404_is_not_retried(check_notes: ModuleType, server: str) -> None:
    check_notes.check_link(server + "/missing", timeout=5)
    assert Handler.hits["/missing"] == 1


def test_slow_link_times_out(check_notes: ModuleType, server: str) -> None:
    started = time.monotonic()
    reason = check_notes.check_link(server + "/slow", timeout=0.3, retries=0)
    assert reason == "timed out after 0.3s"
    assert time.monotonic() - started < 2


def test_unreachable_host_fails(check_notes: ModuleType, server: str) -> None:
    reason = check_notes.check_link("http://127.0.0.1:9/", timeout=2, retries=0)
    assert reason is not None and reason.startswith("URLError")


def test_check_note_reports_dead_reading_list_links(
    check_notes: ModuleType, note_format: ModuleType, server: str, tmp_path: Path
) -> None:
    note = tmp_path / "linked.md"
    text = GOOD_NOTE.replace("https://example.org/paper", server + "/ok").replace(
        "https://example.org/reading", server + "/missing"
    )
    note.write_text(text, encoding="utf-8")
    found = check_notes.check_note(str(note), note_format, links=True, timeout=5)
    assert found == [f"link does not resolve: {server}/missing (HTTP 404)"]
