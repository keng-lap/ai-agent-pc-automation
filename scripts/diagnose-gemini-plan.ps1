<#
.SYNOPSIS
  Diagnoses Gemini Structured Output compatibility without changing the agent.
.DESCRIPTION
  Runs two direct, minimal Gemini API probes using the backend virtualenv:
    1. The current google-genai response_schema + Pydantic model path.
    2. The response_json_schema path using the same model's JSON Schema.
  The API key is requested as a secure prompt unless GEMINI_API_KEY is already
  present in this PowerShell process. It is passed to the child Python process
  through its environment only, never written to disk or printed.
  This script does not call the local agent, approve plans, run dry-run, execute
  commands, or change Windows settings.
#>
[CmdletBinding()]
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot '_common.ps1')
Set-Location $script:RepoRoot

$python = Get-VenvPython
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Backend virtual environment not found. Run scripts\setup.ps1 first.'
}

$originalGeminiKey = [Environment]::GetEnvironmentVariable('GEMINI_API_KEY', 'Process')
if ([string]::IsNullOrWhiteSpace($originalGeminiKey)) {
    $secureKey = Read-Host 'Enter Gemini API key (input is hidden; key is not saved)' -AsSecureString
    if ($null -eq $secureKey -or $secureKey.Length -lt 20) {
        throw 'Gemini API key is missing or too short.'
    }
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
    try {
        $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
    [Environment]::SetEnvironmentVariable('GEMINI_API_KEY', $plainKey, 'Process')
    $plainKey = $null
}
else {
    Write-Host 'Using GEMINI_API_KEY already present in this PowerShell process.' -ForegroundColor DarkGray
}

$pythonCode = @'
import os
import re
import sys
from importlib.metadata import version, PackageNotFoundError

try:
    from pydantic import BaseModel, ConfigDict, Field
    from google import genai
    from google.genai import errors, types
except Exception as exc:
    print(f"[FAIL] Python dependencies: {type(exc).__name__}: {exc}")
    raise SystemExit(2)

key = os.environ.get("GEMINI_API_KEY", "")
if len(key) < 20:
    print("[FAIL] GEMINI_API_KEY was not passed to the diagnostic process.")
    raise SystemExit(2)

try:
    sdk_version = version("google-genai")
except PackageNotFoundError:
    sdk_version = "unknown"

class GeminiPlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    title: str = Field(min_length=1, max_length=120)
    detail: str = Field(min_length=1, max_length=500)

class GeminiPlanDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    goal: str = Field(min_length=1, max_length=2000)
    steps: tuple[GeminiPlanStep, ...] = Field(min_length=1, max_length=6)
    questions: tuple[str, ...] = Field(default=(), max_length=12)

client = genai.Client(api_key=key, vertexai=False)
model = "gemini-3.1-flash-lite"
prompt = (
    "Return a short plan as JSON matching the supplied schema. "
    "Use goal='test', one step with title='test' and detail='test', "
    "and an empty questions array. Do not perform any action."
)

def safe_error(exc):
    code = getattr(exc, "code", None)
    status = getattr(exc, "status", None)
    message = str(getattr(exc, "message", "") or "")
    message = message.replace(key, "[REDACTED_API_KEY]")
    message = re.sub(r"AIza[0-9A-Za-z_-]{20,}", "[REDACTED_API_KEY]", message)
    message = re.sub(r"(?i)(api[_ -]?key\s*[:=]\s*)\S+", r"\1[REDACTED]", message)
    message = " ".join(message.split())
    if len(message) > 700:
        message = message[:700] + "..."
    print(f"  HTTP/code: {code if code is not None else 'n/a'}")
    print(f"  Provider status: {status if status else 'n/a'}")
    print(f"  Provider message: {message if message else '(none)'}")

def run_probe(label, config):
    print(f"\n{label}")
    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=config,
        )
        text = (response.text or "").strip()
        if not text:
            print("[FAIL] Provider returned an empty response.")
            return False
        print("[PASS] Structured response received.")
        return True
    except errors.APIError as exc:
        print("[FAIL] Google API rejected this request.")
        safe_error(exc)
        return False
    except Exception as exc:
        message = str(exc).replace(key, "[REDACTED_API_KEY]")
        message = re.sub(r"AIza[0-9A-Za-z_-]{20,}", "[REDACTED_API_KEY]", message)
        print(f"[FAIL] {type(exc).__name__}: {message[:500]}")
        return False

print("Gemini Structured Output Diagnostic")
print(f"Model: {model}")
print(f"google-genai SDK: {sdk_version}")
print("The API key is not printed or saved.")
print("")

current_ok = run_probe(
    "TEST 1 - Current backend configuration (response_schema=Pydantic model)",
    types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=GeminiPlanDraft,
    ),
)

schema = GeminiPlanDraft.model_json_schema()
json_schema_ok = run_probe(
    "TEST 2 - JSON Schema configuration (response_json_schema)",
    types.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=schema,
    ),
)

print("\nSUMMARY")
print(f"Current response_schema path: {'PASS' if current_ok else 'FAIL'}")
print(f"response_json_schema path: {'PASS' if json_schema_ok else 'FAIL'}")
if current_ok and json_schema_ok:
    print("Both direct provider probes passed. Compare with POST /api/plans to isolate backend prompt/route behavior.")
elif json_schema_ok and not current_ok:
    print("The JSON Schema path passed while the current Pydantic response_schema path failed.")
elif current_ok and not json_schema_ok:
    print("The current response_schema path passed; response_json_schema did not.")
else:
    print("Both direct probes failed. Use the provider status/message above to identify model, key, quota, or schema rejection.")
'@

try {
    Write-Host ''
    Write-Host 'AI Agent - Gemini Structured Output Diagnostic' -ForegroundColor Cyan
    Write-Host 'Safety: direct Gemini API probes only; no agent approval, dry-run, or Windows changes.'
    Write-Host ''
    & $python -c $pythonCode
    $exitCode = $LASTEXITCODE
}
finally {
    [Environment]::SetEnvironmentVariable('GEMINI_API_KEY', $originalGeminiKey, 'Process')
    $secureKey = $null
    $plainKey = $null
    $pythonCode = $null
}

if ($exitCode -ne 0) {
    throw "Gemini diagnostic could not complete (exit code $exitCode)."
}
