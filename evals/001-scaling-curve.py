#!/usr/bin/env python3
"""Toy scaling-curve eval: synthesize data and simulate model error following a power law.

Produces evals/001-scaling-curve.csv with columns: model_size,mse
Prints a one-line summary and exits 0 on success.
"""
import argparse
import csv
import math
import random
import statistics


def simulate(model_size, n=1000, seed=0, a=1.0, alpha=0.5):
    """Simulate predictions for a model of given scalar "size".

    The true function is y = sin(x) on x in [0, 2*pi]. Predictions are y + noise,
    where noise ~ Normal(0, a * model_size^{-alpha}). Return MSE on n samples.
    """
    rng = random.Random(seed + int(model_size))
    mse_acc = 0.0
    for i in range(n):
        x = rng.random() * 2 * math.pi
        y = math.sin(x)
        noise_std = a * (model_size ** (-alpha))
        # Box-Muller to get normal sample from two uniforms
        u1 = rng.random()
        u2 = rng.random()
        z = math.sqrt(-2.0 * math.log(max(u1, 1e-12))) * math.cos(2 * math.pi * u2)
        pred = y + z * noise_std
        err = (pred - y) ** 2
        mse_acc += err
    return mse_acc / float(n)


def fit_power_law(sizes, mses):
    """Fit log-log linear relation; return slope (exponent on size) and intercept.

    We fit log(mse) = b + k * log(size). For a power-law mse = C * size^{k}.
    """
    logs = [(math.log(s), math.log(m)) for s, m in zip(sizes, mses)]
    xs = [p[0] for p in logs]
    ys = [p[1] for p in logs]
    n = len(xs)
    if n < 2:
        raise ValueError("need at least two points to fit")
    x_mean = statistics.mean(xs)
    y_mean = statistics.mean(ys)
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    den = sum((x - x_mean) ** 2 for x in xs)
    slope = num / den
    intercept = y_mean - slope * x_mean
    return slope, intercept


def main():
    parser = argparse.ArgumentParser(description="Run toy scaling curve eval")
    parser.add_argument("--out", default="evals/001-scaling-curve.csv",
                        help="CSV output path")
    parser.add_argument("--seed", type=int, default=0, help="RNG seed")
    parser.add_argument("--points", type=int, default=8, help="Number of sizes to sample")
    parser.add_argument("--min-size", type=float, default=10.0, help="Minimum model size")
    parser.add_argument("--max-size", type=float, default=10000.0, help="Maximum model size")
    args = parser.parse_args()

    # fixed simulation params (pedagogical)
    a = 1.0
    alpha = 0.6  # true exponent for noise ~ size^{-alpha}
    sizes = []
    mses = []
    for i in range(args.points):
        # log-spaced sizes between min and max
        frac = i / float(args.points - 1) if args.points > 1 else 0.0
        size = args.min_size * (args.max_size / args.min_size) ** frac
        sizes.append(size)
        mse = simulate(size, n=1000, seed=args.seed, a=a, alpha=alpha)
        mses.append(mse)

    slope, intercept = fit_power_law(sizes, mses)

    # write CSV
    try:
        with open(args.out, "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["model_size", "mse"])
            for s, m in zip(sizes, mses):
                writer.writerow(["{:.6g}".format(s), "{:.8g}".format(m)])
    except Exception as e:
        print("Failed to write output:", e)
        raise

    # Print one-line summary: fitted slope and last MSE
    print("scaling-curve: fitted_log_slope={:.4f}, last_mse={:.6g}".format(slope, mses[-1]))


if __name__ == "__main__":
    main()
