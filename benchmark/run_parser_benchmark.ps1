# run_parser_benchmark.ps1
# Script para executar o benchmark ISOLADO DO PARSER (usando o gerador P4 existente)

Write-Host "==================================" -ForegroundColor Blue
Write-Host "P4SymTest - Benchmark (Parser Isolado)" -ForegroundColor Blue
Write-Host "==================================" -ForegroundColor Blue

# --- Configuração ---
$CONTAINER_NAME = "p4symtest-backend"
$TIMESTAMP = Get-Date -Format "yyyyMMdd_HHmmss"

$CONTAINER_BENCHMARK_DIR = "/app/benchmark_parser_test"

$LOCAL_SCRIPTS = @(
    ".\parser_test_orchestrator.py",    # O orquestrador
    ".\synthetic_p4_generator.py",    # O gerador P4
    ".\benchmark_analyzer.py"         # O analisador
)

$CONTAINER_RESULTS_DIR = "/app/workspace/parser_benchmark_run"
$LOCAL_RESULTS_DIR = ".\parser_results_$TIMESTAMP"

# --- 1. Verificação do Docker ---
Write-Host "`nVerificando container..." -ForegroundColor Yellow
$containerRunning = docker ps --filter "name=$CONTAINER_NAME" --format "{{.Names}}" 2>$null
if (-not $containerRunning) {
    Write-Host "Erro: Container $CONTAINER_NAME nao esta rodando!" -ForegroundColor Red
    Write-Host "Inicie o Docker Compose primeiro: docker-compose up -d" -ForegroundColor Yellow
    exit 1
}
Write-Host "(OK) Container encontrado: $CONTAINER_NAME" -ForegroundColor Green

# --- 2. Preparação no Container ---
Write-Host "`nPreparando ambiente no container..." -ForegroundColor Yellow
docker exec $CONTAINER_NAME mkdir -p $CONTAINER_BENCHMARK_DIR 2>$null

Write-Host "Copiando scripts de benchmark para o container..." -ForegroundColor Yellow
foreach ($script in $LOCAL_SCRIPTS) {
    if (-not (Test-Path $script)) {
        Write-Host "Erro: Arquivo $script nao encontrado localmente!" -ForegroundColor Red
        exit 1
    }
    docker cp $script ${CONTAINER_NAME}:${CONTAINER_BENCHMARK_DIR}/
}
Write-Host "(OK) Scripts copiados para $CONTAINER_BENCHMARK_DIR" -ForegroundColor Green

# --- 3. Instalar Dependências ---
Write-Host "`nInstalando dependencias (pandas, matplotlib, psutil)..." -ForegroundColor Yellow
docker exec $CONTAINER_NAME pip install pandas numpy matplotlib seaborn psutil 2>&1 | Out-Null
Write-Host "(OK) Dependencias instaladas" -ForegroundColor Green

# --- 4. Executar o Benchmark ---
Write-Host "`nExecutando benchmark do Parser..." -ForegroundColor Yellow
Write-Host "Isso pode levar alguns minutos... Logs aparecerão abaixo." -ForegroundColor Cyan
Write-Host "Os resultados serao salvos em $CONTAINER_RESULTS_DIR" -ForegroundColor Cyan

$PYTHON_COMMAND = "python3"
$SCRIPT_NAME = "parser_test_orchestrator.py"

docker exec --workdir $CONTAINER_BENCHMARK_DIR $CONTAINER_NAME $PYTHON_COMMAND $SCRIPT_NAME

if ($LASTEXITCODE -ne 0) {
    Write-Host "`nErro ao executar o script de benchmark no container!" -ForegroundColor Red
    Write-Host "Verifique os logs de erro acima." -ForegroundColor Yellow
    exit 1
}

Write-Host "`n(OK) Benchmark concluído no container." -ForegroundColor Green

# --- 5. Copiar Resultados ---
Write-Host "`nCopiando resultados de $CONTAINER_RESULTS_DIR..." -ForegroundColor Yellow

New-Item -ItemType Directory -Force -Path $LOCAL_RESULTS_DIR | Out-Null
docker cp ${CONTAINER_NAME}:${CONTAINER_RESULTS_DIR}/. $LOCAL_RESULTS_DIR

Write-Host "(OK) Resultados copiados para: $LOCAL_RESULTS_DIR" -ForegroundColor Green

Write-Host "`n==================================" -ForegroundColor Blue
Write-Host "Benchmark do Parser Concluído!" -ForegroundColor Green
Write-Host "==================================" -ForegroundColor Blue
Write-Host "Resultados salvos em: $LOCAL_RESULTS_DIR" -ForegroundColor Cyan
Write-Host "Graficos disponiveis em: $LOCAL_RESULTS_DIR\analysis\" -ForegroundColor Cyan

# --- INÍCIO DA MODIFICAÇÃO ---
Write-Host "`nPara visualizar:" -ForegroundColor Yellow
Write-Host "  cd $LOCAL_RESULTS_DIR\analysis" -ForegroundColor White
Write-Host "  start *.pdf" -ForegroundColor White # <--- MUDADO AQUI
# --- FIM DA MODIFICAÇÃO ---