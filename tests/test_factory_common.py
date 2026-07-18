import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from factory import common


class RootResolutionTests(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.pop("FACTORY_ROOT", None)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("FACTORY_ROOT", None)
        else:
            os.environ["FACTORY_ROOT"] = self._saved

    def test_explicit_root_wins_over_env(self):
        with TemporaryDirectory() as tmp:
            os.environ["FACTORY_ROOT"] = str(Path(tmp) / "env")
            explicit = Path(tmp) / "explicit"
            self.assertEqual(common.resolve_root(str(explicit)), explicit.resolve())

    def test_env_used_when_no_explicit(self):
        with TemporaryDirectory() as tmp:
            env_root = Path(tmp) / "env"
            os.environ["FACTORY_ROOT"] = str(env_root)
            self.assertEqual(common.resolve_root(None), env_root.resolve())

    def test_default_root_when_unset(self):
        self.assertEqual(common.resolve_root(None), common.DEFAULT_ROOT.resolve())


class AtomicWriteAndHashTests(unittest.TestCase):
    def test_atomic_write_json_roundtrip(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "nested" / "value.json"
            common.atomic_write_json(target, {"b": 2, "a": 1})
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"a": 1, "b": 2})
            # No leftover temp files in the directory.
            self.assertEqual(list(target.parent.glob(".factory-*")), [])

    def test_sha256_file_matches_bytes(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.bin"
            payload = b"factory-probe-content"
            path.write_bytes(payload)
            self.assertEqual(common.sha256_file(path), common.sha256_bytes(payload))

    def test_copy_into_returns_dest_and_hash(self):
        with TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.json"
            src.write_text("hello", encoding="utf-8")
            dest_dir = Path(tmp) / "evidence"
            dest, digest = common.copy_into(src, dest_dir)
            self.assertTrue(dest.is_file())
            self.assertEqual(dest.parent, dest_dir)
            self.assertEqual(digest, common.sha256_bytes(b"hello"))


class TimeTests(unittest.TestCase):
    def test_utc_now_parse_roundtrip(self):
        now = common.utc_now()
        self.assertTrue(now.endswith("Z"))
        parsed = common.parse_utc(now)
        self.assertIsNotNone(parsed.tzinfo)


if __name__ == "__main__":
    unittest.main()
