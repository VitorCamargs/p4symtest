# run_exhaustive_test_no_opt.ps1
# Script to execute the EXHAUSTIVE test for P4SymTest (NON-OPTIMIZED)
# Tests all possible paths through the pipeline without cache/deparser-merge optimizations

Write-Host "==================================" -ForegroundColor Blue
Write-Host "P4SymTest - Exhaustive Test (Full Pipeline - Non-Optimized)" -ForegroundColor Blue
Write-Host "==================================" -ForegroundColor Blue

# --- Configuration ---
$CONTAINER_NAME = "p4symtest-backend"
$TIMESTAMP = Get-Date -Format "yyyyMMdd_HHmmss"

$CONTAINER_BENCHMARK_DIR = "/app/benchmark_exhaustive"

# Required scripts
$LOCAL_SCRIPTS = @(
    ".\exhaustive_test_orchestrator_no_opt.py",
    ".\synthetic_p4_generator.py"
)

$CONTAINER_RESULTS_DIR = "/app/workspace/exhaustive_test_run"
$LOCAL_RESULTS_DIR = ".\exhaustive_results_no_opt_$TIMESTAMP"

# --- 1. Docker Check ---
Write-Host "`nChecking container..." -ForegroundColor Yellow
$containerRunning = docker ps --filter "name=$CONTAINER_NAME" --format "{{.Names}}" 2>$null
if (-not $containerRunning) {
    Write-Host "Error: Container $CONTAINER_NAME is not running!" -ForegroundColor Red
    Write-Host "Start Docker Compose first: docker-compose up -d" -ForegroundColor Yellow
    exit 1
}
Write-Host "(OK) Container found: $CONTAINER_NAME" -ForegroundColor Green

# --- 2. Container Preparation ---
Write-Host "`nPreparing environment in container..." -ForegroundColor Yellow
docker exec $CONTAINER_NAME mkdir -p $CONTAINER_BENCHMARK_DIR 2>$null

Write-Host "Copying benchmark scripts to the container..." -ForegroundColor Yellow
foreach ($script in $LOCAL_SCRIPTS) {
    if (-not (Test-Path $script)) {
        Write-Host "Error: File $script not found locally!" -ForegroundColor Red
        exit 1
    }
    docker cp $script ${CONTAINER_NAME}:${CONTAINER_BENCHMARK_DIR}/
}
Write-Host "(OK) Scripts copied to $CONTAINER_BENCHMARK_DIR" -ForegroundColor Green

# --- 3. Instalar Dependências ---
Write-Host "`nInstalando dependencias (pandas, matplotlib, psutil)..." -ForegroundColor Yellow
docker exec $CONTAINER_NAME pip install pandas numpy matplotlib seaborn psutil 2>&1 | Out-Null
Write-Host "(OK) Dependencias instaladas" -ForegroundColor Green

# --- 4. Clean previous results in container ---
Write-Host "`nCleaning previous results in container..." -ForegroundColor Yellow
docker exec $CONTAINER_NAME rm -rf $CONTAINER_RESULTS_DIR 2>$null
Write-Host "(OK) Container clean" -ForegroundColor Green

# --- 5. Execute Exhaustive Test ---
Write-Host "`n" + "="*50 -ForegroundColor Cyan
Write-Host "STARTING EXHAUSTIVE TEST (NON-OPTIMIZED)" -ForegroundColor Cyan
Write-Host "="*50 -ForegroundColor Cyan
Write-Host ""
Write-Host "This test will:" -ForegroundColor White
Write-Host "  1. Generate P4 programs with varied complexities" -ForegroundColor Gray
Write-Host "  2. Compile each program" -ForegroundColor Gray
Write-Host "  3. Execute the Parser" -ForegroundColor Gray
Write-Host "  4. Explore ALL pipeline paths" -ForegroundColor Gray
Write-Host "  5. Execute each table in each path" -ForegroundColor Gray
Write-Host "  6. Execute the Deparser" -ForegroundColor Gray
Write-Host "  7. Repeat 5x to collect statistics" -ForegroundColor Gray
Write-Host ""
Write-Host "This may take 10-20 minutes... Logs will appear below." -ForegroundColor Yellow
Write-Host ""

