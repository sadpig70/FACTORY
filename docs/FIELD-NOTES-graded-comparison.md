# Field Notes — graded axis, live two-model result (2026-07-19)

Both models re-measured on the 5-probe pack (the 4 binary probes + the new
graded_impl), each a live probe target on its own isolated bus. Audit 5=5=5
on both buses, both `probe_verdict: verified`.

## Graded result

| pairing | probe_verdict | graded_impl score | graded_mean | observed_median_time_s (diagnostic) |
|---|---|---|---|---|
| pao-lwar@0.6.1 × claude-fable-5 | verified | **1.0** | **1.0** | 62.9 |
| pao-lwar@0.6.1 × kimi-k3 | verified | **1.0** | **1.0** | 26.9 |

## What this measured

- **The graded axis works end-to-end on real models.** It computed a real
  per-probe correctness score (not just pass/fail), populated graded_mean, and
  ran identically for both vendors. (Its ranking POWER was already proven by the
  stubbed two-result-set test: graded_mean 1.0 vs 0.5.)
- **graded_impl does NOT discriminate these two strong models** — both write the
  three exact files perfectly (1.0). This is the honest, predicted outcome: a
  task that only asks for byte-exact output is too easy to separate capable
  models. The instrument, not the mechanism, is the limitation.

## The timing diagnostic (explicitly NOT a ranking)

Observed medians differ (Fable 62.9s vs Kimi 26.9s), and per-probe timing shows
Kimi cycled its ADP slices faster on the fixed-work probes (content_exactness
26 vs 57, honest_terminal 21 vs 63). But this is the caveated diagnostic: it is
dominated by each runtime's watch-slice cadence and poll quantization, not model
compute quality — a fast cadence is an adherence/efficiency trait, not "better
answers". It is recorded, never used to rank.

## Next instrument (the real follow-on)

To separate strong models the pack needs a graded probe that ADMITS PARTIAL
CREDIT they actually differ on — e.g. a multi-requirement implementation task
with K independently-checkable behaviors of graded difficulty (edge cases,
error handling, a subtle correctness property), scored by fraction met. Whether
even that separates two frontier models is itself an empirical question; the
axis is now ready to answer it as such probes are authored.
