[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Project virtual environment was not found. Run scripts\setup.ps1 first.'
}

$checks = @(
    @{
        PackageId = 'GitHub.GitHubDesktop'
        Version = '3.7.0'
        Architecture = 'x64'
    },
    @{
        PackageId = 'Discord.Discord'
        Version = '1.0.9269'
        Architecture = 'x64'
    }
)

$pythonCode = @'
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "src" / "backend"))

from agent_backend.software_discovery import WinGetManifestRepository
from agent_backend.software_evidence import SoftwareEvidenceRegistry, signer_subject_matches_publisher
from agent_backend.software_staging import InstallerStager

package_id, version, architecture = sys.argv[1:4]
discovery = WinGetManifestRepository().discover(
    package_id=package_id,
    version=version,
    architecture=architecture,
)
candidate = discovery.candidate
if discovery.status != "CONDITIONAL" or candidate is None:
    raise SystemExit(f"Discovery did not produce a conditional candidate: {discovery.status}")
if candidate.publisher_verification not in {"NOT_CHECKED", "VERIFIED"}:
    raise SystemExit("Publisher source check was not eligible for Authenticode verification")

with tempfile.TemporaryDirectory(prefix="aiagent-publisher-acceptance-") as temp_dir:
    staging_root = Path(temp_dir) / "staging"
    staged = InstallerStager().stage(candidate, staging_root=staging_root)
    try:
        print(json.dumps({
            "diagnostic": "PUBLISHER_IDENTITY",
            "package_id": candidate.package_id,
            "manifest_publisher": candidate.publisher,
            "authenticode_signer_subject": staged.signature_subject,
            "certificate_sha256": staged.signature_sha256,
            "subject_match": signer_subject_matches_publisher(
                staged.signature_subject or "", candidate.publisher
            ),
        }, ensure_ascii=False))
        evidence = SoftwareEvidenceRegistry().register_staged_candidate(
            candidate=candidate,
            staged=staged,
        )
        print(json.dumps({
            "result": "PASS_GENERIC_PUBLISHER",
            "package_id": evidence.package_id,
            "version": evidence.version,
            "architecture": evidence.architecture,
            "scope": evidence.scope,
            "manifest_publisher": evidence.publisher,
            "authenticode_signer_subject": evidence.signature_subject,
            "certificate_sha256": evidence.signature_sha256,
            "installer_sha256": evidence.installer_sha256,
            "manifest_source": evidence.manifest_source_url,
            "note": "Verification only. No installer was executed and no software was installed.",
        }, ensure_ascii=False))
    finally:
        Path(staged.file_path).unlink(missing_ok=True)
'@

$pythonScript = Join-Path $env:TEMP ('aiagent-publisher-acceptance-' + [Guid]::NewGuid().ToString('N') + '.py')
[System.IO.File]::WriteAllText($pythonScript, $pythonCode, [System.Text.UTF8Encoding]::new($false))

Push-Location $repoRoot
try {
    foreach ($check in $checks) {
        Write-Host "Verifying $($check.PackageId) $($check.Version) ($($check.Architecture))..."
        & $python $pythonScript $check.PackageId $check.Version $check.Architecture
        if ($LASTEXITCODE -ne 0) {
            throw "Generic publisher acceptance failed for $($check.PackageId)."
        }
    }
    Write-Host ''
    Write-Host 'PASS: both unrelated package publishers matched their WinGet manifest Publisher.'
    Write-Host 'No installer was executed. No software was installed.'
}
finally {
    Pop-Location
    if (Test-Path -LiteralPath $pythonScript) {
        Remove-Item -LiteralPath $pythonScript -Force
    }
}
