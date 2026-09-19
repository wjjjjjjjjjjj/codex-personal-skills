[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string[]]$InputPath,

    [string]$OutputDirectory,

    [switch]$Recurse,

    [switch]$Force,

    [switch]$UsePlugins,

    [switch]$KeepDataUris
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$supportedExtensions = @(
    ".pdf", ".docx", ".pptx", ".xlsx", ".xls",
    ".html", ".htm", ".csv", ".json", ".xml", ".txt",
    ".zip", ".epub", ".msg", ".eml",
    ".wav", ".mp3",
    ".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff", ".bmp"
)

function Write-ResultAndExit {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Summary,
        [Parameter(Mandatory = $true)]
        [int]$ExitCode
    )
    $Summary | ConvertTo-Json -Depth 8
    exit $ExitCode
}

function Get-MarkItDownCommand {
    $command = Get-Command "markitdown" -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        throw "The markitdown command was not found. Install Microsoft MarkItDown and the required format extras, then ensure its Scripts directory is on PATH."
    }
    return $command.Source
}

function Get-UniqueTargetPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DesiredPath,
        [switch]$AllowOverwrite
    )
    if ($AllowOverwrite -or -not (Test-Path -LiteralPath $DesiredPath)) {
        return $DesiredPath
    }
    $directory = Split-Path -Parent $DesiredPath
    $stem = [System.IO.Path]::GetFileNameWithoutExtension($DesiredPath)
    $candidate = Join-Path $directory ($stem + "-converted.md")
    if (-not (Test-Path -LiteralPath $candidate)) {
        return $candidate
    }
    $index = 2
    while ($true) {
        $candidate = Join-Path $directory ("{0}-converted-{1}.md" -f $stem, $index)
        if (-not (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
        $index += 1
    }
}

function Get-RelativeChildPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Root,
        [Parameter(Mandatory = $true)]
        [string]$Child
    )
    $normalizedRoot = [System.IO.Path]::GetFullPath($Root).TrimEnd([char[]]"\/")
    $normalizedChild = [System.IO.Path]::GetFullPath($Child)
    if ($normalizedChild.StartsWith($normalizedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $normalizedChild.Substring($normalizedRoot.Length).TrimStart([char[]]"\/")
    }
    return [System.IO.Path]::GetFileName($normalizedChild)
}

$jobs = New-Object System.Collections.Generic.List[object]
$skipped = New-Object System.Collections.Generic.List[object]
$successes = New-Object System.Collections.Generic.List[object]
$failures = New-Object System.Collections.Generic.List[object]

try {
    $markitdownCommand = Get-MarkItDownCommand
    $markitdownVersion = (& $markitdownCommand --version 2>&1 | Out-String).Trim()
} catch {
    Write-ResultAndExit -ExitCode 2 -Summary ([pscustomobject]@{
        status = "environment_error"
        markitdown = $null
        markitdown_version = $null
        success_count = 0
        failure_count = 1
        skipped_count = 0
        successes = @()
        failures = @([pscustomobject]@{ source = $null; output = $null; error = $_.Exception.Message })
        skipped = @()
    })
}

foreach ($rawInput in $InputPath) {
    if ([System.Uri]::IsWellFormedUriString($rawInput, [System.UriKind]::Absolute)) {
        $skipped.Add([pscustomobject]@{ source = $rawInput; reason = "URLs are not accepted; download to a controlled local path first" })
        continue
    }
    if (-not (Test-Path -LiteralPath $rawInput)) {
        $skipped.Add([pscustomobject]@{ source = $rawInput; reason = "Path does not exist" })
        continue
    }

    $resolved = (Resolve-Path -LiteralPath $rawInput).Path
    $item = Get-Item -LiteralPath $resolved
    if ($item.PSIsContainer) {
        $targetRoot = if ($OutputDirectory) { [System.IO.Path]::GetFullPath($OutputDirectory) } else { Join-Path $item.FullName "markdown_output" }
        $files = @(Get-ChildItem -LiteralPath $item.FullName -File -Recurse:$Recurse | Where-Object { $supportedExtensions -contains $_.Extension.ToLowerInvariant() })
        foreach ($file in $files) {
            $relative = Get-RelativeChildPath -Root $item.FullName -Child $file.FullName
            $relativeMarkdown = [System.IO.Path]::ChangeExtension($relative, ".md")
            $jobs.Add([pscustomobject]@{ source = $file.FullName; desiredTarget = Join-Path $targetRoot $relativeMarkdown })
        }
        if ($files.Count -eq 0) {
            $skipped.Add([pscustomobject]@{ source = $item.FullName; reason = "No supported files were found in the directory" })
        }
        continue
    }

    if (-not ($supportedExtensions -contains $item.Extension.ToLowerInvariant())) {
        $skipped.Add([pscustomobject]@{ source = $item.FullName; reason = "File extension is not in the batch conversion allowlist" })
        continue
    }
    $targetRoot = if ($OutputDirectory) { [System.IO.Path]::GetFullPath($OutputDirectory) } else { $item.DirectoryName }
    $jobs.Add([pscustomobject]@{ source = $item.FullName; desiredTarget = Join-Path $targetRoot ($item.BaseName + ".md") })
}

