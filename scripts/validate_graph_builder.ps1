# scripts/validate_graph_builder.ps1
#
# Validates PythonAstGraphBuilder against a real repository: node/edge
# counts, graph integrity checks, parse timing. Wraps
# scripts/validate_graph_builder.py, run inside the api container
# (where app.* and its dependencies are importable).
#
# IMPORTANT: rebuild/restart the api container first if you haven't
# already, so the new docker-compose.yml volume mounts (scripts/, data/)
# take effect:
#   docker compose -f docker/docker-compose.yml up -d
#
# Usage:
#   .\scripts\validate_graph_builder.ps1 -Repo psf/requests
#   .\scripts\validate_graph_builder.ps1 -Repo octocat/Hello-World -Branch master
#   .\scripts\validate_graph_builder.ps1 -LocalClone https://github.com/psf/requests
#   .\scripts\validate_graph_builder.ps1 -LocalPath data/requests   # already cloned into ./data

param(
    [string]$Repo,
    [string]$Branch = "main",
    [string]$LocalClone,
    [string]$LocalPath,
    [string]$ComposeFile = "docker/docker-compose.yml"
)

function Test-DockerRunning {
    $status = docker compose -f $ComposeFile ps --format json 2>$null
    if (-not $status) {
        Write-Host "Stack doesn't appear to be running. Start it first:" -ForegroundColor Red
        Write-Host "  docker compose -f $ComposeFile up -d" -ForegroundColor Yellow
        exit 1
    }
}

Test-DockerRunning

if ($Repo) {
    Write-Host "Fetching '$Repo' via GitHub API (rate-limited to 60 req/hour, one request per file)." -ForegroundColor Yellow
    Write-Host "For a large repo, consider -LocalClone instead to avoid the rate limit.`n" -ForegroundColor Yellow
    docker compose -f $ComposeFile exec api python scripts/validate_graph_builder.py --repo $Repo --branch $Branch
}
elseif ($LocalClone) {
    $repoName = ($LocalClone -split '/')[-1] -replace '\.git$', ''
    $cloneTarget = "data/$repoName"

    if (-not (Test-Path $cloneTarget)) {
        Write-Host "Cloning $LocalClone into ./$cloneTarget ..." -ForegroundColor Cyan
        git clone --depth 1 $LocalClone $cloneTarget
        if ($LASTEXITCODE -ne 0) {
            Write-Host "git clone failed -- is git installed and on PATH?" -ForegroundColor Red
            exit 1
        }
    }
    else {
        Write-Host "Using existing clone at ./$cloneTarget (delete it to re-clone)" -ForegroundColor Cyan
    }

    docker compose -f $ComposeFile exec api python scripts/validate_graph_builder.py --local-path /app/$cloneTarget
}
elseif ($LocalPath) {
    docker compose -f $ComposeFile exec api python scripts/validate_graph_builder.py --local-path /app/$LocalPath
}
else {
    Write-Host "Specify one of -Repo, -LocalClone, or -LocalPath. See script header for examples." -ForegroundColor Red
    exit 1
}