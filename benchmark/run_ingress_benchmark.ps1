# run_ingress_benchmark.ps1
# Script para executar o benchmark ISOLADO DA TABELA INGRESS (Objetivo 2)

Write-Host "==================================" -ForegroundColor Blue
Write-Host "P4SymTest - Benchmark (Ingress Table)" -ForegroundColor Blue
Write-Host "==================================" -ForegroundColor Blue

# --- Configuração ---
$CONTAINER_NAME = "p4symtest-backend"
$TIMESTAMP = Get-Date -Format "yyyyMMdd_HHmmss"

# Diretório de destino no container para nossos scripts
$CONTAINER_BENCHMARK_DIR = "/app/benchmark_ingress_test"

# Scripts Python LOCAIS que precisamos copiar
$LOCAL_SCRIPTS = @(
    ".\ingress_test_orchestrator.py",   # O orquestrador (versão de teste único)
    ".\synthetic_p4_generator.py"     # O GERADOR P4 existente
)

# Onde os resultados serão gerados DENTRO do container
$CONTAINER_RESULTS_DIR = "/app/workspace/ingress_benchmark_run"
# Onde copiar os resultados LOCALMENTE
$LOCAL_RESULTS_DIR = ".\ingress_results_$TIMESTAMP"

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
Write-Host "`nExecutando benchmark da Tabela Ingress (Teste Único)..." -ForegroundColor Yellow
Write-Host "Logs e prints do 'run_table.py' aparecerão abaixo." -ForegroundColor Cyan
Write-Host "Os resultados serao salvos em $CONTAINER_RESULTS_DIR" -ForegroundColor Cyan

$PYTHON_COMMAND = "python3"
$SCRIPT_NAME = "ingress_test_orchestrator.py"

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
Write-Host "Benchmark da Tabela Ingress Concluído!" -ForegroundColor Green
Write-Host "==================================" -ForegroundColor Blue
Write-Host "Resultados salvos em: $LOCAL_RESULTS_DIR" -ForegroundColor Cyan
# Não tenta abrir PDFs pois o script de teste único não os gera
Write-Host "Verifique os CSVs em: $LOCAL_RESULTS_DIR\analysis\" -ForegroundColor Cyan