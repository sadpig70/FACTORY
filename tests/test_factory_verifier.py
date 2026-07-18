import itertools
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from factory import common, ledger, verifier


def incrementing_clock():
    counter = itertools.count()
    return lambda: float(next(counter))


class StubRunner:
    """Simulates the PAO OA CLI over a file bus.

    Configured with per-probe outcomes:
      {"kind": "result", "result": {...}}   -> collect returns the result
      {"kind": "quarantine", "reason": str} -> collect returns a quarantined entry
    task_id is derived from the published task's cwd basename (== probe_id).
    """

    def __init__(self, tmp_dir, outcomes):
        self.tmp_dir = Path(tmp_dir)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.outcomes = outcomes
        self.calls = []
        self.sent = {}  # task_id -> probe_id

    def __call__(self, argv):
        self.calls.append(list(argv))
        verb = argv[0]
        if verb == "send":
            task_file = argv[argv.index("--task-file") + 1]
            task = json.loads(Path(task_file).read_text(encoding="utf-8"))
            probe_id = Path(task["cwd"]).name
            task_id = f"task-{probe_id}"
            self.sent[task_id] = probe_id
            return {"event": "task_published", "task_id": task_id, "lwar_id": "LWAR1"}
        if verb == "control":
            return {"event": "control_published"}
        if verb == "collect":
            results, quarantined = [], []
            for task_id, probe_id in self.sent.items():
                spec = self.outcomes[probe_id]
                if spec["kind"] == "quarantine":
                    qfile = self.tmp_dir / f"{probe_id}_quarantine.json"
                    qfile.write_text(json.dumps({"task_id": task_id}), encoding="utf-8")
                    quarantined.append(
                        {"task_id": task_id, "reason": spec.get("reason", "stale_identity_result"), "file": str(qfile)}
                    )
                else:
                    result = dict(spec["result"])
                    result["task_id"] = task_id
                    rfile = self.tmp_dir / f"{probe_id}_result.json"
                    rfile.write_text(json.dumps(result), encoding="utf-8")
                    results.append({"lwar_id": "LWAR1", "result_file": str(rfile), "result": result})
            return {"event": "results_collected", "results": results, "quarantined": quarantined}
        raise AssertionError(f"unexpected verb: {verb}")


def write_probe_pack(base: Path, probes):
    """Write a conformance manifest + minimal task templates; return manifest path."""
    manifest = {
        "schema_version": "factory.conformance.v1",
        "harness": {"name": "pao-lwar", "version": "2.1", "contract": "lwar-runtime.v2-adp"},
        "probes": probes,
    }
    for probe in probes:
        template = {
            "goal": f"probe {probe['probe_id']}",
            "instructions": "run the probe",
            "timeout_s": 60,
        }
        common.atomic_write_json(base / probe["task_template"], template)
    manifest_path = base / "conformance.json"
    common.atomic_write_json(manifest_path, manifest)
    return manifest_path


MARKER_SHA = common.sha256_bytes(b"factory-probe-content")


def run_verify(tmp, manifest_path, outcomes, runner=None):
    runner = runner or StubRunner(tmp / "bus_results", outcomes)
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    result = verifier.verify_pairing(
        manifest=manifest,
        manifest_path=manifest_path,
        model={"name": "Claude Code", "id": "claude-fable-5"},
        runtime={"name": "PAO", "version": "0.6.1"},
        lwar_id="LWAR1",
        bus_root=str(tmp / "probe_bus"),
        workspace_root=tmp / "ws",
        factory_root=tmp / "factory",
        runner=runner,
        poll_timeout_s=50,
        poll_interval_s=1,
        monotonic=incrementing_clock(),
        sleep=lambda _s: None,
    )
    return result, runner


