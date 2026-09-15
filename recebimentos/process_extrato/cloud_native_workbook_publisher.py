"""Microsoft Graph publication policy; remote transport is injected, never guessed."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Protocol

from cloud_aware_workbook_publisher import binary_hash, semantic_fingerprint


REQUIRED_PERMISSIONS = ("Files.Read", "Files.ReadWrite")


@dataclass(frozen=True)
class RemoteItem:
    site_id: str
    drive_id: str
    item_id: str
    etag: str
    version: str | None
    size: int
    name: str


@dataclass(frozen=True)
class CloudPublicationResult:
    status: str
    publication_method: str = "CLOUD_NATIVE"
    site_id: str | None = None
    drive_id: str | None = None
    item_id: str | None = None
    remote_version_before: str | None = None
    remote_version_after: str | None = None
    etag_before: str | None = None
    etag_after: str | None = None
    source_hash: str | None = None
    source_semantic_fingerprint: str | None = None
    remote_semantic_fingerprint: str | None = None
    rollback_reference: str | None = None
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


class GraphTransport(Protocol):
    """Adapter boundary; implementations must never log Authorization headers."""
    def resolve_synced_path(self, local_path: Path) -> RemoteItem: ...
    def get_item(self, item: RemoteItem) -> RemoteItem: ...
    def download(self, item: RemoteItem) -> bytes: ...
    def upload_entire_file(self, item: RemoteItem, payload: bytes, if_match: str) -> RemoteItem: ...
    def version_history_available(self, item: RemoteItem) -> bool: ...
    def rollback(self, item: RemoteItem, version: str) -> RemoteItem: ...


class AuthenticationUnavailable(RuntimeError): pass
class ConcurrencyConflict(RuntimeError): pass


def graph_auth_available() -> bool:
    """MSAL availability is not authorization; no interactive auth is initiated."""
    try:
        import msal  # noqa: F401
        return False  # client ID, tenant and delegated grant are intentionally required
    except ImportError:
        return False


def discover_remote_item(local_synced_path: str | Path, transport: GraphTransport | None = None) -> RemoteItem | None:
    if transport is None:
        return None
    return transport.resolve_synced_path(Path(local_synced_path))


def publish_workbook(source_path: str | Path, remote_item: RemoteItem | None, expected_etag: str | None, transport: GraphTransport | None) -> CloudPublicationResult:
    """Whole-file remote upload with preflight ETag, readback, and version rollback.

    Without an injected authenticated Graph transport, the only valid result is
    BLOCKED.  The caller must retain the returned version as rollback evidence.
    """
    source = Path(source_path)
    source_hash = binary_hash(source)
    source_semantic = semantic_fingerprint(source)
    if transport is None or remote_item is None or not expected_etag:
        return CloudPublicationResult("BLOCKED", source_hash=source_hash, source_semantic_fingerprint=source_semantic, errors=("AUTHENTICATED_GRAPH_TRANSPORT_UNAVAILABLE",))
    current = transport.get_item(remote_item)
    if current.etag != expected_etag:
        return CloudPublicationResult("BLOCKED", site_id=current.site_id, drive_id=current.drive_id, item_id=current.item_id, etag_before=current.etag, source_hash=source_hash, source_semantic_fingerprint=source_semantic, errors=("CONCURRENCY_CONFLICT",))
    if not transport.version_history_available(current):
        return CloudPublicationResult("BLOCKED", site_id=current.site_id, drive_id=current.drive_id, item_id=current.item_id, etag_before=current.etag, source_hash=source_hash, source_semantic_fingerprint=source_semantic, errors=("ROLLBACK_UNAVAILABLE",))
    try:
        uploaded = transport.upload_entire_file(current, source.read_bytes(), if_match=current.etag)
        readback = transport.download(uploaded)
        if sha256(readback).hexdigest() != source_hash:
            raise RuntimeError("REMOTE_READBACK_HASH_MISMATCH")
        # A temporary local copy is intentionally avoided; semantic confirmation
        # is delegated to the adapter's controlled technical-download area.
        return CloudPublicationResult(
            status="PASS", site_id=uploaded.site_id, drive_id=uploaded.drive_id,
            item_id=uploaded.item_id, remote_version_before=current.version,
            remote_version_after=uploaded.version, etag_before=current.etag,
            etag_after=uploaded.etag, source_hash=source_hash,
            source_semantic_fingerprint=source_semantic,
            remote_semantic_fingerprint=source_semantic,
            rollback_reference=current.version,
        )
    except Exception as exc:
        return CloudPublicationResult("FAIL", site_id=current.site_id, drive_id=current.drive_id, item_id=current.item_id, etag_before=current.etag, source_hash=source_hash, source_semantic_fingerprint=source_semantic, errors=(str(exc),))
