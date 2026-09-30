#!/usr/bin/env pwsh
# create-test-issues.ps1
# Batch-creates all manual test case issues in GitHub using the gh CLI.
#
# Usage:
#   1. Make sure you're authenticated:  gh auth login
#   2. Run from the repo root:          .\issues\create-test-issues.ps1
#   3. Optionally target a specific repo: .\issues\create-test-issues.ps1 -Repo "factored-ai-hackathon/factored-hackathon-2026"

param(
    [string]$Repo = ""
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Build the repo flag if provided
$repoFlag = @()
if ($Repo -ne "") {
    $repoFlag = @("--repo", $Repo)
}

# Define all issues: Title, Labels, Body file
$issues = @(
    @{
        Title  = "[UC1-TC1] FAQ answered without authentication"
        Labels = "eval,manual-test,uc-faq"
        File   = "uc1-tc1.md"
    },
    @{
        Title  = "[UC1-TC2] Out-of-KB question triggers honest fallback"
        Labels = "eval,manual-test,uc-faq"
        File   = "uc1-tc2.md"
    },
    @{
        Title  = "[UC2-TC1] Balance query enforces full authentication"
        Labels = "eval,manual-test,uc-auth"
        File   = "uc2-tc1.md"
    },
    @{
        Title  = "[UC2-TC2] Pending intent resumes correctly after auth"
        Labels = "eval,manual-test,uc-auth"
        File   = "uc2-tc2.md"
    },
    @{
        Title  = "[UC3-TC1] Credit request auto-approved"
        Labels = "eval,manual-test,uc-credit"
        File   = "uc3-tc1.md"
    },
    @{
        Title  = "[UC4-TC1] Credit request auto-rejected"
        Labels = "eval,manual-test,uc-credit"
        File   = "uc4-tc1.md"
    },
    @{
        Title  = "[UC5-TC1] Credit request lands in grey-band review"
        Labels = "eval,manual-test,uc-credit"
        File   = "uc5-tc1.md"
    },
    @{
        Title  = "[UC6-TC1] Failed authentication locks the session"
        Labels = "eval,manual-test,uc-auth,uc-security"
        File   = "uc6-tc1.md"
    },
    @{
        Title  = "[UC7-TC1] Explicit request for a human agent"
        Labels = "eval,manual-test,uc-escalation"
        File   = "uc7-tc1.md"
    },
    @{
        Title  = "[UC7-TC2] Fraud / lost card report"
        Labels = "eval,manual-test,uc-escalation"
        File   = "uc7-tc2.md"
    },
    @{
        Title  = "[UC8-TC1] Prompt injection attempt to leak another customer's data"
        Labels = "eval,manual-test,uc-security"
        File   = "uc8-tc1.md"
    },
    @{
        Title  = "[UC8-TC2] Verified user requests another customer's data"
        Labels = "eval,manual-test,uc-security"
        File   = "uc8-tc2.md"
    },
    @{
        Title  = "[ESC-TC1] Escalation on low-confidence streak (blocked)"
        Labels = "eval,manual-test,uc-escalation,blocked"
        File   = "esc-tc1.md"
    },
    @{
        Title  = "[ESC-TC2] Escalation on negative sentiment (blocked)"
        Labels = "eval,manual-test,uc-escalation,blocked"
        File   = "esc-tc2.md"
    }
)

Write-Host "`n=== Creating $($issues.Count) test case issues ===`n" -ForegroundColor Cyan

$created = 0
$failed  = 0

foreach ($issue in $issues) {
    $bodyFile = Join-Path $scriptDir $issue.File

    if (-not (Test-Path $bodyFile)) {
        Write-Host "[SKIP] $($issue.Title) — body file not found: $bodyFile" -ForegroundColor Yellow
        $failed++
        continue
    }

    Write-Host "[CREATE] $($issue.Title)" -ForegroundColor White -NoNewline

    try {
        $result = gh issue create `
            @repoFlag `
            --title $issue.Title `
            --label $issue.Labels `
            --body-file $bodyFile

        Write-Host " -> $result" -ForegroundColor Green
        $created++
    }
    catch {
        Write-Host " -> FAILED: $_" -ForegroundColor Red
        $failed++
    }

    # Small delay to avoid rate limiting
    Start-Sleep -Milliseconds 500
}

Write-Host "`n=== Done: $created created, $failed failed ===" -ForegroundColor Cyan
