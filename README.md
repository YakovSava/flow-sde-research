# Flow-SDE Research: Curvature-Adaptive Stochasticity

> **Status: preliminary.** The sampler is implemented, unit-tested, and verified to reproduce
> `sa_solver` bit-for-bit through ComfyUI. Three models have been measured (Anima, Flux 3 Klein,
> MOSS-Image). Curvature-driven allocation shows **no stable effect on any of them**.
> Error-driven allocation (`signal = pc_error`) shows nothing on Anima, a sign-consistent effect
> on Flux 3, and a one-sided effect on MOSS-Image (the wrong sign hurts, the right sign helps
> little). See [Preliminary results](#preliminary-results). Everything else below is a
> hypothesis, a protocol, or a plan, and numbers quoted from earlier work are labelled as such.

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
profiles.py           per-model graph, resolution, cfg, metric pooling
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

With ComfyUI running (and the model, LoRA, text encoder and VAE names in `profiles.py` adjusted to
your installation). `--model` selects the profile (`anima` by default, `flux3`, or `moss`):

```
venv/Scripts/python.exe custom_nodes/flow-sde-research/run_experiment.py     --prompts flat face --seeds 42 1337 --budgets 10 --variants sa_solver uniform_e17 curv_p1
```

Latents and images are written to `output/flow_sde/` (`output/flow_sde_flux3/` and `output/flow_sde_moss/` for the other models); finished jobs are skipped, so an
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

- **Models:** Anima (flow-matching DiT), 768×1024, cfg 5.0, `normal` scheduler; and Flux 3 Klein
  (int8 checkpoint), 768×1024, cfg 1.0, `normal` scheduler, FLUX.2 VAE (see the Flux 3 profile
  below); and MOSS-Image SFT (int8 checkpoint), 768×1024, cfg 3.0, `normal` scheduler, FLUX.2
  VAE, Qwen3.5-9B text encoder, negative prompt `worst quality, bad anatomy`. MOSS-Image uses
  the Anima protocol unchanged (100-step `euler` reference) with 4× pooling.
- **Budgets:** 6, 8, 10, 12, 15 NFE, 1 NFE per step samplers only.
- **Geometry** (lower is better): RMS deviation from a reference after average pooling in latent
  space (8× for Anima). For Anima the reference is a 100-step `euler` run.
- **Texture:** RMS of the high-pass residual (latent minus its 8× pooled version). Reported both
  absolute and as the gap to a converged reference, here a 30-step `sa_solver` (the earlier work
  averaged six stochastic samplers, so absolute gaps are not directly comparable).
- **Prompts and seeds:** the four prompt classes of the earlier work (flat, face, fur, grid), with more
  seeds than the original 2 so that differences can be tested against seed-to-seed variance.
- **Flux 3 profile.** Two deliberate departures from the Anima protocol:
  1. *Geometry reference.* The 100-step `euler` run is **not** a converged reference for this
     checkpoint: ODE results at 10 and 100 steps differ about as much as unrelated images
     (pooled RMS 0.51 for one prompt and 0.54 for another, against 0.016 between 50 and 100 steps
     on the second), because the composition changes with the step count. This is consistent
     with a step-distilled checkpoint, which is an inference from the sampling behaviour and not
     something confirmed from the model card. Geometry is therefore measured against the
     deterministic `euler` run **at the same step count and seed**, i.e. it is the deviation
     caused by the noise, not an error against a limit. Flux 3 geometry values are not comparable
     with Anima's.
  2. *Pooling.* The FLUX.2 latent has a 16× spatial downsampling instead of 8×, so pooling is 4×
     to keep the same pixel footprint.
- **Reporting:** means with confidence intervals; a difference is claimed only when it exceeds
  the seed-to-seed spread. Negative results are reported.

## Preliminary results

### Anima

Setup: Anima, 768×1024, cfg 5.0, `normal` scheduler, 4 prompt classes × 4 seeds (16 paired
samples) at each of 6, 8, 10, 12 and 15 NFE. The detailed table below is the 10 NFE budget. Geometry is measured against a 100-step `euler`
reference, texture against a 30-step `sa_solver`. Adaptive variants use `eta_bar = 1.7`, `exponent = ±1`, budget conserved.

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

**Texture advantage over the uniform frontier at every budget** (point estimate and 95 % CI;
positive means a better geometry/texture trade-off than uniform `eta`, `*` marks an interval that
excludes zero):

| Variant | 6 NFE | 8 NFE | 10 NFE | 12 NFE | 15 NFE |
| --- | --- | --- | --- | --- | --- |
| `curv_p1` | +0.0015 [−0.0008, +0.0037] | −0.0057 [−0.0139, +0.0024] | −0.0000 [−0.0105, +0.0126] | +0.0092 [−0.0136, +0.0271] | −0.0110 [−0.0341, +0.0136] |
| `curv_m1` | −0.0015 [−0.0034, −0.0001] * | +0.0003 [−0.0045, +0.0055] | +0.0075 [−0.0023, +0.0182] | −0.0013 [−0.0182, +0.0118] | −0.0031 [−0.0226, +0.0140] |
| `pce_p1` | +0.0013 [−0.0033, +0.0050] | −0.0022 [−0.0119, +0.0058] | −0.0017 [−0.0120, +0.0068] | +0.0058 [−0.0242, +0.0283] | +0.0074 [−0.0224, +0.0344] |
| `pce_m1` | +0.0084 [+0.0017, +0.0171] * | −0.0038 [−0.0117, +0.0077] | +0.0086 [−0.0017, +0.0214] | −0.0012 [−0.0150, +0.0113] | −0.0162 [−0.0407, +0.0062] |

**Reading.** There is no robust effect. Of 20 comparisons (4 variants × 5 budgets), 18 intervals
contain zero. The two that do not are at 6 NFE and have opposite signs (`pce_m1` positive,
`curv_m1` marginally negative, upper bound −0.0001); with 20 uncorrected tests about one such
excursion is expected by chance. Signs are not consistent across budgets for any variant, and the
interval half-width grows from about 0.002–0.008 at 6 NFE to about 0.02–0.03 at 15 NFE.

The curvature hypothesis, in the form tested here, is **not supported**: redistributing a fixed
noise budget by local curvature, in either direction, did not improve the geometry/texture
trade-off over uniform `eta` at 6–15 NFE on Anima. The only candidate worth a follow-up is
`pce_m1` at the lowest budget (+0.0084, about half of the texture range spanned by uniform `eta`
1.4–2.0 at 6 NFE), because it is the one result that survives its own interval; it needs more
samples before it can be called real.

Caveats:

- One `eta_bar` (1.7), `exponent = ±1`, and the weight clamped to `[1/3, 3]`. A stronger
  perturbation, a different base `eta`, or a different reference (`smoothing`) may behave
  differently; none were tried.
- A negative result at n = 16 only excludes effects larger than the interval half-width (about
  0.002–0.03 texture units depending on the budget and variant).
- Absolute geometry values are about 2.3× larger than those quoted in the earlier work for the
  same samplers, although the ordering (`euler` worse than `sa_solver`) is the same. The metric
  settings or reference have likely changed between the two code bases; do not compare absolute
  numbers across the two repositories.
- `ode` at 10 steps is shown for reference only and is outside the frontier range.
- Geometry and texture are latent-space proxies that have not been validated against human
  judgement.
- These runs were produced with ComfyUI 0.31.1. After upgrading to 0.42.5 (needed for Flux 3),
  deterministic `euler` output is bit-identical but stochastic samplers produce different noise
  realisations for the same seed, so Anima runs from the two versions must not be mixed within one
  paired comparison. The cause was not investigated.

### Flux 3 Klein

Setup: Flux 3 Klein int8 checkpoint, 768×1024, cfg 1.0, `normal` scheduler, ComfyUI 0.42.5, 4
prompt classes × 4 seeds (16 paired samples) at each of 6, 8, 10, 12 and 15 NFE; about 0.65 s per
step. `eta_bar = 1.7`, `exponent = ±1`, budget conserved. Geometry is the deviation from the
same-budget `euler` run (see the protocol).

**Texture advantage over the uniform frontier** (point estimate and 95 % bootstrap CI; `*` marks an
interval that excludes zero):

| Variant | 6 NFE | 8 NFE | 10 NFE | 12 NFE | 15 NFE |
| --- | --- | --- | --- | --- | --- |
| `curv_p1` | −0.0017 [−0.0023, −0.0011] * | −0.0025 [−0.0040, −0.0011] * | +0.0009 [−0.0009, +0.0029] | +0.0003 [−0.0024, +0.0031] | +0.0049 [+0.0003, +0.0096] * |
| `curv_m1` | +0.0045 [+0.0034, +0.0055] * | +0.0030 [+0.0012, +0.0051] * | −0.0043 [−0.0073, −0.0013] * | −0.0034 [−0.0058, −0.0013] * | −0.0049 [−0.0101, −0.0004] * |
| `pce_p1` | −0.0016 [−0.0021, −0.0012] * | −0.0041 [−0.0053, −0.0027] * | −0.0113 [−0.0151, −0.0074] * | −0.0084 [−0.0122, −0.0044] * | −0.0100 [−0.0142, −0.0058] * |
| `pce_m1` | +0.0041 [+0.0028, +0.0053] * | +0.0042 [+0.0034, +0.0051] * | +0.0090 [+0.0058, +0.0115] * | +0.0042 [+0.0016, +0.0065] * | +0.0110 [+0.0052, +0.0167] * |

**Reading.**

- **Error-driven allocation has a consistent effect.** `pce_m1` (more noise where the free
  predictor–corrector error is low, less where it is high) is positive with an interval excluding
  zero at all five budgets, and its mirror image `pce_p1` is negative at all five. A dose–response
  of this kind is hard to explain by chance. The size is modest: at 15 NFE `pce_m1` gains 0.0110
  texture units, about 90 % of the texture that uniform `eta` buys going from 1.4 to 2.0
  (0.7145 → 0.7268); at 10 NFE it is about half of that range. Relative to the texture value itself
  (about 0.7) it is 1–2 %.
- **Curvature is not a stable control.** `curv_m1` is positive at 6 and 8 NFE and negative at 10,
  12 and 15; `curv_p1` has the opposite pattern. The sign of the effect depends on the budget, so
  no single direction of the curvature rule helps across budgets. The original curvature
  hypothesis is therefore still not supported; what carries the result on Flux 3 is the
  error signal.
- **The allocation law is not universal.** The same `pce_m1` setting is inconclusive on Anima:
  positive point estimates at 6 and 10 NFE, none reliable, and a different sign at the other
  budgets. Whatever the mechanism is, it is considerably stronger on this model than on Anima,
  which answers the transfer question with "needs recalibration per model" rather than
  "universal".

Caveats specific to this result:

- Texture is high-pass energy in latent space. It cannot tell real fine detail from residual
  noise, and noise placed late in the trajectory raises it too. A spot check of 15 NFE crops for
  two prompts and one seed showed no obvious grain for `pce_m1` against uniform `eta`, but a
  spot check is not a test. The human forced-choice study listed under the secondary objective is
  now the most informative next experiment.
- The geometry axis changed meaning (deviation from the same-budget deterministic run), and the
  checkpoint is probably step-distilled, so the frontier is built from a model whose response to
  `eta` is much flatter than Anima's (texture 0.7097 → 0.7274 over `eta` 1.4 → 2.0 at 10 NFE).
  Small absolute differences carry more weight on a flat frontier.
- 20 comparisons were made without correction for multiple testing. The sign-consistent `pce`
  pattern does not depend on it, but the isolated significant `curv` intervals might.
- One `eta_bar`, one `exponent` magnitude, one checkpoint.

### MOSS-Image

Setup: MOSS-Image SFT int8 checkpoint, 768×1024, cfg 3.0 with plain classifier-free guidance (no
skip-layer guidance), `normal` scheduler, ComfyUI 0.42.5, 4 prompt classes × 4 seeds (16 paired
samples) at each of 6, 8, 10, 12 and 15 NFE; about 0.9 s per step. `eta_bar = 1.7`,
`exponent = ±1`, budget conserved. Unlike Flux 3, this checkpoint is not step-distilled and the
100-step `euler` run is a usable reference (pooled RMS between 50 and 100 steps: 0.16 and 0.05 for
two prompts), so the Anima protocol is used as is. The vendor recommends at least 50 steps and at
least 1 MP; this experiment runs at 6–15 steps and 0.79 MP, outside the intended regime.

**Texture advantage over the uniform frontier** (`*` marks an interval that excludes zero):

| Variant | 6 NFE | 8 NFE | 10 NFE | 12 NFE | 15 NFE |
| --- | --- | --- | --- | --- | --- |
| `curv_p1` | −0.0017 [−0.0028, −0.0007] * | −0.0021 [−0.0048, +0.0007] | −0.0036 [−0.0080, −0.0003] * | +0.0011 [−0.0025, +0.0040] | −0.0022 [−0.0091, +0.0041] |
| `curv_m1` | +0.0029 [+0.0015, +0.0042] * | +0.0015 [−0.0009, +0.0034] | −0.0029 [−0.0086, +0.0021] | −0.0045 [−0.0095, +0.0020] | −0.0029 [−0.0067, +0.0013] |
| `pce_p1` | +0.0003 [−0.0004, +0.0010] | −0.0020 [−0.0039, −0.0002] * | −0.0120 [−0.0185, −0.0063] * | −0.0106 [−0.0156, −0.0059] * | −0.0141 [−0.0211, −0.0069] * |
| `pce_m1` | +0.0004 [−0.0005, +0.0010] | +0.0033 [+0.0011, +0.0055] * | +0.0031 [−0.0004, +0.0068] | +0.0012 [−0.0035, +0.0061] | +0.0040 [−0.0015, +0.0091] |

**Reading.**

- **The error signal matters in one direction.** Concentrating noise on steps with *high*
  predictor–corrector error (`pce_p1`) costs texture at the same geometry at 8–15 NFE, by
  0.002–0.014 and with intervals excluding zero at four of five budgets. The opposite choice
  (`pce_m1`) has a positive point estimate at every budget but a significant one only at 8 NFE
  (+0.0033). The asymmetry (a penalty about three to four times larger than the gain) suggests
  that injecting noise where the solver is already inaccurate is the harmful part, and moving it
  elsewhere helps only slightly. This is a reading of three data sets, not a tested mechanism.
- **At 6 NFE the allocation has little to redistribute.** `pce_p1` and `pce_m1` land on top of
  uniform `eta` there (geometry 0.4862 and 0.4864 against 0.4864), as expected when the noise
  window contains only a few steps.
- **Curvature again shows no stable effect.** Two significant intervals at 6 NFE with opposite
  signs for the two directions, and nothing consistent above.

### Across models

Texture advantage of the `pc_error` variants over the uniform frontier, counted over the five
budgets (6, 8, 10, 12, 15 NFE):

| Model | `pce_m1` positive / significantly positive | `pce_p1` negative / significantly negative |
| --- | --- | --- |
| Anima | 2 / 1 | 2 / 0 |
| Flux 3 Klein | 5 / 5 | 5 / 5 |
| MOSS-Image | 5 / 1 | 4 / 4 |

(Each cell is the number of budgets, out of five, with a point estimate of the stated sign /
with a 95 % interval excluding zero on that side.) The direction is the same wherever an effect is visible, the size
is strongly model-dependent, and on Anima it is not detectable at this sample size.

## Secondary objective

- **Transfer to another flow-matching model.** Done for Flux 3 Klein (see above): the effect is
  not universal. MOSS-Image (a different architecture: 5B DiT, Qwen3.5-9B text encoder, shares
  only the FLUX.2 VAE) is also done; the direction of the `pc_error` effect agrees with
  Flux 3 but the size is much smaller.
- **Metric validation against human judgement.** Not started. A forced-choice A/B study on 20–30
  image pairs to check that the custom geometry and texture metrics agree with human preference,
  since all quantitative claims rest on them. Given the Flux 3 result this is the priority: the
  question is whether the `pce_m1` texture gain is something a person prefers.

## Known limitations

- Three models, int8 checkpoints for two of them, and one `eta_bar`; the Flux 3 profile uses a
  different geometry reference from the other two.
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
