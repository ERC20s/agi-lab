"""Repository meta-eval: ensure eval scripts import only stdlib or local modules.

Usage: python3 evals/stdlib_imports_eval.py

This meta-eval scans every *_eval.py in evals/ for top-level Import and
ImportFrom nodes. It permits:
- builtin modules (sys.builtin_module_names),
- modules whose resolved origin lies under the Python stdlib directory
  (sysconfig.get_paths()['stdlib']), and
- local repository modules (when the resolved path is inside the repo root).

Relative imports (ImportFrom with a non-zero level) are ignored so package
local imports inside the repository do not produce failures.

Ambiguous or unresolved imports are WARNed and do not cause the check to
fail. A FAIL is printed only when the import resolves to a location that is
clearly outside the stdlib directory and outside the repository root.

Returns exit code 0 when no FAILs, 1 when any FAILs were emitted, 2 on major
layout errors.
"""

import ast
import importlib.util
import os
import sys
import sysconfig
from pathlib import Path

# This eval checks the repository as a whole, not one note: it is exempt from
# the notes/<topic>.md pairing rule and says so here, where
# evals/note-coverage_eval.py reads it (declares_meta_eval).
META_EVAL = True

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EVALS_DIR = ROOT / "evals"
EVAL_SUFFIX = "_eval.py"


def read_text(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def top_level_imports(text):
    """Return sorted set of top-level import names found in module text.

    For Import nodes yield the top-level name (split at dot). For ImportFrom
    with level > 0 skip (relative import). For ImportFrom with level == 0 use
    the module name's top-level part.
    """
    tree = ast.parse(text)
    names = set()
    for node in tree.body:  # only top-level statements
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name.split(".")[0]
                if name:
                    names.add(name)
        elif isinstance(node, ast.ImportFrom):
            if getattr(node, "level", 0) > 0:
                # relative import; allow local packages
                continue
            module = node.module
            if module:
                name = module.split(".")[0]
                if name:
                    names.add(name)
    return sorted(names)


def is_path_in(path, parent):
    try:
        return Path(path).resolve().is_relative_to(Path(parent).resolve())
    except AttributeError:
        # Python <3.9 fallback
        p = Path(path).resolve()
        parentp = Path(parent).resolve()
        try:
            p.relative_to(parentp)
            return True
        except Exception:
            return False


def classify_import(name, stdlib_dir):
    """Return (status, message, resolved_path_or_None).

    status is one of: "OK" (stdlib or builtin or local), "FAIL" (third-party
    resolvable outside repo and stdlib), "WARN" (could not be resolved or
    ambiguous but not clearly failing).
    """
    # Builtins
    if name in sys.builtin_module_names:
        return "OK", "builtin", None

    try:
        spec = importlib.util.find_spec(name)
    except Exception:
        # Some import machinery can raise; treat as WARN
        return "WARN", "could not run find_spec()", None

    if spec is None:
        return "WARN", "module not found (find_spec returned None)", None

    origin = getattr(spec, "origin", None)
    search_locations = getattr(spec, "submodule_search_locations", None)

    # Builtin / frozen modules
    if origin in ("built-in", "frozen") or origin is None and not search_locations:
        # origin is None with no search locations is ambiguous; warn
        if origin in ("built-in", "frozen"):
            return "OK", origin, None
        return "WARN", "spec has no origin and no search locations", None

    # If the module is a namespace package, check search locations
    if search_locations:
        for loc in list(search_locations):
            if isinstance(loc, str) and is_path_in(loc, ROOT):
                return "OK", f"local namespace package -> {loc}", loc
            if isinstance(loc, str) and stdlib_dir and is_path_in(loc, stdlib_dir):
                return "OK", f"stdlib namespace package -> {loc}", loc
        # Not evidently in stdlib or repo
        return "FAIL", f"namespace package locations not under stdlib or repo: {list(search_locations)}", list(search_locations)

    # Otherwise origin is a file path
    if isinstance(origin, str):
        origin_path = Path(origin).resolve()
        if stdlib_dir and is_path_in(origin_path, stdlib_dir):
            return "OK", f"stdlib -> {origin}", str(origin_path)
        if is_path_in(origin_path, ROOT):
            return "OK", f"local -> {origin}", str(origin_path)
        return "FAIL", f"third-party -> {origin}", str(origin_path)

    # Fallback
    return "WARN", f"unhandled spec: origin={origin}, search_locations={search_locations}", None


def main():
    if not EVALS_DIR.is_dir():
        print("ERROR: expected directory evals/ at the repository root", file=sys.stderr)
        return 2

    stdlib_dir = None
    try:
        stdlib_dir = sysconfig.get_paths().get("stdlib")
    except Exception:
        stdlib_dir = None

    failures = 0

    for fn in sorted(os.listdir(EVALS_DIR)):
        if not fn.endswith(EVAL_SUFFIX):
            continue
        path = EVALS_DIR / fn
        try:
            text = read_text(path)
        except OSError as exc:
            print(f"FAIL: {fn} - could not read {path}: {exc}")
            failures += 1
            continue

        imports = top_level_imports(text)
        if not imports:
            print(f"OK: {fn} - no top-level imports")
            continue

        file_failed = False
        for name in imports:
            status, msg, resolved = classify_import(name, stdlib_dir)
            if status == "OK":
                print(f"OK: {fn} - import {name}: {msg}")
            elif status == "WARN":
                print(f"WARN: {fn} - import {name}: {msg}")
            elif status == "FAIL":
                print(f"FAIL: {fn} - import {name}: {msg}")
                file_failed = True

        if file_failed:
            failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
