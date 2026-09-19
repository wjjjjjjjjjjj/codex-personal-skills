[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$skillRoot = Split-Path -Parent $PSScriptRoot
$convert = Join-Path $skillRoot "scripts\convert.ps1"
$fixture = Join-Path $PSScriptRoot "fixtures\markitdown.cmd"
$powershell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("markitdown-skill-test-" + [guid]::NewGuid().ToString("N"))
$bin = Join-Path $tempRoot "bin"
$data = Join-Path $tempRoot "data"
New-Item -ItemType Directory -Path $bin, $data -Force | Out-Null
Copy-Item -LiteralPath $fixture -Destination (Join-Path $bin "markitdown.cmd")

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw "ASSERTION FAILED: $Message" }
}

function Invoke-Convert {
    param([string[]]$Arguments, [string]$PathValue, [bool]$Fail = $false)
    $oldPath = $env:PATH
    $oldFail = $env:FAKE_MARKITDOWN_FAIL
    try {
        $env:PATH = $PathValue
        if ($Fail) { $env:FAKE_MARKITDOWN_FAIL = "1" } else { Remove-Item Env:FAKE_MARKITDOWN_FAIL -ErrorAction SilentlyContinue }
        $lines = & $powershell -NoProfile -ExecutionPolicy Bypass -File $convert @Arguments 2>&1
        $exitCode = $LASTEXITCODE
        $json = ($lines | Out-String) | ConvertFrom-Json
        return [pscustomobject]@{ ExitCode = $exitCode; Json = $json }
    } finally {
        $env:PATH = $oldPath
        if ($null -eq $oldFail) { Remove-Item Env:FAKE_MARKITDOWN_FAIL -ErrorAction SilentlyContinue } else { $env:FAKE_MARKITDOWN_FAIL = $oldFail }
    }
}

try {
    $source = Join-Path $data "source.txt"
    $target = Join-Path $data "source.md"
    Set-Content -LiteralPath $source -Value "source" -Encoding UTF8

    $missing = Invoke-Convert -Arguments @("-InputPath", (Join-Path $data "missing.txt")) -PathValue $bin
    Assert-True ($missing.ExitCode -eq 2) "nonexistent input must exit 2"
    Assert-True ($missing.Json.status -eq "no_work") "nonexistent input must return no_work JSON"

    $url = Invoke-Convert -Arguments @("-InputPath", "https://example.com/a.pdf") -PathValue $bin
    Assert-True ($url.ExitCode -eq 2) "URL input must exit 2"

    Set-Content -LiteralPath $target -Value "old content" -Encoding UTF8
    $oldHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
    $failed = Invoke-Convert -Arguments @("-InputPath", $source, "-Force") -PathValue $bin -Fail $true
    $newHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
    Assert-True ($failed.ExitCode -eq 1) "failed conversion must exit 1"
    Assert-True ($oldHash -eq $newHash) "failed -Force conversion must preserve old output"
    Assert-True (@(Get-ChildItem -LiteralPath $data -Filter "*.tmp.md" -Force).Count -eq 0) "failed conversion must clean temp files"

    $success = Invoke-Convert -Arguments @("-InputPath", $source, "-Force") -PathValue $bin
    Assert-True ($success.ExitCode -eq 0) "successful conversion must exit 0"
    Assert-True ((Get-Content -LiteralPath $target -Raw) -match "converted") "successful conversion must replace target"

    $missingCommand = Invoke-Convert -Arguments @("-InputPath", $source, "-Force") -PathValue $data
    Assert-True ($missingCommand.ExitCode -eq 2) "missing command must exit 2"
    Assert-True ($missingCommand.Json.status -eq "environment_error") "missing command must return environment_error JSON"

    Write-Output "PASS MarkItDown wrapper regression suite"
} finally {
    if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force }
}
