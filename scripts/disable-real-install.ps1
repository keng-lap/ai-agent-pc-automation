$names = @(
    'AI_AGENT_ENABLE_REAL_INSTALL',
    'AI_AGENT_REAL_INSTALL_RELEASE_TASK',
    'AI_AGENT_REAL_INSTALL_PACKAGE_ID',
    'AI_AGENT_REAL_INSTALL_VERSION',
    'AI_AGENT_REAL_INSTALL_EXPIRES_AT',
    'AI_AGENT_REAL_INSTALL_NONCE'
)

foreach ($name in $names) {
    Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue
}

Write-Host 'Real-install release authorization cleared from this PowerShell process.'
Write-Host 'Restart the backend from this window to keep live installation disabled.'
