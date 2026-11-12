"""Live Windows acceptance test for Microsoft's signed WinGet source2 catalog."""

import os

import pytest

from agent_backend.software_catalog import MicrosoftWinGetCatalogIndex


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
