[CmdletBinding()]
param([string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..\\..")).Path)

$ErrorActionPreference = "Stop"
$python = Join-Path $RepoRoot ".venv\\Scripts\\python.exe"
$log = Join-Path ([System.IO.Path]::GetTempPath()) ("P6-609-B2-storage-" + [guid]::NewGuid().ToString("N") + ".log")
$stdout = "$log.stdout"
$stderr = "$log.stderr"
# Avoid pytest's shared %TEMP%\\pytest-of-<user> directory, which may have
# stale restrictive ACLs from an earlier run. Use a fresh per-run directory.
$pytestTempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("P6-609-B2-pytest-" + [guid]::NewGuid().ToString("N"))
$null = New-Item -ItemType Directory -Path $pytestTempRoot -Force

Push-Location $RepoRoot
try {
    $preflightCode = 0
    try {
        & (Join-Path $PSScriptRoot "preflight.ps1") -RepoRoot $RepoRoot 2>&1 | Tee-Object -FilePath $log
    }
    catch {
        $_ | Out-String | Tee-Object -FilePath $log -Append
        $preflightCode = 1
    }
    if ($preflightCode -ne 0) {
        & (Join-Path $PSScriptRoot "publish-results.ps1") -RepoRoot $RepoRoot -ResultFile $log -SuiteName Storage -ExitCode $preflightCode
        throw "Preflight FAIL. The actual error is shown above; check the uploaded Storage log."
    }

    # Capture native stdout/stderr as files. This avoids PowerShell 7's
    # NativeCommandError promotion when Python emits warnings on stderr.
    $process = Start-Process -FilePath $python -ArgumentList @("-m","pytest","--basetemp=$pytestTempRoot","../../tests/backend/test_platform_storage.py","../../tests/backend/test_job_store.py","-q") -WorkingDirectory (Join-Path $RepoRoot 'src\\backend') -Wait -PassThru -NoNewWindow -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $outText = if (Test-Path $stdout) { [System.IO.File]::ReadAllText($stdout) } else { "" }
    $errText = if (Test-Path $stderr) { [System.IO.File]::ReadAllText($stderr) } else { "" }
    if ($outText) { Add-Content -LiteralPath $log -Value $outText -NoNewline; Write-Host $outText -NoNewline }
    if ($errText) { Add-Content -LiteralPath $log -Value $errText -NoNewline; Write-Host $errText -NoNewline }
    $code = $process.ExitCode

    & (Join-Path $PSScriptRoot "publish-results.ps1") -RepoRoot $RepoRoot -ResultFile $log -SuiteName Storage -ExitCode $code
    if ($code -ne 0) { throw "Storage acceptance FAIL (pytest exit code $code). See the FAILED test and error above or open the uploaded log." }
    Write-Host "Storage acceptance PASS."
}
finally {
    foreach ($file in @($stdout, $stderr, $log)) {
        if (Test-Path $file) { Remove-Item -LiteralPath $file -Force }
    }
    if (Test-Path $pytestTempRoot) { Remove-Item -LiteralPath $pytestTempRoot -Recurse -Force -ErrorAction SilentlyContinue }
    Pop-Location
}
