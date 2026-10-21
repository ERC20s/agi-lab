"""Tests for evals/run_all.py: seeds, timeout, schema validation, exit code, table."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "evals" / "run_all.py"
SCHEMA = ROOT / "evals" / "last_run.schema.json"
FIXTURES = ROOT / "tests" / "fixtures"


def write_script(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    return path


def run_cli(*args: str, runner: Path = RUNNER) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(runner), *args],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=120,
    )


def valid_payload(run_all: ModuleType, tmp_path: Path) -> dict:
    """A summary written by write_json itself, read back from disk."""
    out = tmp_path / "summary.json"
    results = [
        {
            "path": "a_eval.py",
            "returncode": 0,
            "stdout": "ok\n",
            "stderr": "",
            "passed": True,
            "timed_out": False,
            "duration_seconds": 0.25,
            "stdout_truncated": False,
            "stderr_truncated": False,
        }
    ]
    assert run_all.write_json(str(out), results, [], timeout_seconds=1.0, seed=3) is True
    return json.loads(out.read_text(encoding="utf-8"))


# --- discovery and execution -------------------------------------------------


def test_discovery_runs_only_eval_files(run_all: ModuleType, tmp_path: Path) -> None:
    write_script(tmp_path, "b_eval.py", "")
    write_script(tmp_path, "a_eval.py", "")
    write_script(tmp_path, "helper.py", "")
    write_script(tmp_path, "__init__.py", "")
    files, skipped = run_all.discover_eval_files(str(tmp_path))
    assert [os.path.basename(f) for f in files] == ["a_eval.py", "b_eval.py"]
    assert [os.path.basename(f) for f in skipped] == ["helper.py"]


def test_failing_fixture_is_reported_failed(run_all: ModuleType) -> None:
    fixture = FIXTURES / "evals_fail" / "always_fails_eval.py"
    result = run_all.run_file(str(fixture), timeout=30, root=str(fixture.parent))
    assert result["path"] == "always_fails_eval.py"
    assert result["passed"] is False
    assert result["returncode"] == 1
    assert result["timed_out"] is False
    assert "deliberate failure" in result["stderr"]
    assert run_all.result_status(result) == "FAIL"


def test_crashing_eval_is_reported_failed(run_all: ModuleType, tmp_path: Path) -> None:
    script = write_script(tmp_path, "crash_eval.py", "raise RuntimeError('boom')\n")
    result = run_all.run_file(str(script), timeout=30, root=str(tmp_path))
    assert result["passed"] is False
    assert result["returncode"] != 0
    assert "RuntimeError: boom" in result["stderr"]


def test_timeout_kills_a_slow_eval(run_all: ModuleType, tmp_path: Path) -> None:
    script = write_script(tmp_path, "slow_eval.py", "import time\ntime.sleep(30)\n")
    result = run_all.run_file(str(script), timeout=0.5, root=str(tmp_path))
    assert result["timed_out"] is True
    assert result["passed"] is False
    assert "exceeded the 0.5s timeout" in result["stderr"]
    assert result["duration_seconds"] < 10
    assert run_all.result_status(result) == "TIMEOUT"


SEED_PROBE = (
    "import os, random\n"
    "random.seed(int(os.environ['EVAL_SEED']))\n"
    "print(os.environ['PYTHONHASHSEED'], os.environ['EVAL_SEED'],"
    " hash('agi-lab'), random.random())\n"
)


def test_seed_is_exported_and_makes_runs_repeatable(run_all: ModuleType, tmp_path: Path) -> None:
    script = write_script(tmp_path, "seed_eval.py", SEED_PROBE)
    first = run_all.run_file(str(script), timeout=30, seed=7, root=str(tmp_path))
    second = run_all.run_file(str(script), timeout=30, seed=7, root=str(tmp_path))
    other = run_all.run_file(str(script), timeout=30, seed=8, root=str(tmp_path))
    assert first["passed"] and second["passed"] and other["passed"]
    assert first["stdout"].split()[:2] == ["7", "7"]
    # Same seed: same str hash and same random stream, run after run.
    assert first["stdout"] == second["stdout"]
    # A different seed changes both.
    assert other["stdout"].split()[:2] == ["8", "8"]
    assert other["stdout"].split()[2:] != first["stdout"].split()[2:]


@pytest.mark.parametrize("value", ["0", "42", str(2**32 - 1)])
def test_seed_arg_accepts_valid_seeds(run_all: ModuleType, value: str) -> None:
    assert run_all.seed_arg(value) == int(value)


@pytest.mark.parametrize("value", ["-1", str(2**32), "abc", "1.5"])
def test_seed_arg_rejects_invalid_seeds(run_all: ModuleType, value: str) -> None:
    with pytest.raises(run_all.argparse.ArgumentTypeError):
        run_all.seed_arg(value)


# --- JSON Schema ---------------------------------------------------------------


def test_written_summary_matches_schema(run_all: ModuleType, tmp_path: Path) -> None:
    payload = valid_payload(run_all, tmp_path)
    assert payload["summary"]["seed"] == 3
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert run_all.validate_schema(payload, schema) == []
    assert run_all.validate_json_file(str(tmp_path / "summary.json")) == []


def test_schema_pins_every_summary_field_the_runner_writes(
    run_all: ModuleType, tmp_path: Path
) -> None:
    payload = valid_payload(run_all, tmp_path)
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    summary_schema = schema["properties"]["summary"]
    assert sorted(summary_schema["required"]) == sorted(payload["summary"])
    assert summary_schema["properties"]["runner_version"]["const"] == run_all.RUNNER_VERSION


def _set(path: tuple, value: object):
    def mutate(payload: dict) -> None:
        target = payload
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value

    return mutate


def _delete(path: tuple):
    def mutate(payload: dict) -> None:
        target = payload
        for key in path[:-1]:
            target = target[key]
        del target[path[-1]]

    return mutate


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (_delete(("summary", "seed")), "$.summary: missing required property 'seed'"),
        (_set(("summary", "total"), "1"), "$.summary.total: expected integer, got str"),
        (_set(("summary", "total"), True), "$.summary.total: expected integer, got bool"),
        (_set(("summary", "failed"), -1), "$.summary.failed: -1 is less than the minimum 0"),
        (_set(("summary", "runner_version"), "0.3"), "$.summary.runner_version: expected '0.4'"),
        (_set(("summary", "extra"), 1), "$.summary: unexpected property 'extra'"),
        (_set(("summary", "seed"), 2**32), "$.summary.seed: 4294967296 is greater than the maximum"),
        (_delete(("results", 0, "passed")), "$.results[0]: missing required property 'passed'"),
        (_set(("results", 0, "returncode"), "0"), "$.results[0].returncode: expected integer or null"),
        (_set(("results",), {}), "$.results: expected array, got dict"),
        (_set(("skipped",), [1]), "$.skipped[0]: expected string, got int"),
    ],
)
def test_schema_rejects_malformed_summaries(
    run_all: ModuleType, tmp_path: Path, mutate, expected: str
) -> None:
    payload = valid_payload(run_all, tmp_path)
    mutate(payload)
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errors = run_all.validate_schema(payload, schema)
    assert any(e.startswith(expected) for e in errors), errors


def test_validator_refuses_keywords_it_does_not_implement(run_all: ModuleType) -> None:
    errors = run_all.validate_schema("abc", {"type": "string", "pattern": "^x"})
    assert errors == ["$: schema uses unsupported keyword(s) ['pattern']"]


@pytest.mark.parametrize(
    ("instance", "schema", "expected"),
    [
        # The items of an empty array are never visited by the instance.
        (
            [],
            {"type": "array", "items": {"type": "string", "pattern": "^x"}},
            ["$[]: schema uses unsupported keyword(s) ['pattern']"],
        ),
        # An optional property the instance leaves out, as --strip-outputs does.
        (
            {},
            {"type": "object", "properties": {"stdout": {"type": "string", "maxLength": 5}}},
            ["$.stdout: schema uses unsupported keyword(s) ['maxLength']"],
        ),
        (
            {},
            {"type": "object", "additionalProperties": {"format": "date"}},
            ["$.*: schema uses unsupported keyword(s) ['format']"],
        ),
        # A misspelt type name behind one the instance already matches.
        (None, {"type": ["null", "intger"]}, ["$: unknown JSON Schema type(s) ['intger']"]),
    ],
)
def test_validator_checks_the_whole_schema_not_just_the_visited_part(
    run_all: ModuleType, instance: object, schema: dict, expected: list[str]
) -> None:
    assert run_all.validate_schema(instance, schema) == expected


def test_the_shipped_schema_has_no_schema_errors(run_all: ModuleType) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert run_all.schema_errors(schema) == []


def test_cli_fails_on_a_bad_keyword_the_summary_never_reaches(tmp_path: Path) -> None:
    # The fixture directory has no helper files, so "skipped" is empty and
    # its items schema is never visited by the summary; the run must still
    # refuse a schema that uses a keyword the validator does not implement.
    shutil.copyfile(RUNNER, tmp_path / "run_all.py")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    schema["properties"]["skipped"]["items"]["minLength"] = 1
    (tmp_path / "last_run.schema.json").write_text(json.dumps(schema), encoding="utf-8")
    shutil.copyfile(FIXTURES / "evals_pass" / "passes_eval.py", tmp_path / "passes_eval.py")
    out = tmp_path / "out.json"
    proc = run_cli("--json-output", str(out), runner=tmp_path / "run_all.py")
    assert json.loads(out.read_text(encoding="utf-8"))["skipped"] == []
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "$.skipped[]: schema uses unsupported keyword(s) ['minLength']" in proc.stderr


def test_validate_json_file_reports_unreadable_inputs(run_all: ModuleType, tmp_path: Path) -> None:
    good = tmp_path / "good.json"
    good.write_text("{}", encoding="utf-8")
    missing_schema = run_all.validate_json_file(str(good), schema_path=str(tmp_path / "nope.json"))
    assert len(missing_schema) == 1 and "could not load the JSON Schema" in missing_schema[0]
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    unparsable = run_all.validate_json_file(str(broken))
    assert len(unparsable) == 1 and "could not read back" in unparsable[0]


# --- summary table -------------------------------------------------------------


def test_summary_table_lists_every_eval_and_counts_failures(run_all: ModuleType) -> None:
    results = [
        {"path": "a_eval.py", "returncode": 0, "passed": True, "timed_out": False, "duration_seconds": 0.1},
        {"path": "bb_eval.py", "returncode": 1, "passed": False, "timed_out": False, "duration_seconds": 0.2},
        {"path": "c_eval.py", "returncode": -9, "passed": False, "timed_out": True, "duration_seconds": 0.5},
    ]
    lines = run_all.format_summary_table(results).splitlines()
    assert lines[0].split() == ["STATUS", "EVAL", "EXIT", "TIME"]
    assert lines[2].split() == ["PASS", "a_eval.py", "0", "0.100s"]
    assert lines[3].split() == ["FAIL", "bb_eval.py", "1", "0.200s"]
    # A killed eval has no meaningful exit code.
    assert lines[4].split() == ["TIMEOUT", "c_eval.py", "-", "0.500s"]
    assert lines[5] == "3 eval(s) in 0.800s total: 1 passed, 2 failed (1 timed out)"
    # Columns line up: every eval name starts under the EVAL header.
    column = lines[0].index("EVAL")
    assert [lines[i].index(name) for i, name in ((2, "a_eval.py"), (3, "bb_eval.py"), (4, "c_eval.py"))] == [
        column
    ] * 3


# --- command line ----------------------------------------------------------------


def test_cli_reports_the_failing_fixture_and_exits_1(tmp_path: Path) -> None:
    out = tmp_path / "last_run.json"
    proc = run_cli("--evals-dir", str(FIXTURES / "evals_fail"), "--json-output", str(out))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    by_path = {r["path"]: r for r in payload["results"]}
    assert by_path["always_fails_eval.py"]["passed"] is False
    assert by_path["also_passes_eval.py"]["passed"] is True
    assert payload["summary"]["all_passed"] is False
    assert payload["summary"]["failed"] == 1
    assert payload["summary"]["seed"] == 0
    table_rows = [line.split() for line in proc.stdout.splitlines()]
    assert ["FAIL", "always_fails_eval.py", "1"] in [row[:3] for row in table_rows]
    assert "2 eval(s) in" in proc.stdout and "1 passed, 1 failed (0 timed out)" in proc.stdout
    assert f"Validated {out} against last_run.schema.json" in proc.stdout


def test_cli_exits_0_when_every_eval_passes(tmp_path: Path) -> None:
    out = tmp_path / "last_run.json"
    proc = run_cli("--evals-dir", str(FIXTURES / "evals_pass"), "--json-output", str(out), "--seed", "5")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["summary"]["all_passed"] is True
    assert payload["summary"]["seed"] == 5


def test_cli_fails_when_the_summary_does_not_match_the_schema(tmp_path: Path) -> None:
    # A copy of the runner whose schema demands a runner_version it never
    # writes: every eval passes, yet the run must exit 1.
    shutil.copyfile(RUNNER, tmp_path / "run_all.py")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    schema["properties"]["summary"]["properties"]["runner_version"]["const"] = "9.9"
    (tmp_path / "last_run.schema.json").write_text(json.dumps(schema), encoding="utf-8")
    shutil.copyfile(FIXTURES / "evals_pass" / "passes_eval.py", tmp_path / "passes_eval.py")
    out = tmp_path / "out.json"
    proc = run_cli("--json-output", str(out), runner=tmp_path / "run_all.py")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "does not match last_run.schema.json" in proc.stderr
    assert "$.summary.runner_version: expected '9.9', got '0.4'" in proc.stderr


def test_cli_fails_when_the_schema_is_missing(tmp_path: Path) -> None:
    shutil.copyfile(RUNNER, tmp_path / "run_all.py")
    shutil.copyfile(FIXTURES / "evals_pass" / "passes_eval.py", tmp_path / "passes_eval.py")
    proc = run_cli("--json-output", str(tmp_path / "out.json"), runner=tmp_path / "run_all.py")
    assert proc.returncode == 1
    assert "could not load the JSON Schema" in proc.stderr


def test_cli_fails_when_no_evals_are_found(tmp_path: Path) -> None:
    proc = run_cli("--evals-dir", str(tmp_path))
    assert proc.returncode == 1
    assert "nothing was run" in proc.stdout
