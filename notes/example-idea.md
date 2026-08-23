Title: Measuring simple text-overlap as a sanity-check for reproducible retrieval evaluation

Summary:
A short, reproducible eval that measures token-overlap between a query and candidate passages serves as a sanity-check for retrieval pipelines and as a pedagogical example for new contributors.

Problem statement:
Many retrieval and evaluation workflows are complex, involving embedding models or learned rerankers. Before investing in those, a simple deterministic baseline can validate end-to-end mechanics (data loading, matching, scoring, and CI). This note proposes a tiny eval and documents its sources and rationale.

Key claims:
- Claim 1: A deterministic text-overlap metric (exact token intersection over union) is useful as a reproducible baseline.
- Claim 2: Providing a runnable example eval lowers the barrier for contributors to add more sophisticated tests.

Sources:
- https://en.wikipedia.org/wiki/Jaccard_index (definition of intersection-over-union)
- Retrieval baseline practices, e.g. common-sense baselines in IR literature and evaluation tutorials (see reading list links).

Reading list:
- "An Introduction to Information Retrieval" (Manning et al.) — foundational IR concepts and baseline metrics.
- "Designing Evaluation Frameworks for Retrieval" (blog/tutorial) — practical tips on building reproducible evals.

Evals:
- evals/example_eval.py — a small Python script that computes token overlap (Jaccard) for two test pairs and asserts expected scores. Run: python3 evals/example_eval.py

Notes:
This file follows the project template and cites a definitional source (Jaccard). The accompanying eval is intentionally tiny and uses only the Python standard library so it can be executed in CI without extra dependencies.
