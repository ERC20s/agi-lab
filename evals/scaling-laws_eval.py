"""Validate notes/scaling-laws.md and sanity-check the scaling-law claim.

Usage: python3 evals/scaling-laws_eval.py

Checks performed:
1. Note structure (following the pattern used in evals/chain-of-thought_eval.py):
   - File exists at notes/scaling-laws.md
   - Contains an H1 title (line starting with '# ')
   - Contains a 'Summary' section
   - Contains a 'Sources' section with at least one http(s):// URL
2. A concrete, runnable demonstration of the scaling-law claim itself:
   - Generate a small synthetic loss-vs-compute series that exactly follows a
     known power law, loss = a * compute ** (-alpha), plus no noise.
   - Fit the exponent with a simple log-log least-squares regression using
     only the 'math' standard-library module (no third-party dependencies).
   - Assert the recovered exponent is within a small tolerance of the
     synthetic ground truth, i.e. that the fitting procedure correctly
     recovers a power-law relationship when one is known to be present.

This is a sanity check on the mathematical shape of the scaling-law claim
using synthetic data; it does not validate real training curves.

Returns 0 on success, non-zero on failure.
"""

import math
import os
import re
import sys

NOTE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "notes", "scaling-laws.md")


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


def has_section(text, name):
    pattern = re.compile(rf"^{re.escape(name)}\b", re.IGNORECASE | re.MULTILINE)
    return bool(pattern.search(text))


def sources_have_url(text):
    m = re.search(r"^Sources:\s*$", text, re.IGNORECASE | re.MULTILINE)
    if not m:
        return False
    after = text[m.end():]
    url_re = re.compile(r"https?://\S+")
    return bool(url_re.search(after))


def check_note(text):
    ok = True

    if not has_h1(text):
        print("FAIL: missing H1 title (line starting with '# ')")
        ok = False
    else:
        print("OK: found H1 title")

    if not has_section(text, "Summary"):
        print("FAIL: missing 'Summary' section")
        ok = False
    else:
        print("OK: found 'Summary' section")

    if not has_section(text, "Sources"):
        print("FAIL: missing 'Sources' section")
        ok = False
    else:
        print("OK: found 'Sources' section")
        if not sources_have_url(text):
            print("FAIL: 'Sources' section does not contain an http(s):// URL")
            ok = False
        else:
            print("OK: 'Sources' contains a URL")

    return ok


def log_log_least_squares(xs, ys):
    """Fit y = a * x ** (-alpha) via least squares on log(x), log(y).

    Returns (alpha, a). Uses only built-in math, no third-party libs.
    """
    lx = [math.log(x) for x in xs]
    ly = [math.log(y) for y in ys]
    n = len(lx)
    mean_x = sum(lx) / n
    mean_y = sum(ly) / n
    num = sum((lx[i] - mean_x) * (ly[i] - mean_y) for i in range(n))
    den = sum((lx[i] - mean_x) ** 2 for i in range(n))
    slope = num / den  # slope of log(y) vs log(x) == -alpha
    intercept = mean_y - slope * mean_x
    alpha = -slope
    a = math.exp(intercept)
    return alpha, a


def check_power_law_fit():
    ok = True

    # Ground truth synthetic power law: loss = a_true * compute ** (-alpha_true)
    a_true = 10.0
    alpha_true = 0.34  # roughly in the range reported for compute scaling

    computes = [10 ** k for k in range(1, 9)]  # 1e1 .. 1e8
    losses = [a_true * (c ** (-alpha_true)) for c in computes]

    alpha_fit, a_fit = log_log_least_squares(computes, losses)

    tol = 1e-6  # noiseless synthetic data, exact recovery expected up to fp error
    if abs(alpha_fit - alpha_true) > tol:
        print(f"FAIL: recovered exponent {alpha_fit:.6f} not within {tol} of ground truth {alpha_true}")
        ok = False
    else:
        print(f"OK: recovered exponent {alpha_fit:.6f} matches ground truth {alpha_true} within {tol}")

    if abs(a_fit - a_true) / a_true > 1e-3:
        print(f"FAIL: recovered coefficient {a_fit:.6f} not close to ground truth {a_true}")
        ok = False
    else:
        print(f"OK: recovered coefficient {a_fit:.6f} matches ground truth {a_true}")

    return ok


def main():
    text = read_note(NOTE_PATH)
    if text is None:
        return 2

    note_ok = check_note(text)
    fit_ok = check_power_law_fit()

    return 0 if (note_ok and fit_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
