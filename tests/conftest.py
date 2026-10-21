"""Shared pytest fixtures: load the repository's scripts by file path.

The evals are named <topic>_eval.py, with hyphens, so they cannot be imported
by name; each fixture loads one file with importlib under a private name, the
same way evals/runner_eval.py loads the runner.
"""

import importlib.util
import os
from types import ModuleType

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVALS_DIR = os.path.join(ROOT, "evals")
FIXTURES_DIR = os.path.join(ROOT, "tests", "fixtures")

# The per-note evals; each checks one note in notes/.
NOTE_EVALS = (
    "chain-of-thought_eval.py",
    "in-context-learning_eval.py",
    "reproducibility-practices_eval.py",
)


def load_by_path(path: str) -> ModuleType:
    name = "_t_" + os.path.basename(path)[: -len(".py")].replace("-", "_")
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def run_all() -> ModuleType:
    return load_by_path(os.path.join(EVALS_DIR, "run_all.py"))


@pytest.fixture
def note_format() -> ModuleType:
    return load_by_path(os.path.join(EVALS_DIR, "note-format_eval.py"))


@pytest.fixture
def check_notes() -> ModuleType:
    return load_by_path(os.path.join(ROOT, "scripts", "check_notes.py"))


@pytest.fixture(params=NOTE_EVALS)
def note_eval(request: pytest.FixtureRequest) -> ModuleType:
    return load_by_path(os.path.join(EVALS_DIR, request.param))
