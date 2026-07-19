# Field Notes — first empirical model comparison (2026-07-19)

The reason FACTORY exists — "model-independence is a measurement, not a
declaration" — with its first TWO data points. Same harness (pao-lwar@0.6.1),
same 4 model-adherence probes, same isolated-probe-bus verifier; two different
vendor models, neither coached (probes and pass-criteria withheld from both).

## Match ledger

| pairing | verdict | content_exactness | honest_terminal | loop_survival_task | cancel_while_running |
|---|---|---|---|---|---|
| pao-lwar@0.6.1 × **claude-fable-5** (Claude Code) | **verified** | ✓ | ✓ | ✓ | ✓ |
| pao-lwar@0.6.1 × **kimi-k3** (Kimi Code CLI) | **verified** | ✓ | ✓ | ✓ | ✓ |

Both produced the exact intended terminal per probe: succeeded (byte-exact
artifact), failed (honest, no fabricated output), succeeded (stayed resident
through the poll window), cancelled (stopped mid-run, no forbidden artifact).

## What is proven

1. **Cross-vendor contract portability**: a Moonshot model on the Kimi Code CLI
   loaded the same natural-language PAO LWAR contract from `PAO_skills/pao-lwar`
   (no plugin), ran the stdlib runtime, self-bootstrapped the wrappers,
   registered, adopted its identity, and drove the ADP loop across slices — the
   whole skills channel is not Claude-specific.
2. **Both models fully conform** to the LWAR behavior contract under mechanical
   measurement. The match ledger now has a real second entry; the bind gate
   would open for either pairing.

## Honest limits (the useful finding)

- The current mechanical probe suite is **pass/fail and both models pass 4/4**,
  so it proves conformance but does **not yet discriminate** between the models.
  The profile axis the concept promised (cost, latency, output quality, bias) is
  NOT captured by these binary probes — that needs `production_stats` telemetry
  and/or graded probes, still `not_started`. So "which model is better for task
  X" is not yet answerable; "both models are eligible" is.
- Model identity stays operator-attested (`model_attested: true`).
- Two ledgers currently live in separate roots (integration/Kimi runs used
  temp factory roots); consolidating pairings under one FACTORY_ROOT is a
  housekeeping follow-up.
