# watch-jobs.ps1 - picks up job files from the repo and runs them with Claude Code.
# Pulls for free every few minutes. Spends API money only after you type y at the prompt.
# Usage: pwsh -File ops\watch-jobs.ps1   (run from the repo root)

param(
    [int]$IntervalSeconds = 180,
    [double]$DefaultBudgetUsd = 2.00,
    [int]$MaxTurns = 60
)

$ErrorActionPreference = "Stop"
$repo     = (Resolve-Path "$PSScriptRoot\..").Path
$jobsDir  = Join-Path $repo "ops\jobs"
$doneDir  = Join-Path $repo "ops\results"
$logDir   = Join-Path $repo "ops\logs"
New-Item -ItemType Directory -Force -Path $jobsDir, $doneDir, $logDir | Out-Null
Set-Location $repo

Write-Host "Watching $jobsDir every $IntervalSeconds s. Ctrl+C to stop."

while ($true) {
    git pull --ff-only --quiet 2>$null
    if ($LASTEXITCODE -ne 0) { Write-Warning "git pull failed; will retry next loop." }

    $pending = Get-ChildItem $jobsDir -Filter "*.md" | Sort-Object Name | Where-Object {
        -not (Test-Path (Join-Path $doneDir $_.Name)) -and
        -not (Test-Path (Join-Path $logDir ($_.BaseName + ".skipped")))
    }

    foreach ($job in $pending) {
        $text   = Get-Content $job.FullName -Raw
        $title  = ($text -split "`n" | Where-Object { $_ -match '^#\s' } | Select-Object -First 1) -replace '^#\s*', ''
        $budget = $DefaultBudgetUsd
        if ($text -match '(?im)^Budget:\s*\$?([0-9]+(\.[0-9]+)?)') { $budget = [double]$Matches[1] }
        $usesApi = $text -match '(?im)^Anthropic API:\s*yes'

        Write-Host ""
        Write-Host "New job: $($job.Name)  $title"
        Write-Host "Claude Code budget cap: `$$budget   Calls the Anthropic API for critters: $usesApi"
        $answer = Read-Host "Run it? (y = run, s = skip for good, anything else = ask again later)"

        if ($answer -eq 's') { New-Item -ItemType File -Path (Join-Path $logDir ($job.BaseName + ".skipped")) | Out-Null; continue }
        if ($answer -ne 'y') { continue }

        $resultPath = Join-Path $doneDir $job.Name
        $prompt = @"
$text

When you finish, write your summary to $resultPath (markdown, under 400 words).
Do not commit or push anything yourself. The watcher commits only the results file.
"@
        $log = Join-Path $logDir ($job.BaseName + ".log")
        claude -p $prompt --max-turns $MaxTurns --max-budget-usd $budget `
            --allowedTools "Read" "Edit" "Write" "Bash" 2>&1 | Tee-Object -FilePath $log

        if (-not (Test-Path $resultPath)) {
            "Job ended without writing a result. See ops/logs/$($job.BaseName).log on Yggdrasil." | Set-Content $resultPath
        }
        git add -- $resultPath
        git commit -m "Result for $($job.BaseName)" --quiet
        # New jobs may have landed while this one ran, so rebase before pushing.
        git pull --rebase --quiet 2>$null
        git push --quiet
        if ($LASTEXITCODE -ne 0) { Write-Warning "git push failed; the result is committed locally. Push it by hand." }
        Write-Host "Pushed result for $($job.Name)."
    }

    Start-Sleep -Seconds $IntervalSeconds
}
