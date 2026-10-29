# Preprint title and abstract

## Title

**Where, Not How Much: Fixed versus Adaptive Noise Schedules for Flow-Matching SDE Samplers at Low NFE**

Short alternative: *Noise Placement in Flow-Matching SDE Samplers: A Negative Result on Curvature and a Modest Effect of Error-Based Allocation*

The working title of the repository ("Curvature-Adaptive Stochasticity") describes the hypothesis
that was **not** supported, so it is better not to use it as the paper title.

## Abstract

Stochastic samplers for flow-matching image models inject noise with a strength (`eta`) that is
usually a hand-picked constant inside a fixed window. We ask whether this strength can be set
per step from free local signals available inside a multistep predictor–corrector solver, namely
the trajectory curvature and the predictor–corrector error, at 6–15 network evaluations. We
implement a budget-conserving allocator for SA-Solver that redistributes a fixed total noise
budget over the steps, so that a gain cannot be explained by a different overall noise level, and
compare it with constant-`eta` baselines on three flow-matching models (Anima, Flux 3 Klein,
MOSS-Image) using geometry and texture measures in latent space; a fourth model (Krea 2) was
tried informally and was inconclusive. Curvature-driven allocation had no stable effect on any
model. Error-driven allocation that places more noise where the solver error is small gave a
small gain on Flux 3 Klein (about 1–2 % of the texture value), which held on fresh seeds under
criteria fixed in advance; a one-sided effect on MOSS-Image; and no detectable effect on Anima. A
fixed per-step schedule calibrated on independent runs reproduced the Flux 3 gain, so online
adaptation was not necessary: where the noise is injected along the trajectory matters, the
local state does not. In a two-alternative human study (39 respondents), people detected a large
difference in noise strength but no difference between the error-driven allocation and uniform
noise. We release the code, per-image metrics and analysis scripts, and report the negative
results in full.

## Keywords

flow matching; diffusion models; stochastic sampling; SDE sampler; SA-Solver; low NFE; noise
schedule; negative result

## Suggested categories

- arXiv: cs.LG (primary), cs.CV (cross-list). A first submission to arXiv needs an endorsement
  from an established author in the category.
- Zenodo (already used for the earlier work): create a release of the GitHub repository to get a
  DOI; this is the quickest route to a citable, searchable record.

## Points to state in the paper

- The work was carried out with an AI assistant (Claude) for code, experiment execution and
  drafting; the author is responsible for the content. Most venues and arXiv expect this to be
  disclosed.
- The survey was anonymous, collected no personal data and is not a screened panel; the raw
  responses are withheld because of free-text comments.
- The Anima runs used ComfyUI 0.31.1 and the others 0.42.5; stochastic samplers produced a
  different noise realisation for the same seed after the upgrade (cause not investigated).
- `sampler.py` is adapted from ComfyUI's SA-Solver implementation, which is GPL-3.0; see the
  licence note in the repository discussion before choosing a final licence.
