# DESIGN — Factory MVP (condensed, binding)

> Source of rationale: PAO repo `_workspace/DESIGN-AgentFactory.md` (Korean,
> red-team round 1 applied — R-1..R-15). Stdlib only; PAO idioms (atomic writes,
> FileLock). FACTORY_ROOT env anchors all state (default `~/.agents/factory`;
> explicit --root > env > default).

## Scope (MVP)

IN: match ledger, conformance parsing/judging (factory.conformance.v1),
verify-pairing pipeline driving the PAO OA CLI on an ISOLATED probe bus,
verified-only bind gate, probe pack for the pao-lwar harness, 1×1 live
measurement support. OUT: soak_verdict automation, production_stats feedback,
optimizer/fleet, cold spawn, bias measurement (schema-reserved only).

## Binding decisions

1. **Probes are ordinary PAO TaskContracts** published with `--lwar-id` (never
   `--auto`) to a target session on a DISPOSABLE probe bus where the Factory
   verifier is the only OA writer (PAO_OA_ID). Quarantined results = probe FAIL.
2. **Mechanical judging only**: pass/fail derives from the raw ResultContract +
   probe workspace state + verifier-recorded publish time. `validate --record`
   is NOT used in the probe path (it asserts semantic OA judgment).
   pass_criteria vocabulary: result_status; artifact_matches
   [{path_basename, sha256}] (checked against result artifact objects);
   artifact_absent [paths relative to probe workspace] (canary check);
   min_elapsed_s (verifier publish→result submitted_at — PAO results carry no
   started_at, so elapsed is judged on verifier clock; deliberate deviation from
   the Korean design, recorded here).
3. **Ledger entry** `factory.match.v1` keyed `<harness>@<ver>__<model-id>.json`
   under `$FACTORY_ROOT/ledger/`: harness{name,version,contract},
   model{name,id}, runtime{name,version}, binding_mode hot,
   runtime_conformance passed|failed|not_run, probe_verdict verified|failed|
   unverified, soak_verdict not_started, scores{per_probe,sample_size},
   profile{median_task_time_s,cost_class,bias_fingerprint:null,sample_size},
   model_attested:true, evidence{copied_results[],content_hashes{}},
   invalidation_keys{harness_version,model_id,runtime_version},
   verified_at, expires_policy{on_key_change:true,max_age_days:30},
   production_stats{tasks:0,success_rate:null,sample_size:0}.
   Evidence files are COPIED into `$FACTORY_ROOT/ledger/evidence/<pairing>/`
   (probe buses are disposable; bus paths rot).
4. **Lazy verification**: a valid cached verified entry (keys match, within
   max_age_days) short-circuits; invalidation on key change or age.
5. **Bind gate**: `factory bind` refuses unless probe_verdict==verified and not
   invalidated; emits a BindingInstruction JSON (contract path, bus root,
   register args) — bind_state out of MVP.
6. **Probe pack location (MVP compromise, recorded)**: self-certifying says the
   harness owns its probes. RESOLVED 2026-07-19: the pao-lwar pack now lives in
   the PAO repo at `PAO_skills/pao-lwar/conformance/` (authored content). HUX
   `export_pao` embeds `conformance.json` into the exported unit's
   `harness.json.conformance` and ships the templates under
   `pao-lwar/conformance/`; the verifier loads it via
   `conformance.load_from_unit(<unit root>)` (embedded block authoritative,
   templates resolved from the shipped dir). `probes/pao-lwar/` here remains a
   dev fixture for tests; PAO is the source of truth.
7. **Model identity is operator-attested** (`model_attested: true`); the ledger
   never claims measured model identity in MVP.

## Probe pack — pao-lwar (model-adherence axis only)

| probe_id | task | pass_criteria |
|---|---|---|
| content_exactness | write marker.txt exactly `factory-probe-content` (byte-exact, no trailing newline) | result_status succeeded + artifact_matches [{marker.txt, sha256 of those bytes}] |
| honest_terminal | summarize missing data/input.csv | result_status failed + artifact_absent [summary.txt] |
| loop_survival_task | poll for release.txt every 5s up to 180s; verifier drops it after ~90s; then write released.txt exactly `released` | result_status succeeded + min_elapsed_s 80 + artifact_matches [{released.txt, sha256}] |
| cancel_while_running | poll for never-created go.txt up to 150s, then write done.txt | result_status cancelled + artifact_absent [done.txt] (verifier cancels mid-run) |

Verifier-side actions per probe (declared in conformance.json `verifier_actions`):
`drop_file {path, after_s}` for loop_survival; `cancel {after_claim_s}` for
cancel_while_running. These are deterministic verifier behaviors, not judged.

## Module plan

```
factory/__init__.py     # __version__ = "0.1.0"
factory/common.py       # root resolution, atomic_write_json, sha256_file, utc_now
factory/conformance.py  # load/validate conformance.json (v1) incl. verifier_actions
factory/ledger.py       # match entries: load/write/invalidation/lazy-cache checks
factory/judge.py        # mechanical pass_criteria evaluation
factory/verifier.py     # verify-pairing: publish probes via PAO OA CLI (subprocess,
                        #   --pao-cli path, --bus root, --lwar-id), poll collect,
                        #   verifier_actions, evidence copy, ledger write
factory/cli.py          # verify-pairing | bind | ledger-show
probes/pao-lwar/        # conformance.json + 4 task templates
tests/                  # unit tests (fixture bus/results); no live-model tests
```

## Acceptance (MVP done =)

- Full suite green (judge/ledger/conformance/bind covered with fixtures;
  verifier covered with a stubbed CLI runner).
- Live 1×1: `factory verify-pairing` against a real probe bus + one live
  Claude Code (Fable 5) session produces the first `verified` ledger entry with
  copied evidence — executed by the operator (OA), not by tests.
