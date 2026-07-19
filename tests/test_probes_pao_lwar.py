"""Conformance tests for the pao-lwar probe pack.

Stdlib only. These tests deliberately do NOT import the ``factory`` package
(another node owns it); they validate the authored probe pack as data against
the DESIGN-FACTORY.md 'Probe pack — pao-lwar' table and Decision 2 vocabulary.
"""

import hashlib
import json
import unittest
from pathlib import Path

PROBES_DIR = Path(__file__).resolve().parent.parent / "probes" / "pao-lwar"
CONFORMANCE = PROBES_DIR / "conformance.json"

# Decision 2 pass_criteria vocabulary (DESIGN-FACTORY.md).
PASS_CRITERIA_KEYS = {
    "result_status",
    "artifact_matches",
    "artifact_absent",
    "min_elapsed_s",
}

# ResultContract status values (adp-contract.md Result Contract).
RESULT_STATUSES = {
    "succeeded",
    "failed",
    "blocked",
    "cancelled",
    "interrupted",
    "timed_out",
    "protocol_error",
}

# The four probe_ids and their spec, straight from the design table.
EXPECTED_PROBES = {
    "content_exactness",
    "honest_terminal",
    "loop_survival_task",
    "cancel_while_running",
    "graded_impl",
}

# Byte-exact artifact contents specified by the design table. The embedded
# sha256 digests in conformance.json must equal hashlib digests of these bytes.
EXPECTED_ARTIFACT_BYTES = {
    "marker.txt": b"factory-probe-content",
    "released.txt": b"released",
}


def load_conformance():
    with CONFORMANCE.open("r", encoding="utf-8") as fh:
        return json.load(fh)


class ConformanceShapeTests(unittest.TestCase):
    def setUp(self):
        self.conf = load_conformance()

    def test_conformance_is_strict_json(self):
        # Re-read raw and parse strictly (no trailing garbage, valid UTF-8).
        raw = CONFORMANCE.read_text(encoding="utf-8")
        json.loads(raw)  # raises on any malformed content

    def test_schema_version(self):
        self.assertEqual(self.conf["schema_version"], "factory.conformance.v1")

    def test_bootstrap_shape(self):
        boot = self.conf["bootstrap"]
        self.assertEqual(boot["steps"], ["registration"])
        self.assertEqual(boot["judged_from"], "registry_state")

    def test_probe_set_matches_design(self):
        ids = {p["probe_id"] for p in self.conf["probes"]}
        self.assertEqual(ids, EXPECTED_PROBES)

    def test_each_probe_has_required_fields(self):
        for probe in self.conf["probes"]:
            for key in ("probe_id", "task_template", "pass_criteria", "timeout_s"):
                self.assertIn(key, probe, f"{probe.get('probe_id')} missing {key}")
            self.assertIsInstance(probe["timeout_s"], int)
            self.assertGreater(probe["timeout_s"], 0)

    def test_authoring_rules_present(self):
        rule_ids = {r["id"] for r in self.conf["authoring_rules"]}
        self.assertEqual(
            rule_ids,
            {
                "mechanical-only",
                "artifact_absent-for-negatives",
                "satisfiable-in-authority-bounds",
                "no-external-state",
                "model-judgment-probes-only",
            },
        )

    def test_soak_extension_note_present(self):
        self.assertIn("note", self.conf["soak_extension"])


class PassCriteriaVocabularyTests(unittest.TestCase):
    def setUp(self):
        self.conf = load_conformance()

    def test_pass_criteria_use_only_decision2_vocabulary(self):
        for probe in self.conf["probes"]:
            extra = set(probe["pass_criteria"]) - PASS_CRITERIA_KEYS
            self.assertEqual(
                extra, set(), f"{probe['probe_id']} has non-vocabulary keys: {extra}"
            )

    def test_result_status_values_valid(self):
        for probe in self.conf["probes"]:
            status = probe["pass_criteria"]["result_status"]
            self.assertIn(status, RESULT_STATUSES)

    def test_artifact_matches_shape(self):
        for probe in self.conf["probes"]:
            for match in probe["pass_criteria"].get("artifact_matches", []):
                self.assertEqual(set(match), {"path_basename", "sha256"})
                self.assertRegex(match["sha256"], r"^[0-9a-f]{64}$")

    def test_expected_statuses_per_design(self):
        by_id = {p["probe_id"]: p["pass_criteria"] for p in self.conf["probes"]}
        self.assertEqual(by_id["content_exactness"]["result_status"], "succeeded")
        self.assertEqual(by_id["honest_terminal"]["result_status"], "failed")
        self.assertEqual(by_id["loop_survival_task"]["result_status"], "succeeded")
        self.assertEqual(by_id["cancel_while_running"]["result_status"], "cancelled")
        self.assertEqual(by_id["loop_survival_task"]["min_elapsed_s"], 80)


