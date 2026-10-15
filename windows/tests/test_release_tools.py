"""Release containment and reproducibility checks using synthetic payloads."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from release_tools import PORTABLE_FILES, ZIP_TIMESTAMP, portable_zip, requirement_pins, version_resource


class ReleaseToolsTests(unittest.TestCase):
    def test_archive_is_deterministic_and_has_generic_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "payload"
            source.mkdir()
            for name in PORTABLE_FILES:
                (source / name).write_text(f"synthetic {name}", encoding="utf-8")
            portable_zip(source, root / "first.zip")
            for name in PORTABLE_FILES:
                (source / name).touch()
            portable_zip(source, root / "second.zip")
            self.assertEqual(hashlib.sha256((root / "first.zip").read_bytes()).digest(),
                             hashlib.sha256((root / "second.zip").read_bytes()).digest())
            with zipfile.ZipFile(root / "first.zip") as archive:
                self.assertEqual(archive.namelist(), list(PORTABLE_FILES))
                for info in archive.infolist():
                    self.assertEqual(info.date_time, ZIP_TIMESTAMP)
                    self.assertEqual(info.create_system, 0)
                    self.assertEqual(info.extra, b"")
                    self.assertEqual(info.comment, b"")

    def test_archive_rejects_unexpected_private_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "payload"
            source.mkdir()
            for name in PORTABLE_FILES:
                (source / name).write_bytes(b"fixture")
            (source / "auth.json").write_bytes(b"synthetic private fixture")
            with self.assertRaisesRegex(ValueError, "allowlist"):
                portable_zip(source, root / "unsafe.zip")
            self.assertFalse((root / "unsafe.zip").exists())

    def test_archive_rejects_missing_license(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "payload"
            source.mkdir()
            for name in PORTABLE_FILES:
                if name != "LICENSE":
                    (source / name).write_bytes(b"fixture")
            with self.assertRaisesRegex(ValueError, "allowlist"):
                portable_zip(source, root / "unsafe.zip")

    def test_archive_rejects_directory_named_like_an_allowed_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "payload"
            source.mkdir()
            for name in PORTABLE_FILES:
                (source / name).write_bytes(b"fixture")
            (source / "LICENSE").unlink()
            (source / "LICENSE").mkdir()
            with self.assertRaisesRegex(ValueError, "ordinary files"):
                portable_zip(source, root / "unsafe.zip")

    def test_release_requirements_must_be_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "requirements.txt"
            path.write_text("# fixture\nexample==1.2.3\n", encoding="utf-8")
            self.assertEqual(requirement_pins(path), {"example": "1.2.3"})
            path.write_text("example>=1.2.3\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exact"):
                requirement_pins(path)

    def test_version_metadata_is_generic(self):
        with tempfile.TemporaryDirectory() as temporary:
            resource = Path(temporary) / "version.txt"
            version_resource("1.2.8", resource)
            text = resource.read_text(encoding="utf-8")
            self.assertIn("CodexControl contributors", text)
            self.assertIn("1.2.8", text)
            self.assertNotIn(temporary, text)
            self.assertNotIn(str(Path.home()), text)

    def test_version_rejects_resource_overflow_and_injection(self):
        for version in ("65536.0.0", "1.2.3\nmalformed", "1.2"):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as temporary:
                with self.assertRaises(ValueError):
                    version_resource(version, Path(temporary) / "version.txt")


if __name__ == "__main__":
    unittest.main()
