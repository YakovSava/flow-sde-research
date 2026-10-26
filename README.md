# Flow-SDE Research: Curvature-Adaptive Stochasticity

> **Status: preliminary.** The sampler is implemented, unit-tested, and verified to reproduce
> `sa_solver` bit-for-bit on Anima through ComfyUI. The comparison experiments have **not been
> run yet**. This repository contains no results: every section below
> describes a hypothesis, a protocol, or a plan, and numbers quoted from earlier work are
> labelled as such. The README will be rewritten as measurements come in.

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

## Method

At each step `i` the sampler has already evaluated the model and holds the derivative
`d_i = (x_i - denoised_i) / sigma_i`. Local curvature is

```
kappa_i = rms(d_i - d_{i-1}) / |sigma_i - sigma_{i-1}|
```

which is the quantity recorded by the Trajectory Probe of the earlier work and costs **zero extra
network evaluations**. The noise power for the step from `i` to `i+1` is

```
tau_i^2 = eta_bar^2 * w_i * c_i      inside the noise window, 0 outside
w_i     = clamp((kappa_i / reference_i)^exponent, 1/spread, spread)
```

where `reference_i` is a running average of past curvature, `eta_bar` is the nominal strength, and
`c_i` is a budget-conservation factor (see below). The control is causal: it uses only information available
after the evaluation at step `i`.

### The control that matters: equal noise budget

The negative result above was a confound between *how much* and *where*. To avoid repeating it,
every adaptive run is compared against a uniform-`eta` run with the **same integrated noise
budget**, for example matched on `sum(tau_i^2 * h_i)` over the window (with `h_i` the
log-SNR step). Only a gain at equal budget supports the redistribution hypothesis.

### Variants to compare

All variants are settings of the single `Flow-SDE Sampler` node (`signal`, `exponent`,
`conserve_budget`); see [Implementation](#implementation).

| Variant | Settings |
| --- | --- |
| `sa_solver` | ComfyUI baseline; reproduced bit-for-bit at `eta = 1.0`, `exponent = 0` |
| `uniform` | `exponent = 0`, `eta` 1.6–1.8 (the tuned baseline from the earlier work) |
| `uniform-matched` | `exponent = 0`, `eta` set so that `eta^2 * sum(h)` equals the realised budget of an adaptive run. With `conserve_budget` on, this is simply `uniform` at the same `eta` |
| `curvature-online` | `signal = curvature`, `exponent > 0` (more noise on stiff steps) |
| `curvature-online, inverted` | `signal = curvature`, `exponent < 0` (more noise on smooth steps) |
| `pc-error-online` | `signal = pc_error`, for reference against the earlier negative result |
| `static-profile` | Non-uniform `tau` schedule from the mean curvature profile, fixed across samples. **Not implemented yet** |

`static-profile` isolates whether *online* adaptation matters at all, or whether a fixed
non-uniform schedule already captures the effect. The previous variance decomposition
(`analyze_dumps.py` in the earlier repository) measures how much of the signal is explained by
step index alone versus instance-specific behaviour, and decides how much headroom online
control can have.

## Implementation

```
noise_allocation.py   NoiseAllocator: per-step tau from a curvature / pc_error signal
sampler.py            sample_flow_sde: SA-Solver loop with allocator-driven tau
nodes.py              ComfyUI node "Flow-SDE Sampler"
metrics.py            geometry / texture metrics, frontier advantage, bootstrap
run_experiment.py     drives ComfyUI over its HTTP API and reports the comparison
tests/                unit tests (pytest)
```

Install by cloning into `ComfyUI/custom_nodes/` and restarting ComfyUI. No extra dependencies.
The node is found under `sampling/custom_sampling/flow_sde`.

| Parameter | Meaning |
| --- | --- |
| `eta` | Nominal stochastic strength `eta_bar` |
| `stochastic_start`, `stochastic_end` | Noise window, as in `sa_solver` (default 0.2–0.8) |
| `signal` | `curvature` (free, from consecutive derivatives) or `pc_error` (free, predictor–corrector gap) |
| `exponent` | Power applied to `signal / running_reference`. `0` disables adaptation; the sign selects stiff-heavy or smooth-heavy noise |
| `conserve_budget` | Rescales later steps so that `sum(tau_i^2 * h_i)` over the window equals `eta^2 * sum(h_i)`. The last window step absorbs the remainder |
| `spread` | Weight is clamped to `[1/spread, spread]` |
| `smoothing` | EMA factor of the running reference |
| `tau_max` | Hard cap on `tau` (clipping can leave part of the budget unspent) |

The weight acts on the noise power `tau^2`, not on `tau`, because `tau^2 * h` is what the budget
is measured in. Cost is exactly 1 NFE per step.

### Tests

```
venv/Scripts/python.exe -m pytest custom_nodes/flow-sde-research/tests
```

Run from the ComfyUI root. The suite checks that `exponent = 0` reproduces `sa_solver`
bit-for-bit at 6, 10 and 15 steps (maximum absolute difference `0`), that NFE equals the step
count for adaptive runs, that the realised budget of a conserved run equals the uniform one, and
the allocator's invariants (window, bounds, clipping, sign of the exponent). The sampler tests use
a synthetic flow model, so they establish correctness of the mechanism and say nothing about image
quality.

### Running the experiment

With ComfyUI running (and the model, LoRA, text encoder and VAE names at the top of
`run_experiment.py` adjusted to your installation):

```
venv/Scripts/python.exe custom_nodes/flow-sde-research/run_experiment.py     --prompts flat face --seeds 42 1337 --budgets 10 --variants sa_solver uniform_e17 curv_p1
```

Latents and images are written to `output/flow_sde/`; finished jobs are skipped, so an
interrupted run resumes. `--analyse-only` recomputes the report from existing files and
`--report FILE` stores per-sample metrics as JSON.

The report gives mean geometry, texture, and the texture gap to a converged 30-step reference for
every variant, plus the **texture advantage over the uniform frontier**: the difference between a
variant's texture and the texture a uniform-`eta` sampler (`uniform_e14`, `uniform_e17`,
`uniform_e20`) would have at the same geometry, linearly interpolated, with a 95 % bootstrap
confidence interval over (prompt, seed) pairs. A variant that merely moves along the `eta` curve
scores zero; a better trade-off scores above zero. A variant whose geometry falls outside the
range of the uniform runs is reported as `n/a`.

