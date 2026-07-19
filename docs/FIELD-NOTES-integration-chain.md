# Field Notes — three-layer integration chain (2026-07-19)

First end-to-end demonstration that PAO, HUX, and FACTORY COMPOSE — not just
work in isolation. One continuous run on one bus (`D:/temp/integ/probe_bus`),
every layer using the others' real outputs.

## The chain

1. **HUX (layer 2 — unit lifecycle)**
   - `export_pao` turned the PAO repo into a harness unit (harness.json with the
     harness-owned conformance block embedded, 4 probes).
   - `hux install` → unit `pao` gen 1, static admission passed.
   - `hux verify pao` → both per-contract doctors (oa, lwar) healthy.
   - `hux enable pao --skills-path ...` → the contract dirs (with full runtime,
     scripts, schemas, conformance) became discoverable at the skills path. The
     harness is now *live*: an agent loads and runs entirely from the enabled path.

2. **FACTORY (layer 3 — verified pairing)**
   - `verify-pairing` drove the 4 model-adherence probes against a live LWAR
     session, using the conformance FROM THE HUX-ENABLED UNIT (not a Factory-side
     fixture) → `probe_verdict: verified`, evidence copied into the ledger.
   - `bind` on the verified pairing → emitted a BindingInstruction
     (contract lwar-runtime.v2-adp, hot mode); `bind` on an unverified pairing →
     refused (`no_ledger_entry`). The gate works.

3. **PAO (layer 1 — orchestration/execution)**
   - The verified + bound session received a real dev task (a stdlib TokenBucket
     rate limiter + unittest) and executed it. The OA — itself running from the
     hux-enabled `pao-oa` contract — collected the result, INDEPENDENTLY re-ran
     the unittest (rc 0, OK), verified the artifact snapshot, and recorded a
     ValidationDecision.

## Ledger

Integ bus audit balanced 5 = 5 = 5 (4 probes + 1 work task), 0 quarantines.
Match ledger: `pao-lwar@0.6.1__claude-fable-5` verified, 4 evidence files copied.

## What this proves

The concept-doc thesis holds as running code: a harness **managed as a unit**
(HUX) whose **model pairing is pre-verified** (FACTORY) is **bound and executed**
(PAO) — with the conformance and the contracts flowing across layer boundaries,
not re-authored per layer. All three layers ran from a single hux-enabled skills
path, no plugin, no pip, no PYTHONPATH.

## Honest scope

Single model (claude-fable-5) — the comparative half of FACTORY still needs a
second model. The probe target and the bound worker were the same session (the
verified pairing doing real work); a fresh session launched strictly from the
BindingInstruction's register args is the next tightening. soak_verdict remains
not_started.
