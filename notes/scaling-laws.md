Scaling laws and emergent capabilities

Thesis

Scaling model capacity, data and compute often produces predictable declines in error that approximately follow a power law across a wide range of model sizes and dataset sizes. These "scaling laws" help explain why larger systems suddenly exhibit new capabilities: some capabilities appear once error falls below a task-specific threshold. This note surveys the idea, points to primary sources, and specifies a small toy experiment that demonstrates a power-law relation between an abstract "model size" and prediction error.

Summary

Scaling laws provide a compact, empirically useful description of how average error changes with model size. They do not explain causal mechanisms by themselves, but they are a useful empirical regularity to test hypotheses and to design experiments that probe emergence thresholds.

Sources

- Hestness et al., "Deep Learning Scaling is Predictable, Empirically", 2017, https://arxiv.org/abs/1712.00409
- Kaplan et al., "Scaling Laws for Neural Language Models", 2020, https://arxiv.org/abs/2001.08361
- Henighan et al., "Scaling Laws for Autoregressive Generative Modeling", 2020, https://arxiv.org/abs/2010.14701
- Chinchilla paper (training compute-optimal model sizes), 2022, https://arxiv.org/abs/2203.15556
- Power-law and critical phenomena background: Newman, "Power laws, Pareto distributions and Zipf's law", 2005, https://arxiv.org/abs/cond-mat/0412004
- Kaplan et al. followups and notes in the literature; see overview at https://arxiv.org/abs/2210.XXXXX (placeholder for recent surveys)

Reading list

- Kaplan et al., Scaling Laws for Neural Language Models
- Hestness et al., Deep Learning Scaling is Predictable
- Chinchilla paper (compute-optimal training)
- A short tutorial on power laws: Newman, 2005

Toy experimental protocol (one paragraph)

We will run a small, deterministic toy experiment implemented by evals/001-scaling-curve.py. The script synthesizes a regression task (true targets y = sin(x) on x in [0,2pi]) and simulates model predictions whose noise standard deviation follows a power law in a scalar "model_size" parameter: noise_std = a * model_size^{-alpha}. For a range of model_size values (log-spaced), the script samples predictions, computes the mean squared error (MSE) against the true y, and fits a linear model on (log(model_size), log(MSE)) to estimate the fitted power-law exponent. The script writes results to evals/001-scaling-curve.csv and prints a one-line summary. This is a pedagogical exemplar: it uses only Python's standard library, is reproducible with a fixed RNG seed, and is intended as a template for future, more realistic evals.

Notes on limitations

This note is intentionally short and selective: it is an exemplar of the notes+evals pattern for the repository. The toy eval simplifies many real-world concerns (architectures, datasets, training regimes) and should be judged as a pedagogical illustration, not as a substantive empirical claim.
