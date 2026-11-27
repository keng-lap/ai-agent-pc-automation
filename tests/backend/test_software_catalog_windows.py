"""Live Windows acceptance test for Microsoft's signed WinGet source2 catalog."""

import os

import pytest

from agent_backend.software_catalog import MicrosoftWinGetCatalogIndex


@pytest.mark.skipif(os.name != "nt", reason="MSIX trust validation requires Windows")
def test_live_microsoft_source2_catalog_signature_and_search():
    index = MicrosoftWinGetCatalogIndex()
    result = index.search("DBeaver", limit=10)

    assert result.source == "microsoft-winget-source2"
    assert result.source_version
    assert len(result.source_sha256) == 64
    assert result.candidates
    assert any(
        candidate.package_id == "DBeaver.DBeaver.Community"
        for candidate in result.candidates
    )
    assert index.source_signer_subject
    assert "CN=" in index.source_signer_subject
    assert "Microsoft Corporation" in index.source_signer_subject
    assert index.source_signer_sha256
    assert len(index.source_signer_sha256) == 64
    assert all(char in "0123456789abcdef" for char in index.source_signer_sha256)

class _FakeWinVerifyTrust:
    def __init__(self):
        self.calls = []

    def __call__(self, _handle, _action, trust_data):
        data = trust_data._obj
        self.calls.append((data.dwProvFlags, data.fdwRevocationChecks, data.dwStateAction))
        return 0x800B010A


class _FakeWinTrustLibrary:
    def __init__(self):
        self.WinVerifyTrust = _FakeWinVerifyTrust()


def test_authenticode_chain_build_can_retrieve_missing_intermediates(tmp_path, monkeypatch):
    from agent_backend import software_catalog
    from agent_backend.software_catalog import WindowsMsixSignatureVerifier

    installer = tmp_path / "installer.exe"
    installer.write_bytes(b"test-installer")
    library = _FakeWinTrustLibrary()
    monkeypatch.setattr(software_catalog.os, "name", "nt")
    monkeypatch.setattr(
        software_catalog.ctypes,
        "WinDLL",
        lambda *_args, **_kwargs: library,
        raising=False,
    )

    trusted, subject, thumbprint, hresult = (
        WindowsMsixSignatureVerifier().verify_with_diagnostics(installer)
    )

    assert trusted is False
    assert subject is None
    assert thumbprint is None
    assert hresult == "0x800B010A"
    assert library.WinVerifyTrust.calls[0][0] == 0x80
    assert library.WinVerifyTrust.calls[0][1] == 1
    assert library.WinVerifyTrust.calls[0][0] & 0x1000 == 0
