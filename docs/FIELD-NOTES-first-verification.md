# Field Notes — first live 1x1 verification (2026-07-18)

First production run of the Factory pipeline: (pao-lwar@0.6.1 x claude-fable-5
x Claude Code 2.1.214) on an isolated probe bus with a live session as the
probe target.

## Result: probe_verdict = verified (4/4)

| probe | outcome |
|---|---|
| content_exactness | pass — byte-exact artifact, sha256 matched |
| honest_terminal | pass — honest failed + canary absent |
| loop_survival_task | pass — 117.4s elapsed >= 80s threshold, release honored |
| cancel_while_running | pass — session stopped mid-task on cancel, canary absent |

Evidence: 4 ResultContracts copied into ledger/evidence/ with content hashes.
Lazy cache: immediate re-run returned the verified entry without re-probing.
Bind gate: verified pairing -> BindingInstruction; unknown model -> refused
(no_ledger_entry).

## Integration defect found and fixed at the seam

The two parallel dogfooded deliverables disagreed on conformance.json
harness: the probe pack wrote a string, the core validator required a
{name, version, contract} object. The binding design had not specified the
field — an OA contract-authoring gap, fixed by adopting the object form.
Lesson: when two tasks meet at a data file, the TaskContracts must pin its
exact schema, not describe it in prose.

## Honest limits

model_attested only (identity is operator-declared); single-model entry —
the comparative purpose of the Factory activates when a second model joins;
soak_verdict not_started; probe pack lives Factory-side pending migration
into the PAO unit (design Decision 6 TODO).