if ($jobs.Count -eq 0) {
    Write-ResultAndExit -ExitCode 2 -Summary ([pscustomobject]@{
        status = "no_work"
        markitdown = $markitdownCommand
        markitdown_version = $markitdownVersion
        success_count = 0
        failure_count = 0
        skipped_count = $skipped.Count
        successes = @()
        failures = @()
        skipped = $skipped
    })
}

foreach ($job in $jobs) {
    $target = Get-UniqueTargetPath -DesiredPath $job.desiredTarget -AllowOverwrite:$Force
    $targetDirectory = Split-Path -Parent $target
    if (-not (Test-Path -LiteralPath $targetDirectory)) {
        New-Item -ItemType Directory -Path $targetDirectory -Force | Out-Null
    }
    $temp = Join-Path $targetDirectory (".{0}.{1}.tmp.md" -f [System.IO.Path]::GetFileNameWithoutExtension($target), [guid]::NewGuid().ToString("N"))
    $backup = Join-Path $targetDirectory (".{0}.{1}.bak.md" -f [System.IO.Path]::GetFileNameWithoutExtension($target), [guid]::NewGuid().ToString("N"))

    $arguments = @($job.source, "-o", $temp)
    if ($UsePlugins) { $arguments += "--use-plugins" }
    if ($KeepDataUris) { $arguments += "--keep-data-uris" }

    try {
        $output = & $markitdownCommand @arguments 2>&1
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0) {
            throw ("markitdown exited with code {0}: {1}" -f $exitCode, ($output -join [Environment]::NewLine))
        }
        if (-not (Test-Path -LiteralPath $temp)) { throw "The temporary Markdown file was not created" }
        $tempItem = Get-Item -LiteralPath $temp
        if ($tempItem.Length -le 0) { throw "The temporary Markdown file is empty" }

        if (Test-Path -LiteralPath $target) {
            if (-not $Force) { throw "Target exists and overwrite was not authorized" }
            [System.IO.File]::Replace($temp, $target, $backup, $true)
            if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force -ErrorAction SilentlyContinue }
        } else {
            [System.IO.File]::Move($temp, $target)
        }

        $targetItem = Get-Item -LiteralPath $target
        $successes.Add([pscustomobject]@{ source = $job.source; output = $targetItem.FullName; bytes = $targetItem.Length })
    } catch {
        if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force }
        if (Test-Path -LiteralPath $backup) {
            if (-not (Test-Path -LiteralPath $target)) {
                [System.IO.File]::Move($backup, $target)
            } else {
                Remove-Item -LiteralPath $backup -Force
            }
        }
        $failures.Add([pscustomobject]@{ source = $job.source; output = $target; error = $_.Exception.Message })
    }
}

$status = if ($failures.Count -eq 0 -and $skipped.Count -eq 0) { "ok" } elseif ($successes.Count -gt 0) { "partial" } else { "failed" }
$summary = [pscustomobject]@{
    status = $status
    markitdown = $markitdownCommand
    markitdown_version = $markitdownVersion
    success_count = $successes.Count
    failure_count = $failures.Count
    skipped_count = $skipped.Count
    successes = $successes
    failures = $failures
    skipped = $skipped
}

$exitCode = if ($status -eq "ok") { 0 } else { 1 }
Write-ResultAndExit -Summary $summary -ExitCode $exitCode