$PYTHON_COMMAND = "python3"
$SCRIPT_NAME = "exhaustive_test_orchestrator_no_opt.py"

# Execute with real-time output
Write-Host "Running exhaustive test..." -ForegroundColor Cyan
docker exec --workdir $CONTAINER_BENCHMARK_DIR $CONTAINER_NAME $PYTHON_COMMAND $SCRIPT_NAME

if ($LASTEXITCODE -ne 0) {
    Write-Host "`nError running the exhaustive test!" -ForegroundColor Red
    Write-Host "Check the error logs above." -ForegroundColor Yellow
    exit 1
}

Write-Host "`n(OK) Exhaustive test finished in container." -ForegroundColor Green

# --- 6. Copy Results ---
Write-Host "`nCopying results from $CONTAINER_RESULTS_DIR..." -ForegroundColor Yellow

# Create local directory
New-Item -ItemType Directory -Force -Path $LOCAL_RESULTS_DIR | Out-Null

# *** LOGIC FIX: Define the $analysisDir variable ***
$analysisDir = Join-Path $LOCAL_RESULTS_DIR "analysis"

# Copy all results
# docker cp ${CONTAINER_NAME}:${CONTAINER_RESULTS_DIR}/. $LOCAL_RESULTS_DIR

# if ($LASTEXITCODE -eq 0) {
#     Write-Host "(OK) Results copied to: $LOCAL_RESULTS_DIR" -ForegroundColor Green
# } else {
#     Write-Host "Warning: Some files may not have been copied" -ForegroundColor Yellow
# }

# --- 7. Final Report ---
Write-Host "`n" + "="*70 -ForegroundColor Blue
Write-Host "EXHAUSTIVE TEST COMPLETE!" -ForegroundColor Green
Write-Host "="*70 -ForegroundColor Blue

Write-Host "`nResults saved in:" -ForegroundColor Cyan
Write-Host "  $LOCAL_RESULTS_DIR" -ForegroundColor White

Write-Host "`nAvailable files:" -ForegroundColor Cyan
Write-Host "   (Folder) synthetic_p4s/     - Generated P4 programs" -ForegroundColor Gray
Write-Host "   (Folder) analysis/          - CSVs and charts" -ForegroundColor Gray
Write-Host "   (File)   *.pdf              - Analysis charts" -ForegroundColor Gray

Write-Host "`nTo view results:" -ForegroundColor Yellow
Write-Host "  cd $analysisDir" -ForegroundColor White
Write-Host "  start *.pdf" -ForegroundColor White

Write-Host "`nTo view raw data:" -ForegroundColor Yellow
Write-Host "  cd $analysisDir" -ForegroundColor White
Write-Host "  start exhaustive_test_raw.csv" -ForegroundColor White

# --- 8. Quick Statistics ---
Write-Host "`n" + "-"*70 -ForegroundColor Gray
Write-Host "QUICK STATISTICS" -ForegroundColor Cyan
Write-Host "-"*70 -ForegroundColor Gray

$rawCsv = Join-Path $analysisDir "exhaustive_test_raw.csv"
if (Test-Path $rawCsv) {
    try {
        $data = Import-Csv $rawCsv
        $totalRuns = $data.Count
        $successRuns = ($data | Where-Object { $_.success -eq "True" }).Count
        $avgTotalTime = ($data | Where-Object { $_.success -eq "True" } | Measure-Object -Property total_time_s -Average).Average
        $maxPaths = ($data | Measure-Object -Property total_paths -Maximum).Maximum
        
        Write-Host "Total runs: $totalRuns" -ForegroundColor White
        Write-Host "Successful runs: $successRuns" -ForegroundColor Green
        Write-Host "Average total time: $([math]::Round($avgTotalTime, 2))s" -ForegroundColor White
        Write-Host "Max paths explored: $maxPaths" -ForegroundColor White
    } catch {
        Write-Host "Could not calculate quick statistics" -ForegroundColor Yellow
    }
}
