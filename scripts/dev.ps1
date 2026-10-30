<#
.SYNOPSIS
  Runs the backend (FastAPI) and the frontend (Angular dev server) together.
.DESCRIPTION
  Both servers bind to 127.0.0.1 only (approved proposal P-SEC-1).
  Ports come from .env (BACKEND_PORT, FRONTEND_PORT). Press Ctrl+C to stop both.
#>
. (Join-Path $PSScriptRoot '_common.ps1')

Set-Location $script:RepoRoot
$envFile = if (Test-Path '.env') { '.env' } else { '.env.example' }
Import-DotEnv $envFile

$localAgentToken = Get-EnvOrDefault 'LOCAL_AGENT_TOKEN' ''
if ($localAgentToken -notmatch '^[0-9a-f]{64}$') {
    throw 'LOCAL_AGENT_TOKEN is missing or invalid. Run scripts\setup.ps1 again.'
}

$venvPython = Get-VenvPython
if (-not (Test-Path $venvPython) -or -not (Test-Path 'src/frontend/node_modules')) {
    throw 'Dependencies are not installed. Run scripts\setup.ps1 first.'
}

$backendHost = Get-EnvOrDefault 'BACKEND_HOST' '127.0.0.1'
$backendPort = Get-EnvOrDefault 'BACKEND_PORT' '8000'
$frontendPort = Get-EnvOrDefault 'FRONTEND_PORT' '4200'

function Stop-ProcessTree($Process) {
    if ($null -eq $Process -or $Process.HasExited) { return }
    if ($script:IsWin) {
        & taskkill /PID $Process.Id /T /F | Out-Null
    } else {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
    }
}

$backend = $null
$frontend = $null
try {
    # Both child processes inherit LOCAL_AGENT_TOKEN from this process.
    $backend = Start-Process -FilePath $venvPython -ArgumentList @('-m', 'agent_backend') -WorkingDirectory (Join-Path $script:RepoRoot 'src/backend') -NoNewWindow -PassThru
    $null = $backend.Handle

    $feWorkDir = Join-Path $script:RepoRoot 'src/frontend'
    if ($script:IsWin) {
        $frontend = Start-Process -FilePath 'cmd.exe' -ArgumentList @('/c', 'npm', 'run', 'start', '--', '--port', $frontendPort) -WorkingDirectory $feWorkDir -NoNewWindow -PassThru
    } else {
        $frontend = Start-Process -FilePath 'npm' -ArgumentList @('run', 'start', '--', '--port', $frontendPort) -WorkingDirectory $feWorkDir -NoNewWindow -PassThru
    }
    $null = $frontend.Handle

    Write-Host ''
    Write-Host "Backend : http://${backendHost}:$backendPort/health" -ForegroundColor Green
    Write-Host "Frontend: http://127.0.0.1:$frontendPort/" -ForegroundColor Green
    Write-Host 'Press Ctrl+C to stop both.'
    while (-not $backend.HasExited -and -not $frontend.HasExited) { Start-Sleep -Seconds 1 }
    Write-Warning 'One of the servers exited; stopping the other.'
} finally {
    Stop-ProcessTree $backend
    Stop-ProcessTree $frontend
}
