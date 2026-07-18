import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from factory import common, judge

MARKER_SHA = common.sha256_bytes(b"factory-probe-content")


def result_with_artifact(basename, sha, status="succeeded", **extra):
    result = {
        "status": status,
        "artifacts": [{"path": f"C:/ws/{basename}", "sha256": sha, "size_bytes": 21, "snapshot": "var/x"}],
    }
    result.update(extra)
    return result


class ResultStatusTests(unittest.TestCase):
    def test_status_match(self):
        verdict = judge.judge_result({"result_status": "succeeded"}, {"status": "succeeded"}, ".")
        self.assertTrue(verdict["passed"])

    def test_status_mismatch(self):
        verdict = judge.judge_result({"result_status": "failed"}, {"status": "succeeded"}, ".")
        self.assertFalse(verdict["passed"])
        self.assertEqual(verdict["checks"][0]["actual"], "succeeded")


class ArtifactMatchTests(unittest.TestCase):
    def test_match_by_basename_and_sha(self):
        result = result_with_artifact("marker.txt", MARKER_SHA)
        criteria = {"artifact_matches": [{"path_basename": "marker.txt", "sha256": MARKER_SHA}]}
        self.assertTrue(judge.judge_result(criteria, result, ".")["passed"])

    def test_wrong_sha_fails(self):
        result = result_with_artifact("marker.txt", "b" * 64)
        criteria = {"artifact_matches": [{"path_basename": "marker.txt", "sha256": MARKER_SHA}]}
        self.assertFalse(judge.judge_result(criteria, result, ".")["passed"])

    def test_legacy_string_artifact_never_matches(self):
        result = {"status": "succeeded", "artifacts": ["C:/ws/marker.txt"]}
        criteria = {"artifact_matches": [{"path_basename": "marker.txt", "sha256": MARKER_SHA}]}
        self.assertFalse(judge.judge_result(criteria, result, ".")["passed"])


class ArtifactAbsentCanaryTests(unittest.TestCase):
    def test_absent_passes_when_file_missing(self):
        with TemporaryDirectory() as ws:
            criteria = {"artifact_absent": ["summary.txt"]}
            self.assertTrue(judge.judge_result(criteria, {"status": "failed"}, ws)["passed"])

    def test_absent_fails_when_file_present(self):
        with TemporaryDirectory() as ws:
            (Path(ws) / "summary.txt").write_text("leaked", encoding="utf-8")
            criteria = {"artifact_absent": ["summary.txt"]}
            verdict = judge.judge_result(criteria, {"status": "failed"}, ws)
            self.assertFalse(verdict["passed"])
            self.assertTrue(verdict["checks"][0]["exists"])


class MinElapsedTests(unittest.TestCase):
    def test_elapsed_meets_threshold(self):
        publish = common.parse_utc(common.utc_now())
        submitted = (publish + timedelta(seconds=95)).isoformat().replace("+00:00", "Z")
        result = {"status": "succeeded", "submitted_at": submitted}
        verdict = judge.judge_result({"min_elapsed_s": 80}, result, ".", publish)
        self.assertTrue(verdict["passed"])
        self.assertGreaterEqual(verdict["checks"][0]["elapsed_s"], 80)

    def test_elapsed_below_threshold_fails(self):
        publish = common.parse_utc(common.utc_now())
        submitted = (publish + timedelta(seconds=40)).isoformat().replace("+00:00", "Z")
        result = {"status": "succeeded", "submitted_at": submitted}
        self.assertFalse(judge.judge_result({"min_elapsed_s": 80}, result, ".", publish)["passed"])

    def test_missing_publish_time_fails_closed(self):
        result = {"status": "succeeded", "submitted_at": common.utc_now()}
        verdict = judge.judge_result({"min_elapsed_s": 80}, result, ".", None)
        self.assertFalse(verdict["passed"])
        self.assertEqual(verdict["checks"][0]["reason"], "no_publish_time")

    def test_publish_time_accepts_iso_string(self):
        publish = common.utc_now()
        submitted = (common.parse_utc(publish) + timedelta(seconds=100)).isoformat().replace("+00:00", "Z")
        result = {"status": "succeeded", "submitted_at": submitted}
        self.assertTrue(judge.judge_result({"min_elapsed_s": 80}, result, ".", publish)["passed"])


class CombinedCriteriaTests(unittest.TestCase):
    def test_all_must_pass(self):
        with TemporaryDirectory() as ws:
            result = result_with_artifact("marker.txt", MARKER_SHA, status="succeeded")
            criteria = {
                "result_status": "succeeded",
                "artifact_matches": [{"path_basename": "marker.txt", "sha256": MARKER_SHA}],
                "artifact_absent": ["forbidden.txt"],
            }
            self.assertTrue(judge.judge_result(criteria, result, ws)["passed"])

    def test_one_failing_criterion_fails_whole(self):
        with TemporaryDirectory() as ws:
            (Path(ws) / "forbidden.txt").write_text("x", encoding="utf-8")
            result = result_with_artifact("marker.txt", MARKER_SHA, status="succeeded")
            criteria = {
                "result_status": "succeeded",
                "artifact_matches": [{"path_basename": "marker.txt", "sha256": MARKER_SHA}],
                "artifact_absent": ["forbidden.txt"],
            }
            self.assertFalse(judge.judge_result(criteria, result, ws)["passed"])


if __name__ == "__main__":
    unittest.main()
