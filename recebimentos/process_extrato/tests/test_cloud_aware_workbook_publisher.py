from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from openpyxl import Workbook

from cloud_aware_workbook_publisher import (StorageClass, binary_hash, classify_xlsx_diff, diagnose_storage, probe_directory_capability, publish_workbook, semantic_fingerprint)


def workbook(path: Path, value: str = "value") -> None:
    book = Workbook(); book.active["A1"] = value; book.save(path)


class CloudAwarePublisherTests(unittest.TestCase):
    def test_normal_local_file_and_atomic_directory_probe(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "official.xlsx"; workbook(path)
            self.assertEqual(diagnose_storage(path).storage_class, StorageClass.LOCAL_NORMAL)
            self.assertTrue(probe_directory_capability(path.parent).can_atomically_replace_existing_file)

    def test_semantic_fingerprint_ignores_metadata_only_xlsx_mutation(self):
        with TemporaryDirectory() as temp:
            first, second = Path(temp) / "a.xlsx", Path(temp) / "b.xlsx"; workbook(first); workbook(second)
            self.assertEqual(semantic_fingerprint(first), semantic_fingerprint(second))
            self.assertEqual(classify_xlsx_diff(first, second), "OFFICE_METADATA_ONLY")

    def test_concurrency_guard_blocks_changed_destination(self):
        with TemporaryDirectory() as temp:
            source, destination = Path(temp) / "stage.xlsx", Path(temp) / "official.xlsx"; workbook(source, "new"); workbook(destination, "old")
            result = publish_workbook(source, destination, binary_hash(source), "wrong")
            self.assertEqual(result.status, "BLOCKED"); self.assertIn("CONCURRENCY_GUARD_FAILED", result.errors)

    def test_access_denied_replacement_blocks(self):
        with TemporaryDirectory() as temp:
            with patch("cloud_aware_workbook_publisher.os.replace", side_effect=PermissionError(5, "ACCESS_DENIED")):
                capability = probe_directory_capability(temp)
            self.assertFalse(capability.can_atomically_replace_existing_file)
            self.assertTrue(capability.errors)

    def test_reparse_and_cloud_destinations_are_fail_closed(self):
        with TemporaryDirectory() as temp:
            source, destination = Path(temp) / "stage.xlsx", Path(temp) / "official.xlsx"; workbook(source); workbook(destination)
            with patch("cloud_aware_workbook_publisher._win32_attributes", return_value=0x0400):
                result = publish_workbook(source, destination, binary_hash(source), semantic_fingerprint(destination))
            self.assertEqual(result.status, "BLOCKED"); self.assertEqual(result.publication_method, "BLOCKED")

    def test_local_publication_keeps_verified_rollback_backup(self):
        with TemporaryDirectory() as temp:
            source, destination = Path(temp) / "stage.xlsx", Path(temp) / "official.xlsx"; workbook(source, "new"); workbook(destination, "old")
            result = publish_workbook(source, destination, binary_hash(source), semantic_fingerprint(destination))
            self.assertEqual(result.status, "PASS"); self.assertTrue(result.rollback_available)
            self.assertTrue(Path(result.backup_path).is_file()); self.assertEqual(semantic_fingerprint(destination), semantic_fingerprint(source))
