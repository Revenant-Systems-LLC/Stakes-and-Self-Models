# watch-jobs.ps1 - picks up job files from the repo and runs them with Claude Code.
# Usage: pwsh -File ops\watch-jobs.ps1   (run from the repo root)
#
# Auto-run rule (set by David, Nov 25 2026): a job runs without asking when
#   - it says "Anthropic API: no", and
#   - its "Budget: $X" is $5 or less, and
#   - today's auto-run spend plus that budget stays at $25 or less.
# Anything else waits for y at the prompt.
# Total cap: no job starts if all logged Claude Code job spend plus its budget
# would pass $100 (-TotalCapUsd).
#
# Nothing here should look frozen: every Claude Code step prints as it happens,
# a heartbeat prints at least every 30 seconds while a job runs, and the idle
# loop says when it will check next.
#
# Spend per day is kept in ops/logs/spend-YYYY-MM-DD.txt (gitignored). Each job's
# cost is total_cost_usd from Claude Code's final result event. If that can't be
# read (crash, Ctrl+C), the job's full budget cap is counted instead.
#
# A job may ask for code to be committed with "Commit code: yes" and a
# "## Commit paths" section listing paths under world/, runner/ or viewer/
# (.gitignore is also allowed). Nothing under ops/logs, no .env or key files,
# and nothing .gitignore excludes ever gets committed.

