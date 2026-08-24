# In-Context Learning

Summary: In-context learning (ICL) is the phenomenon where large language models perform new tasks by conditioning on a handful of examples (or instructions) placed in the prompt, without any gradient update to the model's weights. It turns a single pretrained model into a general-purpose few-shot learner at inference time, which makes it a candidate mechanism for flexible, general problem-solving.

Motivation & Background:

- Brown et al. (2020) showed that scaling autoregressive language models to GPT-3 size produced strong few-shot task performance purely from prompt-provided examples, with no fine-tuning.
- Xie et al. (2022) offer a theoretical account of ICL as implicit Bayesian inference over latent tasks learned during pretraining, giving a testable explanation for why examples in the prompt steer behavior.
- Wei et al. (2022) document ICL as one of several "emergent abilities" that appear abruptly at sufficient model scale, tying this note to the scaling-laws line of inquiry already in this notebook.
- Understanding whether ICL reflects genuine task learning or shallow pattern matching is directly relevant to this notebook's question of which paths lead toward general intelligence.

Sources:
1. https://arxiv.org/abs/2005.14165
2. https://arxiv.org/abs/2111.02080
3. https://arxiv.org/abs/2206.07682

Reading list:
- Brown, et al. (2020). "Language Models are Few-Shot Learners." Introduces GPT-3 and establishes few-shot in-context prompting as a general capability. (See source 1.)
- Xie, et al. (2022). "An Explanation of In-Context Learning as Implicit Bayesian Inference." Formal framework treating ICL as Bayesian task inference. (See source 2.)
- Wei, et al. (2022). "Emergent Abilities of Large Language Models." Surveys abilities, including ICL, that emerge with scale. (See source 3.)

Eval:
- See evals/in-context-learning_eval.py
