param(
    [string]$SourceBranch = "",
    [switch]$Push
)

$ErrorActionPreference = "Stop"

function Invoke-Git {
    param(
        [string]$RepositoryPath,
        [string[]]$CommandArgs
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & git -C $RepositoryPath @CommandArgs 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($exitCode -ne 0) {
        throw "git $($CommandArgs -join ' ') failed in $RepositoryPath.`n$output"
    }

    return @($output | ForEach-Object { "$_" })
}

$previewRoot = Split-Path -Parent $PSScriptRoot
$workspaceRoot = Split-Path -Parent $previewRoot

if (-not $SourceBranch) {
    $SourceBranch = (Invoke-Git -RepositoryPath $previewRoot -CommandArgs @("branch", "--show-current")).Trim()
}

$sourceStatus = (Invoke-Git -RepositoryPath $previewRoot -CommandArgs @("status", "--porcelain"))
if ($sourceStatus) {
    throw "CODE-preview has uncommitted changes. Commit or stash them before syncing."
}

$sourceGitPath = Join-Path $previewRoot ".git"
$sourceCommit = (Invoke-Git -RepositoryPath $previewRoot -CommandArgs @("rev-parse", "--short", "HEAD")).Trim()

$targets = @(
    @{ Name = "Footprints"; Path = (Join-Path $workspaceRoot "CODE"); Branch = "codex/footprints" },
    @{ Name = "Moments"; Path = (Join-Path $workspaceRoot "CODE-moments"); Branch = "codex/moments" },
    @{ Name = "Music"; Path = (Join-Path $workspaceRoot "CODE-music"); Branch = "codex/music" },
    @{ Name = "Books"; Path = (Join-Path $workspaceRoot "CODE-books"); Branch = "codex/books" },
    @{ Name = "Videos"; Path = (Join-Path $workspaceRoot "CODE-videos"); Branch = "codex/videos" },
    @{ Name = "Mobile"; Path = (Join-Path $workspaceRoot "CODE-mobile-polish"); Branch = "codex/mobile-polish" },
    @{ Name = "Refactor"; Path = (Join-Path $workspaceRoot "CODE-refactor-low-conflict"); Branch = "codex/refactor-low-conflict" }
)

Write-Host ""
Write-Host "Sync source:" -ForegroundColor Cyan
Write-Host "  Branch: $SourceBranch"
Write-Host "  Commit: $sourceCommit"

foreach ($target in $targets) {
    if (-not (Test-Path $target.Path)) {
        Write-Warning "$($target.Name) workspace is missing: $($target.Path)"
        continue
    }

    $targetStatus = (Invoke-Git -RepositoryPath $target.Path -CommandArgs @("status", "--porcelain"))
    if ($targetStatus) {
        throw "$($target.Name) has uncommitted changes. Clean it before syncing."
    }

    $currentBranch = (Invoke-Git -RepositoryPath $target.Path -CommandArgs @("branch", "--show-current")).Trim()
    if ($currentBranch -ne $target.Branch) {
        Invoke-Git -RepositoryPath $target.Path -CommandArgs @("switch", $target.Branch) | Out-Null
    }

    Invoke-Git -RepositoryPath $target.Path -CommandArgs @("fetch", $sourceGitPath, $SourceBranch) | Out-Null
    $mergeOutput = Invoke-Git -RepositoryPath $target.Path -CommandArgs @("merge", "--no-edit", "FETCH_HEAD")

    Write-Host ""
    Write-Host "$($target.Name) -> $($target.Branch)" -ForegroundColor Green
    if ($mergeOutput) {
        $mergeOutput | ForEach-Object { Write-Host "  $_" }
    } else {
        Write-Host "  Already up to date."
    }

    if ($Push) {
        Invoke-Git -RepositoryPath $target.Path -CommandArgs @("push", "origin", $target.Branch) | Out-Null
        Write-Host "  Pushed to origin." -ForegroundColor DarkGreen
    }
}

Write-Host ""
Write-Host "All module workspaces are now synced to $SourceBranch ($sourceCommit)." -ForegroundColor Cyan
