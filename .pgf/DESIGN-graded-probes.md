# DESIGN — graded-correctness axis (binding, red-team-corrected)

> Goal: let the ledger DISCRIMINATE between conforming models. First comparison
> (Fable 5 vs Kimi K3) had both pass 4/4 binary probes, so the binary axis cannot
> rank. Strictly mechanical (concept D5): no AI judgment in scoring.

## Red-team round 1 — the original "timing+footprint discriminator" was REFUTED

A 9-finding review (recorded below) showed the first draft's load-bearing
discriminators discriminate NOTHING on the real pack:

- **Timing cannot vary (D1, P0)**: elapsed is floored by verifier-controlled
  schedules — the 5s collect-poll quantizes anything faster; loop_survival waits
  a verifier drop at ~90s for EVERY model; cancel timing is verifier-fixed. Zero
  of the 4 probes have model-controlled, sub-5s-resolvable timing. Median is a
  verifier-fixed constant across models.
- **Footprint is constant / is noise (D2, P0)**: every current probe writes a
  FIXED byte string (or none), so total_artifact_bytes is identical for all
  models; and "smaller is better" is unjustified (a truncated wrong file would
  "win"). Dropped entirely.
- Plus correctness blockers: ledger whitelist silently drops new keys (D5, P1);
  median over null/failed timings crashes (D4, P1); scored artifact_absent judges
  a mutated workspace (D6, P1); div-by-zero on empty scored/graded (D7/D8);
  cross-host clock skew makes LWAR-authored elapsed invalid (D3); idle gaps
  inflate timing (D9).

**Correction: the only mechanically-sound discriminator is graded CORRECTNESS**
— a task both models attempt, scored by weighted mechanical sub-criteria on the
IMMUTABLE result. Timing is demoted to a null-safe DIAGNOSTIC (not a ranking
signal); footprint is removed.

## Scope (corrected)

1. **`scored` block (the discriminator)** — a probe may declare weighted
   sub-criteria; per-probe `score` in [0,1] = Σ(weights of passing) / Σ(weights).
   - Sub-criteria kinds are restricted to those that judge the IMMUTABLE result
     object: `result_status` and `artifact_matches` ONLY. `artifact_absent` is
     FORBIDDEN in `scored` (D6 — it judges live workspace, order-dependent).
   - Binary `pass_criteria` still governs verified/failed; `scored` only enriches
     the profile. `scores.graded[pid]` is ABSENT for probes without a block
     (D8 — so a real 0.0 differs from "not scored").
2. **Timing as diagnostic (not discriminator)** — record per-probe
   `observed_time_s` from the VERIFIER's own receive tick (the poll at which the
   result is first seen), keeping both endpoints on ONE clock (D3); value capped
   at the probe's `timeout_s` with a `capped` flag (D9); null when no result.
   Aggregated `profile.observed_median_time_s`, explicitly labeled a diagnostic
   with the caveat that it is quantized by poll_interval and floored by verifier
   actions — NOT a model-quality ranking (D1).
3. **Footprint: removed** (D2).

## Ledger shape (additive, back-compatible; make_entry MUST stop whitelisting — D5)

`scores`: keep `per_probe` (bool), `sample_size`; ADD `graded` (dict pid→score,
only for scored probes), `timing` (dict pid→{observed_time_s|null, capped}).
`profile`: `graded_mean` = mean of graded values, or null if none (D8);
`observed_median_time_s` = median of non-null observed times, or null if none
(D4); keep `cost_class`, `bias_fingerprint` (null, reserved). A round-trip test
MUST assert graded+timing survive make_entry (D5).

## Aggregation guards (D4/D7/D8)

- median over `[v for v in observed if v is not None]`; empty → null.
- graded_mean over `graded.values()`; empty → null.
- `_validate` a `scored` block: `criteria` is a non-empty list; each entry has a
  numeric `weight > 0` (reject bool/0/negative), a `kind` in
  {result_status, artifact_matches}, and a valid `spec` for that kind.

## Modules (FACTORY only)

- `conformance.py`: validate optional `scored` (restricted kinds, weights).
- `judge.py`: `judge_scored(scored, result) -> {score, checks}` reusing the
  immutable-result sub-judges; `observed_time(...)` helper is verifier-side.
- `verifier.py`: capture the receive tick per probe; compute observed_time_s
  (capped/flagged); run judge_scored when a block is present; assemble the new
  scores/profile.
- `ledger.py`: widen make_entry to carry graded/timing + graded_mean/
  observed_median_time_s (stop whitelisting).
- `probes/pao-lwar/`: add one graded probe `graded_impl` (a small module with 3
  independently-checkable required behaviors, weighted) as the discriminating
  instrument, and mirror it into PAO's harness-owned pack.
- tests: judge_scored partial/full/zero + artifact_absent-in-scored rejected;
  weight/empty validation; ledger round-trip preserves graded/timing;
  aggregation null-safety (all-failed, singleton, no-scored); AND a fixtured
  two-result-set run that yields DIFFERENT graded scores (proves separation
  power, per the review's acceptance bar).

## Acceptance

- Full suite green. The fixtured two-outcome test shows the graded axis SEPARATES
  (different scores for different result-sets) — the mechanism provably ranks.
- Honest limit recorded: this ships the MECHANISM + one instrument probe; whether
  Fable 5 and Kimi K3 actually separate on `graded_impl` is an empirical step that
  needs both live sessions (a user-gated follow-on). Timing stays a caveated
  diagnostic, never a ranking claim.
