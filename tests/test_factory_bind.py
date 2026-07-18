import contextlib
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from factory import cli, common, ledger


def verified_entry(**overrides):
    entry = ledger.make_entry(
        harness={"name": "pao-lwar", "version": "2.1", "contract": "lwar-runtime.v2-adp"},
        model={"name": "Claude Code", "id": "claude-fable-5"},
        runtime={"name": "PAO", "version": "0.6.1"},
        runtime_conformance="passed",
        probe_verdict="verified",
        scores={"per_probe": {}, "sample_size": 0},
        profile={},
        evidence={},
    )
    entry.update(overrides)
    return entry


def run_cli(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(argv)
    payload = json.loads(out.getvalue()) if out.getvalue().strip() else None
    return code, payload


PAIRING = "pao-lwar@2.1__claude-fable-5"


class BindGateTests(unittest.TestCase):
    def test_bind_refused_when_no_entry(self):
        with TemporaryDirectory() as tmp:
            code, payload = run_cli(["bind", "--pairing", PAIRING, "--root", tmp])
            self.assertEqual(code, 3)
            self.assertEqual(payload["reason"], "no_ledger_entry")

    def test_bind_refused_when_not_verified(self):
        with TemporaryDirectory() as tmp:
            ledger.write_entry(tmp, verified_entry(probe_verdict="failed"))
            code, payload = run_cli(["bind", "--pairing", PAIRING, "--root", tmp])
            self.assertEqual(code, 2)
            self.assertEqual(payload["reason"], "not_verified")

    def test_bind_refused_on_runtime_key_change(self):
        with TemporaryDirectory() as tmp:
            ledger.write_entry(tmp, verified_entry())
            code, payload = run_cli(
                ["bind", "--pairing", PAIRING, "--root", tmp, "--runtime-version", "9.9.9"]
            )
            self.assertEqual(code, 2)
            self.assertEqual(payload["reason"], "key_change")

    def test_bind_accepts_verified_entry(self):
        with TemporaryDirectory() as tmp:
            ledger.write_entry(tmp, verified_entry())
            code, payload = run_cli(
                ["bind", "--pairing", PAIRING, "--root", tmp, "--bus-root", str(Path(tmp) / "bus")]
            )
            self.assertEqual(code, 0)
            self.assertEqual(payload["schema_version"], "factory.binding-instruction.v1")
            self.assertEqual(payload["pairing"], PAIRING)
            self.assertEqual(payload["contract"], "lwar-runtime.v2-adp")
            self.assertIn("register", payload["register_args"])

    def test_bind_by_triple_matches_pairing(self):
        with TemporaryDirectory() as tmp:
            ledger.write_entry(tmp, verified_entry())
            code, payload = run_cli(
                [
                    "bind", "--harness", "pao-lwar", "--harness-version", "2.1",
                    "--model-id", "claude-fable-5", "--root", tmp,
                ]
            )
            self.assertEqual(code, 0)
            self.assertEqual(payload["pairing"], PAIRING)


class LedgerShowTests(unittest.TestCase):
    def test_show_single_and_list(self):
        with TemporaryDirectory() as tmp:
            ledger.write_entry(tmp, verified_entry())
            code, payload = run_cli(["ledger-show", "--pairing", PAIRING, "--root", tmp])
            self.assertEqual(code, 0)
            self.assertEqual(payload["entry"]["probe_verdict"], "verified")

            code, payload = run_cli(["ledger-show", "--root", tmp])
            self.assertEqual(code, 0)
            self.assertEqual(payload["count"], 1)
            self.assertEqual(payload["entries"][0]["pairing"], PAIRING)

    def test_show_missing_pairing(self):
        with TemporaryDirectory() as tmp:
            code, payload = run_cli(["ledger-show", "--pairing", "x@0__y", "--root", tmp])
            self.assertEqual(code, 3)


class VerifyPairingCacheTests(unittest.TestCase):
    def test_valid_cached_entry_short_circuits(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            ledger.write_entry(tmp, verified_entry())
            manifest = {
                "schema_version": "factory.conformance.v1",
                "harness": {"name": "pao-lwar", "version": "2.1", "contract": "lwar-runtime.v2-adp"},
                "probes": [
                    {
                        "probe_id": "content_exactness",
                        "task_template": "content.json",
                        "pass_criteria": {"result_status": "succeeded"},
                        "verifier_actions": [],
                    }
                ],
            }
            manifest_path = tmp / "conformance.json"
            common.atomic_write_json(manifest_path, manifest)
            # --pao-cli points nowhere; the cache short-circuit must return before
            # any subprocess is built or invoked.
            code, payload = run_cli(
                [
                    "verify-pairing",
                    "--conformance", str(manifest_path),
                    "--model-id", "claude-fable-5",
                    "--runtime-version", "0.6.1",
                    "--lwar-id", "LWAR1",
                    "--bus-root", str(tmp / "bus"),
                    "--workspace", str(tmp / "ws"),
                    "--pao-cli", str(tmp / "does-not-exist.py"),
                    "--root", str(tmp),
                ]
            )
            self.assertEqual(code, 0)
            self.assertEqual(payload["event"], "verify_pairing_cached")
            self.assertEqual(payload["probe_verdict"], "verified")


if __name__ == "__main__":
    unittest.main()
