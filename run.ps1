param(
    [Parameter(Position = 0)]
    [string]$Command
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ContainerName = if ($env:P4SYMTEST_BENCH_CONTAINER) { $env:P4SYMTEST_BENCH_CONTAINER } else { "p4symtest-backend" }
$HostWorkspaceDir = Join-Path $RootDir "backend/workspace"
$HostOpenRequestFile = Join-Path $HostWorkspaceDir ".benchmark_open_requests"
$ContainerOpenRequestFile = "/app/workspace/.benchmark_open_requests"

function Show-Usage {
    @"
Usage:
  .\run.ps1 benchmark

Environment:
  P4SYMTEST_BENCH_CONTAINER   Override backend container name (default: p4symtest-backend)
"@
}

if ([string]::IsNullOrWhiteSpace($Command)) {
    Show-Usage
    exit 1
}

if ($Command -ne "benchmark") {
    Show-Usage
    exit 1
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Error: docker was not found in PATH."
    exit 1
}

$runningContainers = docker ps --format "{{.Names}}" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: failed to list running containers via docker ps."
    exit 1
}

$containerIsRunning = $runningContainers -split "`n" | Where-Object { $_ -eq $ContainerName }
if (-not $containerIsRunning) {
    Write-Host "Error: container '$ContainerName' is not running."
    Write-Host "Start it first with: docker compose up -d"
    exit 1
}

Write-Host "Preparing benchmark CLI inside container '$ContainerName'..."
docker exec $ContainerName sh -lc "test -f /app/benchmark_cli/run_benchmark_menu.py" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: /app/benchmark_cli/run_benchmark_menu.py was not found in the container."
    Write-Host "Check whether files exist under backend/benchmark_cli on the host."
    exit 1
}

if (-not (Test-Path -LiteralPath $HostWorkspaceDir -PathType Container)) {
    Write-Host "Error: workspace directory not found on host: $HostWorkspaceDir"
    exit 1
}

New-Item -ItemType File -Path $HostOpenRequestFile -Force | Out-Null
Clear-Content -Path $HostOpenRequestFile -ErrorAction SilentlyContinue

$watcherJob = Start-Job -ArgumentList $HostOpenRequestFile, $HostWorkspaceDir -ScriptBlock {
    param($OpenRequestFile, $WorkspaceDir)

    Get-Content -Path $OpenRequestFile -Tail 0 -Wait | ForEach-Object {
        $rawPath = $_.Trim()
        if (-not [string]::IsNullOrWhiteSpace($rawPath)) {
            $hostPath = $rawPath

            if ($rawPath.StartsWith("/app/workspace/")) {
                $relativePath = $rawPath.Substring("/app/workspace/".Length).Replace("/", [IO.Path]::DirectorySeparatorChar)
                $hostPath = Join-Path $WorkspaceDir $relativePath
            }

            if (Test-Path -LiteralPath $hostPath -PathType Leaf) {
                try {
                    Start-Process -FilePath $hostPath | Out-Null
                } catch {
                    # Ignore host open failures to keep benchmark flow running.
                }
            }
        }
    }
}

try {
    $dockerTtyArgs = @("-i")
    if (-not [Console]::IsInputRedirected -and -not [Console]::IsOutputRedirected) {
        $dockerTtyArgs = @("-it")
    }

    Write-Host "Opening interactive menu..."
    & docker exec @dockerTtyArgs -e "P4SYMTEST_OPEN_REQUEST_FILE=$ContainerOpenRequestFile" $ContainerName python3 /app/benchmark_cli/run_benchmark_menu.py
    exit $LASTEXITCODE
}
finally {
    if ($watcherJob) {
        Stop-Job -Job $watcherJob -ErrorAction SilentlyContinue | Out-Null
        Remove-Job -Job $watcherJob -ErrorAction SilentlyContinue | Out-Null
    }
}
