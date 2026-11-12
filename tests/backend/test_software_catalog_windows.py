"""Live Windows acceptance test for Microsoft's signed WinGet source2 catalog."""

import os
from pathlib import Path

import pytest
import requests

from agent_backend.software_catalog import (
    MAX_MSIX_BYTES,
    USER_AGENT,
    WINGET_SOURCE2_URL,
    MicrosoftWinGetCatalogIndex,
    WindowsMsixSignatureVerifier,
)


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
def test_wintrust_returns_subject_from_verified_microsoft_catalog(tmp_path):
    response = requests.get(
        WINGET_SOURCE2_URL,
        headers={"Accept": "application/octet-stream", "User-Agent": USER_AGENT},
        timeout=(5.0, 30.0),
        allow_redirects=False,
        stream=True,
    )
    path = tmp_path / "source2.msix"
    total = 0
    try:
        assert response.status_code == 200
        assert response.headers.get("Content-Encoding", "identity").lower() in {"", "identity"}
        with path.open("wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                assert total <= MAX_MSIX_BYTES
                output.write(chunk)
    finally:
        response.close()

    verifier = WindowsMsixSignatureVerifier()
    assert verifier.verify(path) is True
    subject = verifier.verify_and_get_signer_subject(path)

    assert subject
    assert "CN=" in subject
    assert "Microsoft Corporation" in subject
