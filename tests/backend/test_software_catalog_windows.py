"""Live Windows acceptance test for Microsoft's signed WinGet source2 catalog."""

import os
from pathlib import Path

import pytest

from agent_backend.software_catalog import MicrosoftWinGetCatalogIndex, WindowsMsixSignatureVerifier


@pytest.mark.skipif(os.name != "nt", reason="MSIX trust validation requires Windows")
def test_live_microsoft_source2_catalog_signature_and_search():
    result = MicrosoftWinGetCatalogIndex().search("DBeaver", limit=10)

    assert result.source == "microsoft-winget-source2"
    assert result.source_version
    assert len(result.source_sha256) == 64
    assert result.candidates
    assert any(
        candidate.package_id == "DBeaver.DBeaver.Community"
        for candidate in result.candidates
    )



@pytest.mark.skipif(os.name != "nt", reason="Authenticode signer inspection requires Windows")
def test_wintrust_returns_subject_from_verified_windows_binary():
    system_root = Path(os.environ["WINDIR"])
    signed_binary = system_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"

    verifier = WindowsMsixSignatureVerifier()
    assert verifier.verify(signed_binary) is True
    subject = verifier.verify_and_get_signer_subject(signed_binary)

    assert subject
    assert "CN=" in subject
    assert "O=" in subject