param(
    [int]$IntervalSeconds = 60,
    [int]$HeartbeatSeconds = 30,
    [double]$DefaultBudgetUsd = 2.00,
    [int]$MaxTurns = 100,
    [double]$AutoJobCapUsd = 5.00,
    [double]$AutoDayCapUsd = 25.00,
    [string]$DefaultModel = "sonnet",
    [double]$TotalCapUsd = 100.00
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$repo     = (Resolve-Path "$PSScriptRoot\..").Path
$jobsDir  = Join-Path $repo "ops\jobs"
$doneDir  = Join-Path $repo "ops\results"
$logDir   = Join-Path $repo "ops\logs"
New-Item -ItemType Directory -Force -Path $jobsDir, $doneDir, $logDir | Out-Null
Set-Location $repo

$CommitPrefixes = @('world/', 'runner/', 'viewer/')
$BlockedPatterns = @('^ops/logs/', '\.env$', '(^|/)secrets/', '(^|/)keys/', '\.key$', '\.pem$', '(^|/)config\.local\.')
$SecretRegex = 'sk-ant-[A-Za-z0-9_\-]{10,}|ANTHROPIC_API_KEY\s*[=:]\s*["'']?[A-Za-z0-9_\-]{10,}|hf_[A-Za-z0-9]{30,}'

function Get-SpendFile { Join-Path $logDir ("spend-" + (Get-Date -Format "yyyy-MM-dd") + ".txt") }

# Lines look like: 14:05:22<TAB>004-world-engine<TAB>auto<TAB>1.2345
function Get-SpendToday([string]$mode) {
    $f = Get-SpendFile
    if (-not (Test-Path $f)) { return 0.0 }
    $sum = 0.0
    foreach ($line in Get-Content $f) {
        $parts = $line -split "`t"
        if ($parts.Count -ge 4 -and ($mode -eq 'all' -or $parts[2] -eq $mode)) { $sum += [double]$parts[3] }
    }
    return $sum
}

# All Claude Code job spend this watcher has logged, every day and mode.
# Spend from before Nov 26 2026 (jobs 003b and 004) isn't in these files.
function Get-SpendTotal {
    $sum = 0.0
    foreach ($f in Get-ChildItem -Path $logDir -Filter "spend-*.txt" -ErrorAction SilentlyContinue) {
        foreach ($line in Get-Content $f.FullName) {
            $parts = $line -split "`t"
            if ($parts.Count -ge 4) { $sum += [double]$parts[3] }
        }
    }
    return $sum
}

function Add-Spend([string]$job, [string]$mode, [double]$cost) {
    $line = "{0}`t{1}`t{2}`t{3:0.0000}" -f (Get-Date -Format "HH:mm:ss"), $job, $mode, $cost
    Add-Content -Path (Get-SpendFile) -Value $line
}

function Format-Elapsed([TimeSpan]$t) { "{0}m{1:00}s" -f [int][Math]::Floor($t.TotalMinutes), $t.Seconds }

function Get-Preview($tool) {
    $i = $tool.input
    $p = $null
    if ($i) {
        foreach ($k in 'command', 'file_path', 'path', 'pattern', 'description', 'url', 'prompt') {
            if ($i.PSObject.Properties.Name -contains $k -and $i.$k) { $p = [string]$i.$k; break }
        }
        if (-not $p) { $p = ($i | ConvertTo-Json -Compress -Depth 3) }
    }
    if (-not $p) { $p = "" }
    $p = ($p -replace '\s+', ' ').Trim()
    if ($p.Length -gt 140) { $p = $p.Substring(0, 140) + "..." }
    return $p
}

# Prints one stream-json event and updates the job state.
function Show-Event([string]$line, $state) {
    $ev = $null
    try { $ev = $line | ConvertFrom-Json -ErrorAction Stop } catch { $ev = $null }
    if (-not $ev) {
        if ($line.Trim()) { Write-Host "  $line" -ForegroundColor DarkGray }
        return
    }
    switch ($ev.type) {
        'system' {
            if ($ev.subtype -eq 'init') { Write-Host "  model: $($ev.model)" -ForegroundColor DarkGray }
            elseif ($ev.subtype -eq 'api_retry') { Write-Host "  API retry $($ev.attempt): $($ev.error)" -ForegroundColor Yellow }
        }
        'assistant' {
            foreach ($b in @($ev.message.content)) {
                if ($b.type -eq 'text' -and $b.text) {
                    Write-Host $b.text
                    $t = ($b.text -replace '\s+', ' ').Trim()
                    if ($t.Length -gt 80) { $t = $t.Substring(0, 80) + "..." }
                    $state.Last = "said: $t"
                }
                elseif ($b.type -eq 'tool_use') {
                    $state.Tools++
                    $state.Last = "{0}: {1}" -f $b.name, (Get-Preview $b)
                    Write-Host ("  > " + $state.Last) -ForegroundColor Cyan
                }
            }
        }
        'user' {
            foreach ($b in @($ev.message.content)) {
                if ($b.type -eq 'tool_result' -and $b.is_error) { Write-Host "  ! tool error" -ForegroundColor Yellow }
            }
        }
        'result' {
            if ($null -ne $ev.total_cost_usd) { $state.Cost = [double]$ev.total_cost_usd }
            $state.ResultText = [string]$ev.result
            Write-Host ("  finished: {0}, {1} turns, cost `${2}" -f $ev.subtype, $ev.num_turns, $ev.total_cost_usd) -ForegroundColor Green
        }
    }
}

# Runs one job in a background PowerShell job, tails its output file, prints every
# step and a heartbeat. Returns the state (Cost, ResultText, Tools).
function Invoke-Job($job, [string]$fullPrompt, [double]$budget, [int]$turns, [string]$model) {
    $log        = Join-Path $logDir ($job.BaseName + ".log")
    $promptFile = Join-Path $logDir ($job.BaseName + ".prompt.md")
    Set-Content -Path $promptFile -Value $fullPrompt -Encoding utf8
    if (Test-Path $log) { Remove-Item $log }
    New-Item -ItemType File -Path $log | Out-Null
    $shortPrompt = "Your full instructions for this job are in the file $promptFile. Read that whole file first, then do exactly what it says."

    $state = [pscustomobject]@{ Cost = $null; ResultText = $null; Tools = 0; Last = "starting" }
    $start = Get-Date
    $bg = Start-Job -ArgumentList $repo, $shortPrompt, $turns, $budget, $log, $model -ScriptBlock {
        param($repo, $prompt, $turns, $budget, $log, $model)
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        Set-Location $repo
        & claude -p $prompt --model $model --max-turns $turns --max-budget-usd $budget `
            --output-format stream-json --verbose `
            --allowedTools "Read" "Edit" "Write" "Bash" 2>&1 | ForEach-Object {
            Add-Content -Path $log -Value "$_" -Encoding utf8
        }
    }

    $fs = [System.IO.FileStream]::new($log, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete)
    $reader = [System.IO.StreamReader]::new($fs, [System.Text.Encoding]::UTF8)
    $buf = ""
    $lastBeat = Get-Date
    try {
        while ($true) {
            $done = "$($bg.State)" -in @('Completed', 'Failed', 'Stopped')
            $chunk = $reader.ReadToEnd()
            if ($chunk) {
                $buf += $chunk
                $parts = $buf -split "`r?`n"
                $buf = $parts[-1]
                if ($parts.Count -gt 1) {
                    foreach ($l in $parts[0..($parts.Count - 2)]) { if ($l) { Show-Event $l $state } }
                }
            }
            if ($done) {
                if ($buf.Trim()) { Show-Event $buf $state }
                break
            }
            if (((Get-Date) - $lastBeat).TotalSeconds -ge $HeartbeatSeconds) {
                Write-Host ("  ... {0} still running, {1} elapsed, {2} tool calls, last: {3}" -f $job.BaseName, (Format-Elapsed ((Get-Date) - $start)), $state.Tools, $state.Last) -ForegroundColor DarkYellow
                $lastBeat = Get-Date
            }
            Start-Sleep -Milliseconds 1000
        }
        if ("$($bg.State)" -eq 'Failed') {
            $err = Receive-Job $bg -ErrorAction SilentlyContinue 2>&1 | Out-String
            Write-Warning "Claude Code run failed to start or crashed. $err"
        }
    }
    finally {
        $reader.Close()
        if ("$($bg.State)" -eq 'Running') { Stop-Job $bg }
        Remove-Job $bg -Force -ErrorAction SilentlyContinue
        if ($null -eq $state.Cost) {
            Write-Warning "Couldn't read the job's cost. Counting the full `$$budget cap."
            $state.Cost = $budget
        }
    }
    Write-Host ("  {0} took {1}" -f $job.BaseName, (Format-Elapsed ((Get-Date) - $start))) -ForegroundColor Green
    return $state
}

function Get-CommitPaths([string]$text) {
    $paths = @()
    $inSection = $false
    foreach ($line in ($text -split "`r?`n")) {
        if ($line -match '^##\s+Commit paths') { $inSection = $true; continue }
        if ($inSection -and $line -match '^#') { break }
        if ($inSection -and $line -match '^\s*[-*]\s+`?([^`\s]+)`?') {
            $p = ($Matches[1] -replace '\\', '/')
            if ($p.StartsWith('./')) { $p = $p.Substring(2) }
            $okPrefix = ($CommitPrefixes | Where-Object { $p.StartsWith($_) }).Count -gt 0
            if ($p -notmatch '\.\.' -and ($okPrefix -or $p -eq '.gitignore')) { $paths += $p }
            else { Write-Warning "Ignoring commit path outside world/, runner/, viewer/: $p" }
        }
    }
    return $paths
}

function Sync-Repo {
    git pull --rebase --autostash --quiet 2>$null
    if ($LASTEXITCODE -ne 0) { Write-Warning "git pull failed; will retry next loop."; return }
    # Push any result that an earlier push failed to send.
    $ahead = git rev-list --count '@{u}..HEAD' 2>$null
    if ($LASTEXITCODE -eq 0 -and [int]$ahead -gt 0) {
        git push --quiet
        if ($LASTEXITCODE -eq 0) { Write-Host "Pushed $ahead waiting commit(s)." }
    }
}

Write-Host "Watching $jobsDir every $IntervalSeconds s. Ctrl+C to stop."
Write-Host ("Auto-run: Anthropic API no, budget <= `${0}, day total <= `${1}. Auto spend today so far: `${2:0.00}" -f $AutoJobCapUsd, $AutoDayCapUsd, (Get-SpendToday 'auto'))

while ($true) {
    Sync-Repo

    $pending = Get-ChildItem $jobsDir -Filter "*.md" | Sort-Object Name | Where-Object {
        -not (Test-Path (Join-Path $doneDir $_.Name)) -and
        -not (Test-Path (Join-Path $logDir ($_.BaseName + ".skipped")))
    }

    foreach ($job in $pending) {
        $text   = Get-Content $job.FullName -Raw
        $title  = ($text -split "`n" | Where-Object { $_ -match '^#\s' } | Select-Object -First 1) -replace '^#\s*', ''
        $budget = $DefaultBudgetUsd
        if ($text -match '(?im)^Budget:\s*\$?([0-9]+(\.[0-9]+)?)') { $budget = [double]$Matches[1] }
        $model = $DefaultModel
        if ($text -match '(?im)^Model:\s*([A-Za-z0-9._\-\[\]]+)') { $model = $Matches[1].ToLower() }
        $turns = $MaxTurns
        if ($text -match '(?im)^Max turns:\s*([0-9]+)') { $turns = [int]$Matches[1] }
        # Only an explicit "Anthropic API: no" counts as no.
        $apiNo = $text -match '(?im)^Anthropic API:\s*no\b'
        $commitCode = $text -match '(?im)^Commit code:\s*yes'
        $commitPaths = @()
        if ($commitCode) { $commitPaths = @(Get-CommitPaths $text) }

        $autoSpent = Get-SpendToday 'auto'
        $totalSpent = Get-SpendTotal
        if (($totalSpent + $budget) -gt $TotalCapUsd) {
            Write-Host ""
            Write-Host ("Not starting {0}: Claude Code job spend so far is `${1:0.00}, and its `${2} budget would pass the `${3} total cap. Waiting." -f $job.Name, $totalSpent, $budget, $TotalCapUsd) -ForegroundColor Yellow
            continue
        }
        $auto = $apiNo -and ($budget -le $AutoJobCapUsd) -and (($autoSpent + $budget) -le $AutoDayCapUsd)

        Write-Host ""
        Write-Host "New job: $($job.Name)  $title"
        Write-Host ("Model: {3}   Claude Code budget cap: `${0}   Calls the Anthropic API for critters: {1}   Auto spend today: `${2:0.00}   All jobs so far: `${4:0.00} of `${5}" -f $budget, (-not $apiNo), $autoSpent, $model, $totalSpent, $TotalCapUsd)

        if ($auto) {
            $mode = 'auto'
            Write-Host "Inside the auto-run rule. Running without asking." -ForegroundColor Green
        }
        else {
            $why = @()
            if (-not $apiNo) { $why += "it calls the Anthropic API for critters" }
            if ($budget -gt $AutoJobCapUsd) { $why += "its budget is over `$$AutoJobCapUsd" }
            elseif (($autoSpent + $budget) -gt $AutoDayCapUsd) { $why += "it would take today past `$$AutoDayCapUsd" }
            Write-Host ("Needs your yes because " + ($why -join " and ") + ".") -ForegroundColor Yellow
            $answer = Read-Host "Run it? (y = run, s = skip for good, anything else = ask again later)"
            if ($answer -eq 's') { New-Item -ItemType File -Path (Join-Path $logDir ($job.BaseName + ".skipped")) | Out-Null; continue }
            if ($answer -ne 'y') { continue }
            $mode = 'manual'
        }

        $resultPath = Join-Path $doneDir $job.Name
        $commitLine = "Do not commit or push anything yourself. The watcher commits only the results file."
        if ($commitPaths.Count -gt 0) {
            $commitLine = "Do not commit or push anything yourself. After you finish, the watcher commits the results file and these paths: " + ($commitPaths -join ", ") + ". Never put API keys or secrets in those paths."
        }
        $prompt = @"
$text

When you finish, write your summary to $resultPath (markdown, under 400 words).
$commitLine
"@

        Write-Host ("Started {0} on {2} at {1}" -f $job.Name, (Get-Date -Format "HH:mm:ss"), $model) -ForegroundColor Green
        $cost = $budget
        $state = $null
        try {
            $state = Invoke-Job $job $prompt $budget $turns $model
            $cost = $state.Cost
        }
        finally {
            Add-Spend $job.BaseName $mode $cost
        }
        Write-Host ("Done {0} at {1}. Cost `${2:0.00}. Auto spend today: `${3:0.00}" -f $job.Name, (Get-Date -Format "HH:mm:ss"), $cost, (Get-SpendToday 'auto')) -ForegroundColor Green

        if (-not (Test-Path $resultPath)) {
            $fallback = "Job ended without writing a result. See ops/logs/$($job.BaseName).log on Yggdrasil."
            if ($state -and $state.ResultText) { $fallback += "`n`nClaude Code's last message:`n`n" + $state.ResultText }
            $fallback | Set-Content $resultPath
        }

        git add -- $resultPath
        $committedCode = $false
        if ($commitPaths.Count -gt 0) {
            foreach ($p in $commitPaths) {
                if (Test-Path (Join-Path $repo $p)) { git add -- $p 2>$null }
                else { Write-Warning "Commit path not found, skipped: $p" }
            }
            $resultRel = "ops/results/" + $job.Name
            # Unstage anything outside the allowed paths or matching a blocked pattern.
            foreach ($f in @(git diff --cached --name-only)) {
                $allowed = ($f -eq $resultRel) -or ($f -eq '.gitignore') -or (($CommitPrefixes | Where-Object { $f.StartsWith($_) }).Count -gt 0)
                $blocked = ($BlockedPatterns | Where-Object { $f -match $_ }).Count -gt 0
                if ((-not $allowed) -or $blocked) { git reset -q -- $f; Write-Warning "Left out of the commit: $f" }
            }
            $hits = git diff --cached -U0 | Select-String -Pattern $SecretRegex
            if ($hits) {
                Write-Warning "Something that looks like a key is in the staged code. Committing only the result."
                git reset -q
                Add-Content -Path $resultPath -Value "`nWatcher: code was not committed because something that looks like an API key was in it. Check by hand."
                git add -- $resultPath
            }
            else { $committedCode = $true }
        }

        $msg = "Result for $($job.BaseName)"
        if ($committedCode) { $msg += " with code" }
        git commit -m $msg --quiet
        # New jobs may have landed while this one ran, so rebase before pushing.
        git pull --rebase --autostash --quiet 2>$null
        git push --quiet
        if ($LASTEXITCODE -ne 0) { Write-Warning "git push failed; the result is committed locally. The next loop tries again." }
        else { Write-Host "Pushed result for $($job.Name)." }
    }

    Write-Host ("[{0}] Waiting for jobs, next check in {1}s." -f (Get-Date -Format "HH:mm:ss"), $IntervalSeconds) -ForegroundColor DarkGray
    Start-Sleep -Seconds $IntervalSeconds
}