class Sha256RecomputationTests(unittest.TestCase):
    def setUp(self):
        self.conf = load_conformance()

    def test_embedded_digests_match_recomputed(self):
        seen = set()
        for probe in self.conf["probes"]:
            for match in probe["pass_criteria"].get("artifact_matches", []):
                basename = match["path_basename"]
                self.assertIn(
                    basename,
                    EXPECTED_ARTIFACT_BYTES,
                    f"unexpected artifact basename {basename}",
                )
                expected = hashlib.sha256(EXPECTED_ARTIFACT_BYTES[basename]).hexdigest()
                self.assertEqual(
                    match["sha256"],
                    expected,
                    f"{probe['probe_id']}: {basename} digest mismatch",
                )
                seen.add(basename)
        # Both byte-exact artifacts from the design table are actually covered.
        self.assertEqual(seen, set(EXPECTED_ARTIFACT_BYTES))


class ArtifactAbsentCanaryTests(unittest.TestCase):
    def setUp(self):
        self.conf = load_conformance()

    def test_negative_probes_declare_canary_paths(self):
        # Every probe whose expected status is not 'succeeded' must assert a
        # non-empty artifact_absent canary list (artifact_absent-for-negatives).
        for probe in self.conf["probes"]:
            pc = probe["pass_criteria"]
            if pc["result_status"] != "succeeded":
                absent = pc.get("artifact_absent", [])
                self.assertTrue(
                    isinstance(absent, list) and len(absent) > 0,
                    f"{probe['probe_id']} negative probe lacks artifact_absent canary",
                )
                self.assertTrue(all(isinstance(p, str) and p for p in absent))


class VerifierActionsTests(unittest.TestCase):
    def setUp(self):
        self.conf = load_conformance()
        self.by_id = {p["probe_id"]: p for p in self.conf["probes"]}

    def test_loop_survival_drops_release_file(self):
        actions = self.by_id["loop_survival_task"]["verifier_actions"]
        self.assertEqual(len(actions), 1)
        drop = actions[0]
        self.assertEqual(drop["type"], "drop_file")
        self.assertIn("path", drop)
        self.assertIsInstance(drop["after_s"], int)

    def test_cancel_probe_cancels_after_claim(self):
        actions = self.by_id["cancel_while_running"]["verifier_actions"]
        self.assertEqual(len(actions), 1)
        cancel = actions[0]
        self.assertEqual(cancel["type"], "cancel")
        self.assertIsInstance(cancel["after_claim_s"], int)

    def test_only_declared_probes_have_verifier_actions(self):
        for pid, probe in self.by_id.items():
            has = "verifier_actions" in probe
            if pid in {"loop_survival_task", "cancel_while_running"}:
                self.assertTrue(has, f"{pid} should declare verifier_actions")
            else:
                self.assertFalse(has, f"{pid} should not declare verifier_actions")


class TaskTemplateTests(unittest.TestCase):
    def setUp(self):
        self.conf = load_conformance()

    def test_every_referenced_template_exists_and_parses(self):
        for probe in self.conf["probes"]:
            path = PROBES_DIR / probe["task_template"]
            self.assertTrue(path.is_file(), f"missing template {path}")
            with path.open("r", encoding="utf-8") as fh:
                draft = json.load(fh)
            self.assertTrue(draft.get("goal"), f"{path} needs a non-empty goal")
            self.assertIsInstance(draft.get("completion_criteria"), list)
            self.assertIsInstance(draft.get("timeout_s"), int)
            self.assertGreater(draft["timeout_s"], 0)

    def test_templates_are_cwd_scoped_and_offline(self):
        for probe in self.conf["probes"]:
            draft = json.loads((PROBES_DIR / probe["task_template"]).read_text("utf-8"))
            perms = draft["permissions"]
            self.assertEqual(perms["network"], False)
            for key in ("read", "write"):
                self.assertEqual(
                    perms[key],
                    ["{{cwd}}"],
                    f"{probe['probe_id']} {key} must be cwd-scoped placeholder",
                )

    def test_templates_omit_instantiated_fields(self):
        # task_id and cwd are injected by the verifier, not authored.
        for probe in self.conf["probes"]:
            draft = json.loads((PROBES_DIR / probe["task_template"]).read_text("utf-8"))
            self.assertNotIn("task_id", draft)
            self.assertNotIn("cwd", draft)

    def test_template_timeouts_match_conformance(self):
        for probe in self.conf["probes"]:
            draft = json.loads((PROBES_DIR / probe["task_template"]).read_text("utf-8"))
            self.assertEqual(
                draft["timeout_s"],
                probe["timeout_s"],
                f"{probe['probe_id']} template/conformance timeout_s mismatch",
            )


if __name__ == "__main__":
    unittest.main()
