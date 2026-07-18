# WORKPLAN — Factory MVP (dogfooded through PAO)

```
FactoryMVP // (in-progress) @v:0.1
    W1 CorePipeline // factory package: common/conformance/ledger/judge/verifier/cli + tests (delegated: task-factory-core)
    W2 ProbePack // probes/pao-lwar conformance.json + 4 templates + tests (delegated: task-factory-probes)
    W3 LiveMeasure // 1x1 live verify-pairing -> first ledger entry (owner: OA + live probe session) @dep:W1,W2
    W4 OaAcceptance // review, suite, commits (owner: OA)
```