class VerifierHappyPathTests(unittest.TestCase):
    def test_all_probes_pass_writes_verified_entry(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            probes = [
                {
                    "probe_id": "content_exactness",
                    "task_template": "content.json",
                    "pass_criteria": {
                        "result_status": "succeeded",
                        "artifact_matches": [{"path_basename": "marker.txt", "sha256": MARKER_SHA}],
                    },
                    "verifier_actions": [],
                },
                {
                    "probe_id": "honest_terminal",
                    "task_template": "honest.json",
                    "pass_criteria": {"result_status": "failed", "artifact_absent": ["summary.txt"]},
                    "verifier_actions": [],
                },
            ]
            manifest_path = write_probe_pack(tmp, probes)
            outcomes = {
                "content_exactness": {
                    "kind": "result",
                    "result": {
                        "status": "succeeded",
                        "artifacts": [
                            {"path": "C:/ws/marker.txt", "sha256": MARKER_SHA, "size_bytes": 21, "snapshot": "var/a"}
                        ],
                    },
                },
                "honest_terminal": {"kind": "result", "result": {"status": "failed", "artifacts": []}},
            }
            result, _ = run_verify(tmp, manifest_path, outcomes)

            self.assertEqual(result["probe_verdict"], "verified")
            self.assertTrue(result["probes"]["content_exactness"]["passed"])
            self.assertTrue(result["probes"]["honest_terminal"]["passed"])

            # Ledger entry written and marked verified.
            entry = ledger.load_entry(tmp / "factory", "pao-lwar@2.1__claude-fable-5")
            self.assertIsNotNone(entry)
            self.assertEqual(entry["probe_verdict"], "verified")

            # Evidence copied out of the bus with content hashes recorded.
            self.assertEqual(len(entry["evidence"]["copied_results"]), 2)
            for rel, digest in entry["evidence"]["content_hashes"].items():
                copied = ledger.evidence_dir(tmp / "factory", "pao-lwar@2.1__claude-fable-5") / rel
                self.assertTrue(copied.is_file())
                self.assertEqual(common.sha256_file(copied), digest)


class VerifierFailurePathTests(unittest.TestCase):
    def test_quarantined_result_is_probe_fail(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            probes = [
                {
                    "probe_id": "content_exactness",
                    "task_template": "content.json",
                    "pass_criteria": {"result_status": "succeeded"},
                    "verifier_actions": [],
                }
            ]
            manifest_path = write_probe_pack(tmp, probes)
            outcomes = {"content_exactness": {"kind": "quarantine", "reason": "stale_identity_result"}}
            result, _ = run_verify(tmp, manifest_path, outcomes)

            self.assertEqual(result["probe_verdict"], "failed")
            self.assertEqual(result["probes"]["content_exactness"]["outcome"], "quarantined")
            entry = ledger.load_entry(tmp / "factory", "pao-lwar@2.1__claude-fable-5")
            self.assertEqual(entry["probe_verdict"], "failed")

    def test_failing_criterion_makes_pairing_fail(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            probes = [
                {
                    "probe_id": "content_exactness",
                    "task_template": "content.json",
                    "pass_criteria": {"result_status": "succeeded"},
                    "verifier_actions": [],
                }
            ]
            manifest_path = write_probe_pack(tmp, probes)
            # LWAR reports failed where the probe demanded succeeded.
            outcomes = {"content_exactness": {"kind": "result", "result": {"status": "failed", "artifacts": []}}}
            result, _ = run_verify(tmp, manifest_path, outcomes)
            self.assertEqual(result["probe_verdict"], "failed")
            self.assertFalse(result["probes"]["content_exactness"]["passed"])


class VerifierActionTests(unittest.TestCase):
    def test_drop_file_and_cancel_actions_fire(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            probes = [
                {
                    "probe_id": "loop_survival_task",
                    "task_template": "loop.json",
                    "pass_criteria": {"result_status": "succeeded"},
                    "verifier_actions": [{"type": "drop_file", "path": "release.txt", "after_s": 0}],
                },
                {
                    "probe_id": "cancel_while_running",
                    "task_template": "cancel.json",
                    "pass_criteria": {"result_status": "cancelled", "artifact_absent": ["done.txt"]},
                    "verifier_actions": [{"type": "cancel", "after_claim_s": 0}],
                },
            ]
            manifest_path = write_probe_pack(tmp, probes)
            outcomes = {
                "loop_survival_task": {"kind": "result", "result": {"status": "succeeded", "artifacts": []}},
                "cancel_while_running": {"kind": "result", "result": {"status": "cancelled", "artifacts": []}},
            }
            result, runner = run_verify(tmp, manifest_path, outcomes)

            self.assertEqual(result["probe_verdict"], "verified")
            # drop_file created the release marker in the probe workspace.
            self.assertTrue((tmp / "ws" / "loop_survival_task" / "release.txt").is_file())
            # cancel issued an oa control cancel for the cancel probe.
            cancels = [c for c in runner.calls if c[0] == "control" and "cancel" in c]
            self.assertEqual(len(cancels), 1)
            self.assertIn("task-cancel_while_running", cancels[0])


if __name__ == "__main__":
    unittest.main()