Measured cost on an RTX 5060 (8 GB) at 768×1024, cfg 5: roughly 6–7 s per step. A 100-step
geometry reference takes about 11 min and a 30-step texture reference about 4 min per
(prompt, seed), which dominates the cost of the experiment.

## Evaluation protocol

The protocol follows the earlier work so the numbers stay comparable.

- **Model:** Anima (flow-matching DiT), 768×1024, cfg 5.0, `normal` scheduler.
- **Budgets:** 6, 8, 10, 12, 15 NFE, 1 NFE per step samplers only.
- **Geometry** (lower is better): RMS deviation from a 100-step `euler` reference after 8×
  average pooling in latent space.
- **Texture:** RMS of the high-pass residual (latent minus its 8× pooled version). Reported both
  absolute and as the gap to a converged reference, here a 30-step `sa_solver` (the earlier work
  averaged six stochastic samplers, so absolute gaps are not directly comparable).
- **Prompts and seeds:** the four prompt classes of the earlier work (flat, face, fur, grid), with more
  seeds than the original 2 so that differences can be tested against seed-to-seed variance.
- **Reporting:** means with confidence intervals; a difference is claimed only when it exceeds
  the seed-to-seed spread. Negative results are reported.

## Preliminary results

Stage A: Anima, 768×1024, cfg 5.0, `normal` scheduler, **10 NFE**, 4 prompt classes × 4 seeds
(16 samples, paired). Geometry is measured against a 100-step `euler` reference, texture against
a 30-step `sa_solver`. Adaptive variants use `eta_bar = 1.7`, `exponent = ±1`, budget conserved.

| Variant | Geometry | Texture | Texture vs uniform frontier (95 % CI) |
| --- | --- | --- | --- |
| `ode` (euler) | 0.8162 | 0.2654 | n/a |
| `sa_solver` (= uniform, eta 1.0) | 0.8036 | 0.4478 | n/a |
| `uniform` eta 1.4 | 0.8699 | 0.4919 | frontier |
| `uniform` eta 1.7 | 0.9299 | 0.5318 | frontier |
| `uniform` eta 2.0 | 1.0049 | 0.5795 | frontier |
| `curv_p1` (more noise on stiff steps) | 0.9045 | 0.5149 | −0.0000 [−0.0105, +0.0126] |
| `curv_m1` (more noise on smooth steps) | 0.9360 | 0.5432 | +0.0075 [−0.0023, +0.0182] |
| `pce_p1` (`pc_error`, +1) | 0.9415 | 0.5374 | −0.0017 [−0.0120, +0.0068] |
| `pce_m1` (`pc_error`, −1) | 0.8988 | 0.5197 | +0.0086 [−0.0017, +0.0214] |

**Reading.** Every confidence interval contains zero, so at this sample size none of the adaptive
variants is distinguishable from simply moving along the uniform-`eta` curve. The point estimates
for the inverted (smooth-heavy) variants are the only ones that lean positive, and the largest,
+0.0086 texture units, is about a fifth of the texture gained by raising uniform `eta` from 1.4 to
1.7. The interval half-width is about 0.012, so an effect of this size would need roughly four
times more samples to resolve. This is a null result at n = 16, not evidence of absence.

Caveats:

- A single budget (10 NFE) and a single `eta_bar`; the 6–15 NFE sweep has not been run.
- Absolute geometry values are about 2.3× larger than those quoted in the earlier work for the
  same samplers, although the ordering (`euler` worse than `sa_solver`) is the same. The metric
  settings or reference have likely changed between the two code bases; do not compare absolute
  numbers across the two repositories.
- `ode` at 10 steps is shown for reference only and is outside the frontier range.

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

The SA-Solver loop in `sampler.py` is adapted from `sample_adaptive_sa` of
`adaptive-step-samplers`, with the error-driven controller replaced by `NoiseAllocator`.
The trajectory probe and analysis scripts are not copied; experiments are intended to use the
probe from the earlier repository, installed alongside.

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
