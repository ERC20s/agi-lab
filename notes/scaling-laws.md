# Scaling Laws

Summary: Scaling laws describe empirical power-law relationships between a language model's test loss and the compute, parameter count, and training data used to train it. Within a broad regime, loss falls predictably as any one of these resources grows, and the relationship can be used to forecast the performance of larger, not-yet-trained models and to allocate a fixed compute budget between model size and data.

Motivation & Background:

- Kaplan et al. (2020) showed that transformer language model loss follows smooth power laws in compute, parameters, and dataset size over several orders of magnitude, largely independent of model shape (depth vs. width).
- Hoffmann et al. (2022), the "Chinchilla" paper, revisited these fits with a larger set of training runs and found that most contemporary models of the time were significantly undertrained relative to their parameter count: for a fixed compute budget, model size and training tokens should be scaled roughly equally, not model size alone.
- Scaling laws matter for AGI-relevant debates because they are one of the few quantitative tools for reasoning about whether continued scaling of current architectures and training recipes is likely to keep producing capability gains, and at what cost — as opposed to purely qualitative arguments about what scale "should" do.
- Caveat: fitted power-law exponents are empirical regularities observed within a tested range and training setup; they are not physical laws, can shift with architecture, data quality, or objective changes, and should not be extrapolated far outside the range in which they were measured.

Sources:
1. https://arxiv.org/abs/2001.08361
2. https://arxiv.org/abs/2203.15556

Reading list:
- Kaplan, J. et al. (2020). "Scaling Laws for Neural Language Models." Establishes power-law fits of loss vs. compute, parameters, and dataset size. (See source 1.)
- Hoffmann, J. et al. (2022). "Training Compute-Optimal Large Language Models." Argues for compute-optimal joint scaling of model size and training tokens ("Chinchilla scaling"). (See source 2.)

Eval:
- See evals/scaling-laws_eval.py
