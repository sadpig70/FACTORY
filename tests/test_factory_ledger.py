import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from factory import common, ledger


def sample_entry(**overrides):
    entry = ledger.make_entry(
        harness={"name": "pao-lwar", "version": "2.1", "contract": "lwar-runtime.v2-adp"},
        model={"name": "Claude Code", "id": "claude-fable-5"},
        runtime={"name": "PAO", "version": "0.6.1"},
        runtime_conformance="passed",
        probe_verdict="verified",
        scores={"per_probe": {"content_exactness": True}, "sample_size": 1},
        profile={"median_task_time_s": 12.0, "cost_class": "standard", "sample_size": 1},
        evidence={"copied_results": ["content_exactness/r.json"], "content_hashes": {"content_exactness/r.json": "d" * 64}},
    )
    entry.update(overrides)
    return entry


class LedgerShapeTests(unittest.TestCase):
    def test_entry_has_all_decision3_fields(self):
        entry = sample_entry()
        for key in (
            "schema_version", "harness", "model", "runtime", "binding_mode",
            "runtime_conformance", "probe_verdict", "soak_verdict", "scores",
            "profile", "model_attested", "evidence", "invalidation_keys",
            "verified_at", "expires_policy", "production_stats",
        ):
            self.assertIn(key, entry)
        self.assertEqual(entry["schema_version"], "factory.match.v1")
        self.assertEqual(entry["binding_mode"], "hot")
        self.assertEqual(entry["soak_verdict"], "not_started")
        self.assertTrue(entry["model_attested"])
        self.assertIsNone(entry["profile"]["bias_fingerprint"])
        self.assertEqual(entry["production_stats"], {"tasks": 0, "success_rate": None, "sample_size": 0})
        self.assertEqual(
            entry["invalidation_keys"],
            {"harness_version": "2.1", "model_id": "claude-fable-5", "runtime_version": "0.6.1"},
        )

    def test_pairing_key_format_and_sanitisation(self):
        self.assertEqual(
            ledger.pairing_key("pao-lwar", "2.1", "claude-fable-5"),
            "pao-lwar@2.1__claude-fable-5",
        )
        self.assertEqual(ledger.pairing_key("a/b", "1", "c d"), "a_b@1__c_d")

    def test_bad_verdict_rejected(self):
        with self.assertRaises(ValueError):
            ledger.make_entry(
                harness={"name": "h", "version": "1", "contract": "c"},
                model={"id": "m"},
                runtime={"version": "1"},
                runtime_conformance="passed",
                probe_verdict="bogus",
                scores={},
                profile={},
                evidence={},
            )


class LedgerRoundTripTests(unittest.TestCase):
    def test_write_then_load(self):
        with TemporaryDirectory() as tmp:
            entry = sample_entry()
            path = ledger.write_entry(tmp, entry)
            self.assertEqual(path.name, "pao-lwar@2.1__claude-fable-5.json")
            loaded = ledger.load_entry(tmp, "pao-lwar@2.1__claude-fable-5")
            self.assertEqual(loaded, entry)

    def test_load_missing_returns_none(self):
        with TemporaryDirectory() as tmp:
            self.assertIsNone(ledger.load_entry(tmp, "nope@0__x"))


class InvalidationTests(unittest.TestCase):
    def current_keys(self):
        return {"harness_version": "2.1", "model_id": "claude-fable-5", "runtime_version": "0.6.1"}

    def test_valid_when_verified_keys_match_and_fresh(self):
        entry = sample_entry()
        self.assertIsNone(ledger.invalidation_reason(entry, self.current_keys()))
        self.assertTrue(ledger.is_valid_cached(entry, self.current_keys()))

    def test_not_verified_is_invalid(self):
        entry = sample_entry(probe_verdict="failed")
        self.assertEqual(ledger.invalidation_reason(entry, self.current_keys()), "not_verified")

    def test_key_change_invalidates(self):
        entry = sample_entry()
        keys = self.current_keys()
        keys["runtime_version"] = "0.7.0"
        self.assertEqual(ledger.invalidation_reason(entry, keys), "key_change")

    def test_age_beyond_max_age_days_expires(self):
        old = common.parse_utc(common.utc_now()) - timedelta(days=31)
        entry = sample_entry(verified_at=old.isoformat().replace("+00:00", "Z"))
        self.assertEqual(ledger.invalidation_reason(entry, self.current_keys()), "expired")

    def test_age_within_max_age_days_valid(self):
        recent = common.parse_utc(common.utc_now()) - timedelta(days=29)
        entry = sample_entry(verified_at=recent.isoformat().replace("+00:00", "Z"))
        self.assertIsNone(ledger.invalidation_reason(entry, self.current_keys()))

    def test_keys_optional_still_checks_verdict_and_age(self):
        entry = sample_entry()
        self.assertIsNone(ledger.invalidation_reason(entry))


if __name__ == "__main__":
    unittest.main()
