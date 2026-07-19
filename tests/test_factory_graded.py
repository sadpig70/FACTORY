import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from factory import conformance, judge, ledger, verifier


HASH_A = "8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8"  # 'alpha'
HASH_B = "f44e64e75f3948e9f73f8dfa94721c4ce8cbb4f265c4790c702b2d41cfbf2753"  # 'beta'


def result_with(*objs, status="succeeded"):
    return {"status": status, "artifacts": list(objs)}


def art(name, sha):
    return {"path": f"D:/ws/{name}", "sha256": sha, "size_bytes": 5, "snapshot": "x"}


SCORED = {"criteria": [
    {"weight": 1, "kind": "artifact_matches", "spec": {"path_basename": "a.txt", "sha256": HASH_A}},
    {"weight": 1, "kind": "artifact_matches", "spec": {"path_basename": "b.txt", "sha256": HASH_B}},
]}


class JudgeScoredTests(unittest.TestCase):
    def test_full_score(self):
        r = judge.judge_scored(SCORED, result_with(art("a.txt", HASH_A), art("b.txt", HASH_B)))
        self.assertEqual(r["score"], 1.0)

    def test_partial_score(self):
        r = judge.judge_scored(SCORED, result_with(art("a.txt", HASH_A)))
        self.assertEqual(r["score"], 0.5)

    def test_zero_score(self):
        r = judge.judge_scored(SCORED, result_with(art("a.txt", "0" * 64)))
        self.assertEqual(r["score"], 0.0)

    def test_weighted(self):
        scored = {"criteria": [
            {"weight": 3, "kind": "artifact_matches", "spec": {"path_basename": "a.txt", "sha256": HASH_A}},
            {"weight": 1, "kind": "artifact_matches", "spec": {"path_basename": "b.txt", "sha256": HASH_B}},
        ]}
        r = judge.judge_scored(scored, result_with(art("a.txt", HASH_A)))
        self.assertEqual(r["score"], 0.75)


class ScoredValidationTests(unittest.TestCase):
    def _manifest(self, scored):
        return {
            "schema_version": "factory.conformance.v1",
            "harness": {"name": "h", "version": "1", "contract": "c"},
            "probes": [{
                "probe_id": "p", "task_template": "p.task.json",
                "pass_criteria": {"result_status": "succeeded"}, "scored": scored,
            }],
        }

    def test_artifact_absent_forbidden_in_scored(self):
        with self.assertRaises(conformance.ConformanceError):
            conformance.validate(self._manifest({"criteria": [
                {"weight": 1, "kind": "artifact_absent", "spec": {"x": 1}}]}))

    def test_empty_criteria_rejected(self):
        with self.assertRaises(conformance.ConformanceError):
            conformance.validate(self._manifest({"criteria": []}))

    def test_nonpositive_weight_rejected(self):
        for w in (0, -1, True):
            with self.assertRaises(conformance.ConformanceError):
                conformance.validate(self._manifest({"criteria": [
                    {"weight": w, "kind": "result_status", "spec": {"result_status": "succeeded"}}]}))

    def test_valid_scored_accepted(self):
        conformance.validate(self._manifest(SCORED))


class LedgerRoundTripTests(unittest.TestCase):
    def test_graded_and_timing_survive_make_entry(self):
        entry = ledger.make_entry(
            harness={"name": "pao-lwar", "version": "0.6.1", "contract": "lwar-runtime.v2-adp"},
            model={"name": "M", "id": "m"}, runtime={"name": "R", "version": "1"},
            runtime_conformance="passed", probe_verdict="verified",
            scores={"per_probe": {"graded_impl": True}, "graded": {"graded_impl": 0.5},
                    "timing": {"graded_impl": {"observed_time_s": 7.0, "capped": False}}, "sample_size": 1},
            profile={"observed_median_time_s": 7.0, "graded_mean": 0.5, "sample_size": 1},
            evidence={"copied_results": [], "content_hashes": {}},
        )
        self.assertEqual(entry["scores"]["graded"], {"graded_impl": 0.5})
        self.assertEqual(entry["scores"]["timing"]["graded_impl"]["observed_time_s"], 7.0)
        self.assertEqual(entry["profile"]["graded_mean"], 0.5)
        self.assertEqual(entry["profile"]["observed_median_time_s"], 7.0)


class SeparationTests(unittest.TestCase):
    """The graded axis provably RANKS: two result-sets on the same probe yield
    different graded_mean. Uses a stubbed runner so no live model is needed."""

    def _run(self, ok_files):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            pack = root / "pack"
            (pack).mkdir()
            manifest = {
                "schema_version": "factory.conformance.v1",
                "harness": {"name": "pao-lwar", "version": "0.6.1", "contract": "lwar-runtime.v2-adp"},
                "probes": [{
                    "probe_id": "graded_impl", "task_template": "g.task.json",
                    "pass_criteria": {"result_status": "succeeded"}, "scored": SCORED, "timeout_s": 60,
                }],
            }
            (pack / "g.task.json").write_text(json.dumps({"goal": "g", "instructions": "g",
                "completion_criteria": [], "timeout_s": 60, "permissions": {}}), encoding="utf-8")
            arts = [art(n, h) for n, h in ok_files]
            calls = {"n": 0}

            def runner(argv):
                verb = argv[0]
                if verb == "send":
                    return {"event": "task_published", "task_id": "task-g"}
                if verb == "collect":
                    return {"quarantined": [], "results": [{"result_file": None,
                            "result": {"task_id": "task-g", "status": "succeeded", "artifacts": arts,
                                       "submitted_at": "2026-01-01T00:00:00Z"}}]}
                return {}

            report = verifier.verify_pairing(
                manifest=manifest, manifest_path=str(pack / "conformance.json"),
                model={"name": "M", "id": "m"}, runtime={"name": "R", "version": "1"},
                lwar_id="LWAR1", bus_root=str(root / "bus"), workspace_root=str(root / "ws"),
                factory_root=str(root / "fr"), runner=runner, runtime_conformance="passed",
                poll_timeout_s=1, poll_interval_s=0, monotonic=lambda: 0.0, sleep=lambda s: None,
            )
            # verify_pairing returns a report with entry_path; read the entry.
            return json.loads(Path(report["entry_path"]).read_text(encoding="utf-8"))

    def test_graded_mean_separates_two_result_sets(self):
        strong = self._run([("a.txt", HASH_A), ("b.txt", HASH_B)])   # both correct
        weak = self._run([("a.txt", HASH_A)])                        # one correct
        self.assertEqual(strong["profile"]["graded_mean"], 1.0)
        self.assertEqual(weak["profile"]["graded_mean"], 0.5)
        self.assertNotEqual(strong["profile"]["graded_mean"], weak["profile"]["graded_mean"])


class AggregationSafetyTests(unittest.TestCase):
    def test_no_scored_probe_yields_null_graded_mean(self):
        entry = ledger.make_entry(
            harness={"name": "h", "version": "1", "contract": "c"},
            model={"id": "m"}, runtime={"version": "1"},
            runtime_conformance="passed", probe_verdict="verified",
            scores={"per_probe": {"p": True}, "graded": {}, "timing": {}, "sample_size": 1},
            profile={"observed_median_time_s": None, "graded_mean": None, "sample_size": 1},
            evidence={"copied_results": [], "content_hashes": {}},
        )
        self.assertIsNone(entry["profile"]["graded_mean"])
        self.assertIsNone(entry["profile"]["observed_median_time_s"])


if __name__ == "__main__":
    unittest.main()
