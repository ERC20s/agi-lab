#!/usr/bin/env python3
"""
Simple reproducible eval: compute Jaccard (token intersection over union) for pairs of texts.
Usage: python3 evals/example_eval.py
Exits with code 0 on success, non-zero on failure.
"""
import sys
import re


def tokenize(text):
    # simple whitespace+punctuation tokenizer
    return [t.lower() for t in re.findall(r"\w+", text)]


def jaccard(a, b):
    sa = set(tokenize(a))
    sb = set(tokenize(b))
    if not sa and not sb:
        return 1.0
    inter = sa & sb
    union = sa | sb
    return len(inter) / len(union)


TESTS = [
    # (text1, text2, expected_jaccard)
    ("the quick brown fox", "the quick fox", 0.75),
    ("hello world", "hello", 0.5),
]


def approx_equal(a, b, tol=1e-6):
    return abs(a - b) <= tol


def run():
    all_ok = True
    print("Running example_eval.py — Jaccard token-overlap tests")
    for i, (a, b, expected) in enumerate(TESTS, 1):
        score = jaccard(a, b)
        ok = approx_equal(score, expected)
        status = "PASS" if ok else "FAIL"
        print(f"Test {i}: {status} — score={score:.6f} expected={expected}")
        if not ok:
            all_ok = False
    if all_ok:
        print("All tests passed.")
        return 0
    else:
        print("Some tests failed.")
        return 2


if __name__ == '__main__':
    rc = run()
    sys.exit(rc)
