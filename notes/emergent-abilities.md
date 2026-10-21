# Emergent Abilities

Summary: "Emergent abilities" are capabilities — multi-step arithmetic, instruction following, in-context task composition — that a language model appears not to have at small scale and then appears to have once scale crosses some threshold, with performance jumping sharply rather than improving smoothly. Wei et al. (2022) catalogued dozens of such jumps across model families and argued they cannot be extrapolated from smaller models. Schaeffer et al. (2023) countered that the discontinuity often lives in the metric, not the model: exact-match and other all-or-nothing scores manufacture sharp curves out of smooth underlying improvements. Whether emergence is a real phase transition or a measurement artifact is still open, and the answer changes how far ahead capabilities can be forecast.

Motivation & Background:

- Capability forecasting: if abilities genuinely appear discontinuously, evaluations on small models cannot bound what a larger model will do, and scaling-law extrapolation of downstream task performance becomes unreliable. This is the practical reason the debate matters to a notebook about paths to general intelligence.
- Safety planning: unpredictable capability jumps are the core assumption behind "evaluate before you scale" arguments. If Schaeffer et al. are right, the same jumps are visible earlier under continuous metrics (token edit distance, Brier score, log-likelihood), and pre-deployment evaluation gets easier rather than impossible.
- Measurement design: the critique is constructive. It says to report continuous metrics alongside thresholded ones, and to check whether a claimed jump survives a change of metric on the same predictions. That is a cheap, concrete standard this notebook can apply to its own evals.
- Link to existing notes: notes/in-context-learning.md already treats in-context learning as one of the abilities Wei et al. list as emergent, and notes/chain-of-thought.md covers a prompting technique whose benefit is itself reported as scale-dependent. This note is the place where the "does scale produce discontinuities?" question is argued directly rather than assumed.
- Open question worth an eval one day: no public claim of emergence in this notebook is yet re-scored under a continuous metric. That is a candidate for a future runnable eval rather than a structural one.

Sources:
1. https://arxiv.org/abs/2206.07682
2. https://arxiv.org/abs/2304.15004
3. https://arxiv.org/abs/2001.08361

Reading list:
- Wei, et al. (2022). "Emergent Abilities of Large Language Models." Surveys abilities that appear abruptly with scale across several model families; the origin of the term as used here. (See source 1.)
- Schaeffer, Miranda, Koyejo (2023). "Are Emergent Abilities of Large Language Models a Mirage?" Argues the sharp curves are produced by discontinuous metrics and shows smooth curves for the same predictions under continuous scoring. (See source 2.)
- Kaplan, et al. (2020). "Scaling Laws for Neural Language Models." The smooth loss-versus-scale baseline against which claimed downstream discontinuities are judged. (See source 3.)

Eval:
- See evals/emergent-abilities_eval.py
