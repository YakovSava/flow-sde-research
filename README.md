# Flow-SDE Research: Curvature-Adaptive Stochasticity

English · [Русский](README_ru.md) · [中文](README_zh.md) · [Марий йылме](README_mhr.md)

This English text is the reference version. The translations follow it and may lag behind;
if they disagree, the English text is authoritative.

> **Status: work in progress.** The sampler is implemented, unit-tested, and verified to
> reproduce `sa_solver` bit-for-bit through ComfyUI. Three models have been measured (Anima,
> Flux 3 Klein, MOSS-Image). Curvature-driven allocation shows **no stable effect on any of
> them**. Error-driven allocation (`signal = pc_error`) shows nothing on Anima, a sign-consistent
> effect on Flux 3, and a one-sided effect on MOSS-Image (the wrong sign hurts, the right sign
> helps little). A human study (39 respondents) confirms that people see large differences in
> noise strength but finds **no perceptible difference** between the error-driven allocation and
> uniform noise. The static-profile control experiment is in progress. See
> [Goals, hypotheses and outcomes](#goals-hypotheses-and-outcomes) for a one-page overview and
> [Preliminary results](#preliminary-results) for the numbers. Everything else below is a
> hypothesis, a protocol, or a plan, and numbers quoted from earlier work are labelled as such.

Research on controlling the strength of stochasticity (`eta`) in SDE samplers [1] for
flow-matching models [2, 3, 6] at low NFE budgets (6–15 steps).

This is a follow-up to two earlier pieces of work, both published in
[adaptive-step-samplers](https://github.com/YakovSava/adaptive-step-samplers)
([DOI](https://doi.org/10.5281/zenodo.23529356), reference [9]):

1. A free local error estimate from the predictor–corrector gap (a Milne-type estimate [7]),
   used for adaptive step size.
2. Exposed SA-Solver stochastic strength, including error-driven noise control
   (`response` ≠ 0), which turned out to be a negative result.

This repository tests a different mechanism: noise distributed over steps according to local
trajectory curvature.

## Goals, hypotheses and outcomes

*State on 2026-10-27. The work is not finished; what is described here is what has actually been
done and measured.*

### Goals

| Goal | Outcome |
| --- | --- |
| **Primary.** Build a Flow-SDE sampler whose noise strength comes from free local signals instead of a constant, and compare it with `sa_solver` at 6–15 NFE | **Done.** The `Flow-SDE Sampler` node costs 1 NFE per step, reproduces `sa_solver` bit-for-bit when adaptation is off, and has 151 unit tests. It was compared on three models at five budgets with 16 paired samples each |
| **Does it give a better geometry/texture trade-off?** | **Depends on the model and the signal.** No for curvature. A small gain for `pc_error` on Flux 3 Klein, a one-sided effect on MOSS-Image, nothing detectable on Anima |
| **Secondary A.** Check whether the law transfers to other flow-matching models | **Done** for Flux 3 Klein and MOSS-Image. The effect is not universal |
| **Secondary B.** Check the custom metrics against human judgement | **Done (null result for the main claim).** 39 respondents. The texture metric points the same way as human judgement for a large noise difference, but humans see no difference for the error-driven allocation. See [Human study](#human-study) |

### Hypotheses

| Hypothesis | Verdict | Evidence |
| --- | --- | --- |
| **H1.** Redistributing a fixed noise budget by local curvature improves the geometry/texture trade-off | **Not supported** | 30 comparisons (2 directions × 5 budgets × 3 models). Some intervals exclude zero (1 on Anima, 8 on Flux 3, 3 on MOSS-Image) but the sign depends on the budget, so no single direction helps |
| **H2.** *(Exploratory; formed after seeing the Anima and Flux 3 data.)* Redistributing noise by the free predictor–corrector error, with the budget held equal, improves the trade-off when more noise goes where the error is low | **Partly supported** | Flux 3: `pce_m1` positive and `pce_p1` negative at all five budgets, all ten intervals exclude zero. MOSS-Image: same direction; the harmful sign is significant at 4 of 5 budgets, the helpful one at 1 of 5. Anima: not detectable. Needs confirmation on new samples and checkpoints |
| **H3.** The earlier null result for error-driven noise control (`response` ≠ 0) was a confusion of *how much* and *where* | **Not shown on Anima**, where the null reproduces at equal budget; an effect appears on other models | See H2 |
| **H4.** The allocation law is universal across flow-matching models | **Not supported** | The direction agrees where an effect is visible, but its size differs strongly between models |
| **H5.** The texture gain is real detail rather than residual noise, and a person can perceive it | **Not supported at this sample size** | Human study, 39 respondents: the positive control (`eta` 1.4 vs 2.0) is detected (the stronger noise is called AI 61 % of the time, p = 0.001), but `pce_m1` is indistinguishable from `pce_p1` (50 %) and from uniform `eta` 1.7 (51 %). Only effects larger than roughly ±13 percentage points are excluded once image variability is counted |
| **H6.** Online adaptation matters beyond a fixed non-uniform schedule (`static-profile`) | **In progress** | The variant is implemented (a per-step profile averaged over independent calibration runs, rescaled to the same budget); calibration and evaluation are running |

### Not done yet

- The `static-profile` variant.
- Other `eta_bar` values, stronger `exponent` (±2), other `spread` and `smoothing` settings.
- Confirmation of H2 on fresh seeds and prompts, other Flux 3 / MOSS-Image checkpoints
  (bf16, base), and with correction for multiple comparisons.
- The reason why stochastic samplers produce a different noise realisation for the same seed
  after the ComfyUI upgrade from 0.31.1 to 0.42.5.

## Motivation

ComfyUI's `sa_solver` [5, 12] pins the stochastic strength to a constant `eta = 1.0` inside a fixed
20–80 % window. The previous work exposed `eta` and found that `eta = 1.6–1.8` buys texture at a
cost in macro geometry, with the exchange rate collapsing past `1.8`. Both the constant and the
window are chosen by hand and are blind to what the trajectory is actually doing. Injecting
noise only inside a window of noise levels has the same form as the stochastic sampler of
Karras et al. [4].

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

This is a different mechanism from `response` ≠ 0 and had not been tested before this work
(results are below). The sign of the relation (more noise on stiff steps or on smooth ones) was
not known in advance and is part of what the experiments had to determine.

## Method

At each step `i` the sampler has already evaluated the model and holds the derivative
`d_i = (x_i - denoised_i) / sigma_i`. Local curvature is

```
kappa_i = rms(d_i - d_{i-1}) / |sigma_i - sigma_{i-1}|
```

which is the quantity recorded by the Trajectory Probe of the earlier work [9] and costs **zero extra
network evaluations**. The noise power for the step from `i` to `i+1` is

```
tau_i^2 = eta_bar^2 * w_i * c_i      inside the noise window, 0 outside
w_i     = clamp((kappa_i / reference_i)^exponent, 1/spread, spread)
```

where `reference_i` is a running average of past curvature, `eta_bar` is the nominal strength, and
`c_i` is a budget-conservation factor (see below). The control is causal: it uses only
information available after the evaluation at step `i`.

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
export_results.py     writes every per-sample metric and the summary table to results/
build_survey.py       builds the human-study image set and answer keys in survey/
results/              samples.csv (one row per image) and summary.csv (one row per model, NFE, variant)
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
venv/Scripts/python.exe custom_nodes/flow-sde-research/run_experiment.py \
    --prompts flat face --seeds 42 1337 --budgets 10 --variants sa_solver uniform_e17 curv_p1
```

Latents and images are written to `output/flow_sde/` (`output/flow_sde_flux3/` and
`output/flow_sde_moss/` for the other models); finished jobs are skipped, so an interrupted run
resumes. `--analyse-only` recomputes the report from existing files and
`--report FILE` stores per-sample metrics as JSON.

The report gives mean geometry, texture, and the texture gap to a converged 30-step reference for
every variant, plus the **texture advantage over the uniform frontier**: the difference between a
variant's texture and the texture a uniform-`eta` sampler (`uniform_e14`, `uniform_e17`,
`uniform_e20`) would have at the same geometry, linearly interpolated, with a 95 % bootstrap
confidence interval [8] over (prompt, seed) pairs. A variant that merely moves along the `eta` curve
scores zero; a better trade-off scores above zero. A variant whose geometry falls outside the
range of the uniform runs is reported as `n/a`.

### Saved metrics

`results/samples.csv` holds one row per generated image (model, ComfyUI version, variant, prompt,
seed, NFE, geometry, texture, texture gap, geometry reference type). `results/summary.csv` holds
the per-(model, NFE, variant) means and the texture advantage over the uniform frontier with its
95 % bootstrap interval. Regenerate both from the saved latents with
`venv/Scripts/python.exe custom_nodes/flow-sde-research/export_results.py`. Intervals in the
CSV can differ from the README tables in the last digit, because the bootstrap resamples pairs in
a different order; point estimates are identical. Anima rows come from ComfyUI 0.31.1 and the
others from 0.42.5 (the `comfyui_version` column), and the Flux 3 `geometry` column is relative to
the same-budget `euler` run while the other two are relative to the 100-step run.

Measured cost on an RTX 5060 (8 GB) at 768×1024: about 0.65 s per step for Flux 3 Klein and
0.9–1 s per step for Anima and MOSS-Image. The 100-step geometry reference (about 90 s) and
the 30-step texture reference (about 25 s) per (prompt, seed) are a sizeable part of the cost.
Complete runs of 16 pairs × 5 budgets × 8 variants took 70 min (Flux 3 Klein) and 150 min
(MOSS-Image); Anima was run in two stages of 57 and 101 min.

### Human study materials

`build_survey.py` assembles the images for the "which one is AI-generated" study from the Flux 3
runs at 15 NFE (prompts `face` and `fur`, four seeds). `survey/pairs/` holds 24 side-by-side
images (A | B) covering three contrasts: `texture_law` (`pce_m1` vs `pce_p1`), `eta_control`
(uniform `eta` 1.4 vs 2.0, a positive control) and `claim` (`pce_m1` vs uniform `eta` 1.7).
`survey/singles/form_1` and `form_2` hold 16 single images each, with the variant of every item
swapped between the two forms so that no respondent sees both variants of one item. Side
assignment and order are randomised with a fixed seed. Images are re-saved without metadata.
The answer keys are in `survey/key/` and must not be shown to respondents; the images themselves
are not tracked by git.

## Evaluation protocol

The protocol follows the earlier work so the numbers stay comparable.

- **Models:** Anima (flow-matching DiT), 768×1024, cfg 5.0, `normal` scheduler; and Flux 3 Klein
  [10] (int8 checkpoint), 768×1024, cfg 1.0, `normal` scheduler, FLUX.2 VAE (see the Flux 3 profile
  below); and MOSS-Image SFT [11] (int8 checkpoint), 768×1024, cfg 3.0, `normal` scheduler, FLUX.2
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
  spot check is not a test. The human study reported below found no perceptible difference between
  `pce_m1` and uniform `eta`.
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

### Human study

**Design.** Two-alternative forced choice: "which of the two images is AI-generated?". All images
are AI-generated, so the question measures which one *looks more* AI-generated. 24 side-by-side
pairs from Flux 3 Klein at 15 NFE (prompts `face` and `fur`, four seeds), eight pairs per
contrast, each variant on the left in four of the eight. Only the pair format was run; the
single-image sets built by `build_survey.py` were not used. 39 respondents answered an anonymous
multilingual online form recruited informally, without screening or attention checks.

The table gives the share of answers that called the *first* variant AI (0.5 means no
difference). "CI, respondents" resamples respondents only; "CI, respondents + images" also
resamples the eight images of the contrast, which is the honest interval for the claim that the
result holds for other images of the same kind.

| Contrast | First variant | Share calling it AI | CI, respondents | CI, respondents + images | p (t-test, respondents) |
| --- | --- | --- | --- | --- | --- |
| `eta_control` | uniform `eta` 1.4 | 0.394 | [0.34, 0.45] | [0.27, 0.52] | 0.001 |
| `texture_law` | `pce_m1` | 0.503 | [0.45, 0.55] | [0.36, 0.65] | 0.91 |
| `claim` | `pce_m1` | 0.513 | [0.45, 0.58] | [0.39, 0.64] | 0.70 |

**Reading.**

- **The positive control works.** The image generated with uniform `eta` 2.0 is called AI in 61 %
  of answers against `eta` 1.4. People notice a large difference in noise strength, so the
  instrument is sensitive. More texture is read as *more* AI-like, not as more realistic.
- **The main claim shows no difference.** `pce_m1` against `pce_p1` (`texture_law`) is 50 %, and
  `pce_m1` against uniform `eta` 1.7 (`claim`) is 51 %. Their texture difference by the latent
  metric is about 0.01, against about 0.04–0.1 for the control.
- **Interim numbers at 19 respondents pointed elsewhere** (0.526 and 0.454) and moved to 0.5
  when the sample doubled, a reminder that small-sample leanings in this design are noise.
- **What is excluded.** With respondents only, effects above about 6 percentage points would be
  visible; once the eight images per contrast are counted, only effects above about 13 points
  are excluded. Smaller effects, including the roughly 1–2 % texture gain of `pce_m1`, cannot be
  ruled in or out by this study.

Caveats: informal sample without screening; eight images per contrast; a position bias (the
second image was chosen in 63 % of answers, balanced by design); several free-text comments say
that all images look AI-generated, so the question may be near a ceiling for these scenes;
"looks AI" is not the same as "is preferred" or "has more real detail". The export of the form
contained one response column beyond the 24 pairs, which was excluded from the analysis. The raw
responses are not published because they contain free-text comments and timestamps; the
analysis script (`analyze_survey.py`) and the summary (`results/survey_summary.csv`) are in the
repository.

## Secondary objective

- **Transfer to another flow-matching model.** Done for Flux 3 Klein (see above): the effect is
  not universal. MOSS-Image (a different architecture: 5B DiT, Qwen3.5-9B text encoder, shares
  only the FLUX.2 VAE) is also done; the direction of the `pc_error` effect agrees with
  Flux 3 but the size is much smaller.
- **Metric validation against human judgement.** Done with 39 respondents; see
  [Human study](#human-study). The study asked which of two AI-generated images looks more
  AI-generated. It validates the direction of the texture metric for large differences, and
  finds no perceptible difference for the main claim. It does not show that the texture gain
  is something people prefer, because preference was not asked.

## Known limitations

- Three models, int8 checkpoints for two of them, and one `eta_bar`; the Flux 3 profile uses a
  different geometry reference from the other two.
- Geometry and texture are latent-space proxies, not validated perceptual metrics.
- Raising `eta` also shifts composition, so "geometry" against a deterministic reference
  conflates structural damage with legitimate variation.

## Relationship to the previous repository

The SA-Solver loop in `sampler.py` is adapted from `sample_adaptive_sa` of
`adaptive-step-samplers`, with the error-driven controller replaced by `NoiseAllocator`.
The trajectory probe and analysis scripts are not copied, and the experiment runner does not
depend on them: it saves the final latents with the core `SaveLatent` node.

## Authors

Iakov Savelev.

## Citation

Preliminary results are not yet available. Please cite the earlier work (its authors are listed
in the record below):

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

## References

1. Song, Y., Sohl-Dickstein, J., Kingma, D. P., Kumar, A., Ermon, S., Poole, B.
   *Score-Based Generative Modeling through Stochastic Differential Equations.* ICLR 2021.
   [arXiv:2011.13456](https://arxiv.org/abs/2011.13456)
2. Lipman, Y., Chen, R. T. Q., Ben-Hamu, H., Nickel, M., Le, M. *Flow Matching for Generative
   Modeling.* ICLR 2023. [arXiv:2210.02747](https://arxiv.org/abs/2210.02747)
3. Liu, X., Gong, C., Liu, Q. *Flow Straight and Fast: Learning to Generate and Transfer Data
   with Rectified Flow.* ICLR 2023. [arXiv:2209.03003](https://arxiv.org/abs/2209.03003)
4. Karras, T., Aittala, M., Aila, T., Laine, S. *Elucidating the Design Space of Diffusion-Based
   Generative Models.* NeurIPS 2022. [arXiv:2206.00364](https://arxiv.org/abs/2206.00364)
5. Xue, S. et al. *SA-Solver: Stochastic Adams Solver for Fast Sampling of Diffusion Models.*
   NeurIPS 2023. [arXiv:2309.05019](https://arxiv.org/abs/2309.05019)
6. Esser, P. et al. *Scaling Rectified Flow Transformers for High-Resolution Image Synthesis.*
   ICML 2024. [arXiv:2403.03206](https://arxiv.org/abs/2403.03206)
7. Hairer, E., Nørsett, S. P., Wanner, G. *Solving Ordinary Differential Equations I: Nonstiff
   Problems.* 2nd revised ed., Springer Series in Computational Mathematics 8, Springer, 1993.
8. Efron, B. Bootstrap methods: another look at the jackknife. *The Annals of Statistics* 7(1),
   1–26, 1979.
9. Savelev, I., Yuzvynsky, Y. *Adaptive Step Samplers: Zero-Cost Truncation Error Estimation and
   Exposed Stochastic Control for ComfyUI.* Zenodo, 2026.
   [doi:10.5281/zenodo.23529356](https://doi.org/10.5281/zenodo.23529356)
10. Black Forest Labs. *FLUX.3 Image Klein* (documentation and ComfyUI weights).
    <https://docs.bfl.ml/flux_3/flux3_image_klein>
11. OpenMOSS. *MOSS-Image* (code, model cards and user guide).
    <https://github.com/OpenMOSS/MOSS-Image>
12. ComfyUI. <https://github.com/comfyanonymous/ComfyUI>

References 1–8 are the literature the method and the statistics build on. References 9–12 are
the earlier work, the two checkpoints and the software used in the experiments. The Anima
checkpoint is not listed: no citable source has been added yet.
