import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from factory import common, conformance


def valid_manifest():
    return {
        "schema_version": "factory.conformance.v1",
        "harness": {"name": "pao-lwar", "version": "2.1", "contract": "lwar-runtime.v2-adp"},
        "probes": [
            {
                "probe_id": "content_exactness",
                "task_template": "content_exactness.task.json",
                "pass_criteria": {
                    "result_status": "succeeded",
                    "artifact_matches": [{"path_basename": "marker.txt", "sha256": "a" * 64}],
                },
                "verifier_actions": [],
            },
            {
                "probe_id": "loop_survival_task",
                "task_template": "loop_survival.task.json",
                "pass_criteria": {"result_status": "succeeded", "min_elapsed_s": 80},
                "verifier_actions": [{"type": "drop_file", "path": "release.txt", "after_s": 90}],
            },
            {
                "probe_id": "cancel_while_running",
                "task_template": "cancel.task.json",
                "pass_criteria": {"result_status": "cancelled", "artifact_absent": ["done.txt"]},
                "verifier_actions": [{"type": "cancel", "after_claim_s": 10}],
            },
        ],
    }


class ConformanceValidTests(unittest.TestCase):
    def test_valid_manifest_passes(self):
        manifest = valid_manifest()
        self.assertIs(conformance.validate(manifest), manifest)

    def test_load_from_disk_and_template_path(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "conformance.json"
            common.atomic_write_json(path, valid_manifest())
            manifest = conformance.load(path)
            template = conformance.template_path(path, manifest["probes"][0])
            self.assertEqual(template, (path.parent / "content_exactness.task.json").resolve())


class ConformanceInvalidTests(unittest.TestCase):
    def _assert_rejects(self, mutate):
        manifest = valid_manifest()
        mutate(manifest)
        with self.assertRaises(conformance.ConformanceError):
            conformance.validate(manifest)

    def test_bad_schema_version(self):
        self._assert_rejects(lambda m: m.__setitem__("schema_version", "wrong"))

    def test_missing_harness_field(self):
        self._assert_rejects(lambda m: m["harness"].pop("contract"))

    def test_empty_probes(self):
        self._assert_rejects(lambda m: m.__setitem__("probes", []))

    def test_duplicate_probe_id(self):
        def mutate(m):
            m["probes"][1]["probe_id"] = m["probes"][0]["probe_id"]

        self._assert_rejects(mutate)

    def test_unknown_pass_criteria(self):
        self._assert_rejects(lambda m: m["probes"][0]["pass_criteria"].__setitem__("bogus", 1))

    def test_artifact_match_needs_full_sha(self):
        self._assert_rejects(
            lambda m: m["probes"][0]["pass_criteria"]["artifact_matches"].__setitem__(
                0, {"path_basename": "x", "sha256": "short"}
            )
        )

    def test_min_elapsed_must_be_positive(self):
        self._assert_rejects(lambda m: m["probes"][1]["pass_criteria"].__setitem__("min_elapsed_s", 0))

    def test_unknown_action_type(self):
        self._assert_rejects(lambda m: m["probes"][2]["verifier_actions"].__setitem__(0, {"type": "explode"}))

    def test_drop_file_action_needs_path(self):
        self._assert_rejects(
            lambda m: m["probes"][1]["verifier_actions"].__setitem__(0, {"type": "drop_file", "after_s": 1})
        )

    def test_cancel_action_needs_after_claim_s(self):
        self._assert_rejects(
            lambda m: m["probes"][2]["verifier_actions"].__setitem__(0, {"type": "cancel"})
        )


if __name__ == "__main__":
    unittest.main()
