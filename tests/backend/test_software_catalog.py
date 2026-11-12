"""Tests for the signed Microsoft WinGet source2 catalog search."""

import io
import sqlite3
import zipfile

import pytest

from agent_backend.software_catalog import (
    EXPECTED_PACKAGE_NAME,
    EXPECTED_PUBLISHER,
    WINGET_SOURCE2_URL,
    CatalogUnavailable,
    MicrosoftWinGetCatalogIndex,
)


def build_catalog_msix(*, publisher=EXPECTED_PUBLISHER, include_required_columns=True):
    database = sqlite3.connect(":memory:")
    if include_required_columns:
        database.execute(
            "CREATE TABLE packages (id TEXT PRIMARY KEY, name TEXT NOT NULL, "
            "moniker TEXT, latest_version TEXT NOT NULL)"
        )
        database.executemany(
            "INSERT INTO packages VALUES (?, ?, ?, ?)",
            [
                ("DBeaver.DBeaver.Community", "DBeaver Community Edition", "dbeaver", "25.3.0"),
                ("DBeaverCorp.DBeaverEnterpriseEdition", "DBeaver Enterprise Edition", None, "25.3.0"),
                ("Mozilla.Firefox", "Mozilla Firefox", "firefox", "145.0"),
            ],
        )
    else:
        database.execute("CREATE TABLE packages (id TEXT, name TEXT)")
    database_bytes = database.serialize()
    database.close()

    manifest = (
        '<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10">'
        f'<Identity Name="{EXPECTED_PACKAGE_NAME}" Publisher="{publisher}" Version="1.0.0.0" />'
        "</Package>"
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("AppxManifest.xml", manifest)
        archive.writestr("AppxBlockMap.xml", "<BlockMap />")
        archive.writestr("AppxSignature.p7x", b"PKCX-test-signature")
        archive.writestr("Public/index.db", database_bytes)
    return output.getvalue()


class FakeResponse:
    def __init__(self, body, status_code=200):
        self.status_code = status_code
        self.headers = {"Content-Length": str(len(body))}
        self.body = body
        self.closed = False

    def iter_content(self, chunk_size):
        for offset in range(0, len(self.body), chunk_size):
            yield self.body[offset : offset + chunk_size]

    def close(self):
        self.closed = True


class FakeSource:
    def __init__(self, body=None, status_code=200):
        self.body = body if body is not None else build_catalog_msix()
        self.status_code = status_code
        self.calls = []
        self.responses = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = FakeResponse(self.body, self.status_code)
        self.responses.append(response)
        return response


class AcceptSignature:
    def __init__(self, accepted=True):
        self.accepted = accepted
        self.paths = []

    def verify(self, path):
        self.paths.append(path)
        return self.accepted


class AcceptSignatureWithIdentity:
    def verify_and_get_signer_identity(self, path):
        assert path.is_file()
        return True, "CN=Microsoft Corporation", "d" * 64


class TamperDuringSignatureCheck(AcceptSignature):
    def verify(self, path):
        self.paths.append(path)
        path.write_bytes(b"tampered after trust check")
        return True


def make_index(source, verifier=None):
    return MicrosoftWinGetCatalogIndex(
        http_get=source.get,
        signature_verifier=verifier or AcceptSignature(),
    )


def test_catalog_search_resolves_product_name_without_ai_or_winget_cli():
    source = FakeSource()
    verifier = AcceptSignature()
    result = make_index(source, verifier).search("DBeaver")

    assert [candidate.package_id for candidate in result.candidates] == [
        "DBeaver.DBeaver.Community",
        "DBeaverCorp.DBeaverEnterpriseEdition",
    ]
    assert result.candidates[0].name == "DBeaver Community Edition"
    assert result.candidates[0].latest_version == "25.3.0"
    assert result.source == "microsoft-winget-source2"
    assert len(result.source_sha256) == 64
    assert source.calls[0][0] == WINGET_SOURCE2_URL
    assert source.calls[0][1]["allow_redirects"] is False
    assert source.responses[0].closed is True
    assert verifier.paths and not verifier.paths[0].exists()


def test_catalog_index_is_cached_between_searches():
    source = FakeSource()
    index = make_index(source)

    first = index.search("DBeaver")
    second = index.search("Firefox")

    assert len(first.candidates) == 2
    assert len(second.candidates) == 1
    assert second.candidates[0].package_id == "Mozilla.Firefox"
    assert len(source.calls) == 1


def test_catalog_search_uses_bound_sql_parameters():
    result = make_index(FakeSource()).search("' OR 1=1 --")
    assert result.candidates == ()


def test_loaded_catalog_connection_is_read_only():
    index = make_index(FakeSource())
    index.search("DBeaver")

    with pytest.raises(sqlite3.OperationalError):
        index._connection.execute("DELETE FROM packages")


def test_catalog_signature_failure_blocks_search():
    with pytest.raises(CatalogUnavailable):
        make_index(FakeSource(), AcceptSignature(accepted=False)).search("DBeaver")


def test_catalog_changed_after_signature_validation_is_rejected():
    with pytest.raises(CatalogUnavailable):
        make_index(FakeSource(), TamperDuringSignatureCheck()).search("DBeaver")


def test_catalog_wrong_publisher_is_rejected_after_signature_check():
    body = build_catalog_msix(publisher="CN=Untrusted Publisher")
    with pytest.raises(CatalogUnavailable):
        make_index(FakeSource(body), AcceptSignature()).search("DBeaver")


def test_catalog_rejects_unrecognized_sqlite_schema():
    body = build_catalog_msix(include_required_columns=False)
    with pytest.raises(CatalogUnavailable):
        make_index(FakeSource(body), AcceptSignature()).search("DBeaver")


def test_catalog_download_does_not_follow_redirects():
    source = FakeSource(status_code=302)
    with pytest.raises(CatalogUnavailable):
        make_index(source).search("DBeaver")
    assert source.calls[0][1]["allow_redirects"] is False
    assert source.responses[0].closed is True


@pytest.mark.parametrize("query", ["", " ", "x", "\u0000bad", "a" * 129])
def test_catalog_rejects_invalid_queries_before_network(query):
    source = FakeSource()
    with pytest.raises(ValueError):
        make_index(source).search(query)
    assert source.calls == []


def test_catalog_retains_certificate_fingerprint_from_verified_signer():
    index = make_index(FakeSource(), AcceptSignatureWithIdentity())
    index.search("DBeaver")

    assert index.source_signer_subject == "CN=Microsoft Corporation"
    assert index.source_signer_sha256 == "d" * 64
