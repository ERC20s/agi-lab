# Chain-of-Thought Reasoning

Summary: Chain-of-thought (CoT) refers to prompting techniques and model behaviors where intermediate reasoning steps are produced or elicited. These steps can improve reasoning performance on multi-step tasks and make model behavior more interpretable.

Motivation & Background:

- Recent work shows that asking language models to produce intermediate steps—either via few-shot prompts that include worked examples or via specific prompting formats—can substantially increase accuracy on reasoning benchmarks.
- Recording a concise note and a matching eval helps this repository exercise the CONTRIBUTING.md conventions and makes future note-standard checks automatable.

Sources:
1. https://arxiv.org/abs/2210.03629
2. https://arxiv.org/abs/2201.11903

Reading list:
- Wei, et al. (2022). "Chain of Thought Prompting Elicits Reasoning in Large Language Models." (See arXiv link above.)

Eval:
- See evals/chain-of-thought_eval.py
