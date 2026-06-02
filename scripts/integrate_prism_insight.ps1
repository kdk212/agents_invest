<#
.SYNOPSIS
    Import dragon1086/prism-insight into this repository under prism-insight/.

.DESCRIPTION
    This script uses a conservative subtree-style import. It keeps upstream
    PRISM-INSIGHT files under prism-insight/ so the optimization modules in the
    repository root remain separate and easy to wire in.

    Run from an English-only local path when possible, for example:
      C:\work\agents_invest

.NOTES
    This script does not enable live trading. It only imports upstream source.
#>

param(
    [string]$UpstreamUrl = "https://github.com/dragon1086/prism-insight.git",
    [string]$UpstreamBranch = "main",
    [string]$Prefix = "prism-insight"
)

$ErrorActionPreference = "Stop"

function Write-Step($Message) {
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Assert-GitRepo() {
    git rev-parse --show-toplevel *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "현재 폴더가 Git 저장소가 아닙니다. agents_invest 저장소 루트에서 실행하세요."
    }
}

function Assert-CleanEnough() {
    $status = git status --short
    if ($status) {
        Write-Host "현재 작업트리에 변경사항이 있습니다:" -ForegroundColor Yellow
        Write-Host $status
        throw "먼저 변경사항을 커밋하거나 별도 브랜치에서 정리한 뒤 다시 실행하세요."
    }
}

Assert-GitRepo
Assert-CleanEnough

Write-Step "Create integration branch"
$branchName = "integrate-prism-insight"
$currentBranch = git branch --show-current
if ($currentBranch -ne $branchName) {
    git checkout -B $branchName
}

Write-Step "Configure upstream remote"
$remotes = git remote
if ($remotes -notcontains "prism-upstream") {
    git remote add prism-upstream $UpstreamUrl
}

git fetch prism-upstream $UpstreamBranch

Write-Step "Import upstream into $Prefix/"
if (Test-Path -LiteralPath $Prefix) {
    throw "$Prefix 폴더가 이미 있습니다. 중복 병합을 막기 위해 중단합니다."
}

git read-tree --prefix="$Prefix/" -u "prism-upstream/$UpstreamBranch"

Write-Step "Stage imported upstream files"
git status --short

Write-Step "Commit import"
git commit -m "chore: import prism-insight upstream under $Prefix"

Write-Step "Run local checks"
python -m pip install -e ".[test]"
python -m pytest -q
python -m runtime.preflight --json

Write-Host ""
Write-Host "완료: PRISM-INSIGHT 원본이 $Prefix/ 하위 폴더로 병합되었습니다." -ForegroundColor Green
Write-Host "다음 단계: docs/UPSTREAM_MERGE_PLAYBOOK_ko.md의 6단계에 따라 trigger_batch.py와 stock_tracking_agent.py에 optimization 어댑터를 연결하세요."
