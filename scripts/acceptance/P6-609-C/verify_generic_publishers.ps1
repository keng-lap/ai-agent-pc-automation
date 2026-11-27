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
)

$pythonCode = @'
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "src" / "backend"))

from agent_backend.software_discovery import WinGetManifestRepository
from agent_backend.software_evidence import SoftwareEvidenceRegistry
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
        # The signer name is deliberately changed to prove it is not a
        # trust decision. Installer SHA-256 remains checked against WinGet.
        staged = staged.model_copy(update={"signature_subject": "CN=Deliberately Different Signer"})
        evidence = SoftwareEvidenceRegistry().register_staged_candidate(
            candidate=candidate,
            staged=staged,
        )
        print(json.dumps({
            "diagnostic": "INSTALLER_SHA256_ONLY",
            "package_id": candidate.package_id,
            "version": candidate.version,
            "manifest_sha256": candidate.installer_sha256,
            "downloaded_sha256": staged.sha256,
            "signer_name_used_for_decision": False,
            "result": "PASS_SHA256_POLICY",
            "evidence_id_created": bool(evidence.evidence_id),
            "note": "Signer metadata mismatch did not block valid WinGet SHA-256 evidence. No installer was executed and no software was installed.",
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
            throw "SHA-256 trust acceptance failed for $($check.PackageId)."
        }
    }
    Write-Host ''
    Write-Host 'PASS: package passed the shared WinGet SHA-256 policy without signer-name matching.'
    Write-Host 'No installer was executed. No software was installed.'
}
finally {
    Pop-Location
    if (Test-Path -LiteralPath $pythonScript) {
        Remove-Item -LiteralPath $pythonScript -Force
    }
}
