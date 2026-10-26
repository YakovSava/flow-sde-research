# Flow-SDE Research: Curvature-Adaptive Stochasticity

> **Status: preliminary.** This repository is at the planning stage. It contains no results
> yet: every section below describes a hypothesis, a protocol, or a plan, and numbers quoted
> from earlier work are labelled as such. The README will be rewritten as measurements come in.

Research on controlling the strength of stochasticity (`eta`) in SDE samplers for flow-matching
models at low NFE budgets (6–15 steps).

This is a follow-up to two earlier pieces of work, both published in
[adaptive-step-samplers](https://github.com/YakovSava/adaptive-step-samplers)
([DOI](https://doi.org/10.5281/zenodo.23529356)):

1. A free local error estimate from the predictor–corrector gap, used for adaptive step size.
2. Exposed SA-Solver stochastic strength, including error-driven noise control
   (`response` ≠ 0), which turned out to be a negative result.

This repository tests a different mechanism: noise distributed over steps according to local
trajectory curvature.

## Motivation

ComfyUI's `sa_solver` pins the stochastic strength to a constant `eta = 1.0` inside a fixed
20–80 % window. The previous work exposed `eta` and found that `eta = 1.6–1.8` buys texture at a
cost in macro geometry, with the exchange rate collapsing past `1.8`. Both the constant and the
window are chosen by hand and are blind to what the trajectory is actually doing.

The previous attempt at making noise adaptive drove it directly by the free predictor–corrector
error estimate (`pc_error`). On every test it matched, within noise, simply lowering `eta` by the
same average amount. That result says the *magnitude* of the noise is what mattered, and
error-proportional control added nothing on top of it.

## Hypothesis

The open question is different: **not how much noise, but where along the trajectory it is
injected.** Noise added where the velocity field is stiff (high curvature) may be amplified into
geometric error, while the same noise added where the field is smooth may be converted into
texture. If so, redistributing a fixed noise budget across steps according to local curvature
should improve the geometry/texture trade-off over a uniform `eta` at the same budget.

This is a different mechanism from `response` ≠ 0 and has not been tested. The sign of the
relation (more noise on stiff steps or on smooth ones) is not known in advance and is part of
what the experiments must determine.

## Method (planned)

At each step `i` the sampler has already evaluated the model and holds the derivative
`d_i = (x_i - denoised_i) / sigma_i`. Local curvature is

```
kappa_i = rms(d_i - d_{i-1}) / |sigma_i - sigma_{i-1}|
```

which is already computed by the Trajectory Probe of the previous work and costs **zero extra
network evaluations**. The stochastic strength for the next step is

```
tau_{i+1} = eta_bar * w(kappa_i, history) * base_window(sigma_{i+1})
```

where `w` is a normalised, bounded function of curvature relative to its running reference and
`eta_bar` is the nominal strength. The control is causal: it uses only information available
after the evaluation at step `i`.

### The control that matters: equal noise budget

The negative result above was a confound between *how much* and *where*. To avoid repeating it,
every adaptive run is compared against a uniform-`eta` run with the **same integrated noise
budget**, for example matched on `sum(tau_i^2 * h_i)` over the window (with `h_i` the
log-SNR step). Only a gain at equal budget supports the redistribution hypothesis.

### Variants to compare

| Variant | Description |
| --- | --- |
| `sa_solver` | ComfyUI baseline, `eta = 1.0`, window 0.2–0.8 |
| `uniform` | Constant `eta` in 1.6–1.8 within window 0.2–0.8 (the tuned baseline from the earlier work) |
| `uniform-matched` | Constant `eta` with budget matched to each adaptive run |
| `static-profile` | Non-uniform `tau` schedule from the mean curvature profile, fixed across samples |
| `curvature-online` | `tau` driven by live curvature (the proposed method) |
| `curvature-online, inverted` | Same with the sign of the relation flipped |
| `pc-error-online` | Direct error control (`response` ≠ 0) from the earlier work, for reference |

`static-profile` isolates whether *online* adaptation matters at all, or whether a fixed
non-uniform schedule already captures the effect. The previous variance decomposition
(`analyze_dumps.py`) measures how much of the signal is explained by step index alone versus
instance-specific behaviour, and decides how much headroom online control can have.

## Evaluation protocol

The protocol follows the earlier work so the numbers stay comparable.

- **Model:** Anima (flow-matching DiT), 768×1024, cfg 5.0, `normal` scheduler.
- **Budgets:** 6, 8, 10, 12, 15 NFE, 1 NFE per step samplers only.
- **Geometry** (lower is better): RMS deviation from a 100-step `euler` reference after 8×
  average pooling in latent space.
- **Texture:** RMS of the high-pass residual (latent minus its 8× pooled version). Reported both
  absolute and as the gap to a converged 30-step SDE reference.
- **Prompts and seeds:** the four prompt classes of the earlier work (flat, face, fur, grid), with more
  seeds than the original 2 so that differences can be tested against seed-to-seed variance.
- **Reporting:** means with confidence intervals; a difference is claimed only when it exceeds
  the seed-to-seed spread. Negative results are reported.

## Secondary objective

One of two directions will be chosen once the primary result is in:

- **Transfer to another flow-matching model** (Flux- or SD3-class, subject to access). Tests
  whether the adaptation law is universal or needs per-architecture recalibration. The weakest
  point of both earlier pieces of work is that they were measured on a single model.
- **Metric validation against human judgement.** A forced-choice A/B study on 20–30 image pairs
  to check that the custom geometry and texture metrics agree with human preference, since all
  quantitative claims of the earlier work rest on them.

## Known limitations

- Single-model evidence until the transfer study is done.
- Geometry and texture are latent-space proxies, not validated perceptual metrics.
- Raising `eta` also shifts composition, so "geometry" against a deterministic reference
  conflates structural damage with legitimate variation.

## Relationship to the previous repository

This repository is intended to build on the ComfyUI integration, trajectory probe, and analysis
scripts of `adaptive-step-samplers`. Code will be brought in as needed rather than duplicated
wholesale. The sampler is expected to remain bit-compatible with `sa_solver` when the adaptation
is switched off.

## Authors

Iakov Savelev, Yehor Yuzvynsky.

## Citation

Preliminary results are not yet available. Please cite the earlier work:

```bibtex
@software{savelev_yuzvynsky_2026_adaptivesamplers,
  author       = {Iakov Savelev and Yehor Yuzvynsky},
  title        = {Adaptive Step Samplers: Zero-Cost Truncation Error Estimation and Exposed Stochastic Control for ComfyUI},
  year         = {2026},
  publisher    = {Zenodo},
  doi          = {10.5281/zenodo.23529356},
  url          = {https://doi.org/10.5281/zenodo.23529356}
}
```
