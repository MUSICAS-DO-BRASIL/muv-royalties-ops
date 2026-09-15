from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from openpyxl import Workbook
from cloud_native_workbook_publisher import RemoteItem, discover_remote_item, publish_workbook


class FakeGraph:
    def __init__(self, etag="v1", versions=True): self.item=RemoteItem("site","drive","item",etag,"1",0,"book.xlsx"); self.versions=versions; self.payload=b""
    def resolve_synced_path(self, path): return self.item
    def get_item(self, item): return self.item
    def version_history_available(self, item): return self.versions
    def upload_entire_file(self, item, payload, if_match):
        if if_match != self.item.etag: raise RuntimeError("etag conflict")
        self.payload=payload; self.item=RemoteItem("site","drive","item","v2","2",len(payload),"book.xlsx"); return self.item
    def download(self, item): return self.payload
    def rollback(self, item, version): return self.item

def book(path):
    workbook=Workbook(); workbook.active["A1"]="safe"; workbook.save(path)

class CloudNativePublisherTests(unittest.TestCase):
    def test_auth_unavailable_is_blocked(self):
        with TemporaryDirectory() as temp:
            source=Path(temp)/"stage.xlsx"; book(source)
            self.assertEqual(publish_workbook(source,None,None,None).status,"BLOCKED")
    def test_discovery_and_upload_readback(self):
        with TemporaryDirectory() as temp:
            source=Path(temp)/"stage.xlsx"; book(source); graph=FakeGraph(); item=discover_remote_item("C:/synced/book.xlsx",graph)
            result=publish_workbook(source,item,"v1",graph)
            self.assertEqual(result.status,"PASS"); self.assertEqual(result.etag_after,"v2"); self.assertEqual(result.rollback_reference,"1")
    def test_etag_conflict_and_missing_rollback_block(self):
        with TemporaryDirectory() as temp:
            source=Path(temp)/"stage.xlsx"; book(source); graph=FakeGraph("v2")
            self.assertIn("CONCURRENCY_CONFLICT",publish_workbook(source,graph.item,"v1",graph).errors)
            graph=FakeGraph(versions=False)
            self.assertIn("ROLLBACK_UNAVAILABLE",publish_workbook(source,graph.item,"v1",graph).errors)
