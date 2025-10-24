# run_benchmark.ps1
# Script para executar benchmark no Docker Desktop (Windows)

Write-Host "==================================" -ForegroundColor Blue
Write-Host "P4SymTest Benchmark (Docker Mode)" -ForegroundColor Blue
Write-Host "==================================" -ForegroundColor Blue

# Nome do container (ajuste se necessario)
$CONTAINER_NAME = "p4symtest-backend"

Write-Host "`nVerificando container..." -ForegroundColor Yellow

# Verifica se container esta rodando
$containerRunning = docker ps --filter "name=$CONTAINER_NAME" --format "{{.Names}}" 2>$null

if (-not $containerRunning) {
    Write-Host "Erro: Container $CONTAINER_NAME nao esta rodando!" -ForegroundColor Red
    Write-Host "Inicie o Docker Compose primeiro: docker-compose up -d" -ForegroundColor Yellow
    exit 1
}

Write-Host "(OK) Container encontrado: $CONTAINER_NAME" -ForegroundColor Green

# Cria diretorio benchmark no container
Write-Host "`nPreparando ambiente no container..." -ForegroundColor Yellow
docker exec $CONTAINER_NAME mkdir -p /app/benchmark 2>$null

# Copia arquivos para o container
Write-Host "Copiando arquivos de benchmark para o container..." -ForegroundColor Yellow

docker cp synthetic_p4_generator.py ${CONTAINER_NAME}:/app/benchmark/
docker cp benchmark_orchestrator.py ${CONTAINER_NAME}:/app/benchmark/
docker cp benchmark_analyzer.py ${CONTAINER_NAME}:/app/benchmark/

Write-Host "(OK) Arquivos copiados" -ForegroundColor Green

# Instala dependencias no container
Write-Host "`nInstalando dependencias..." -ForegroundColor Yellow

docker exec $CONTAINER_NAME pip install pandas numpy matplotlib seaborn psutil 2>&1 | Out-Null

Write-Host "(OK) Dependencias instaladas" -ForegroundColor Green

# Executa benchmark (versao inline para Windows)
Write-Host "`nExecutando benchmark..." -ForegroundColor Yellow
Write-Host "Isso pode levar alguns minutos...`n" -ForegroundColor Cyan

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"

# Script Python inline para gerar programas
Write-Host "[1/3] Gerando programas P4 sinteticos..." -ForegroundColor Cyan

$generateScript = @"
import sys
sys.path.insert(0, '/app/benchmark')
from synthetic_p4_generator import SyntheticP4Generator
from pathlib import Path
import json

generator = SyntheticP4Generator(seed=42)
manifest = []

configs = [
    (3, 2, 1, 1, 2),
    (5, 3, 2, 1, 3),
]

# --- CAMINHO ATUALIZADO ---
output_dir = Path('/app/benchmark/synthetic_programs')
output_dir.mkdir(parents=True, exist_ok=True)

print(f'Gerando {len(configs)} programas sinteticos...')

for parser_states, ingress_tables, egress_tables, headers_per_state, actions_per_table in configs:
    metadata = generator.generate_program(
        parser_states=parser_states,
        ingress_tables=ingress_tables,
        egress_tables=egress_tables,
        headers_per_state=headers_per_state,
        actions_per_table=actions_per_table,
        output_dir=output_dir
    )
    manifest.append(metadata)
    print(f'(OK) Gerado: {metadata[\"id\"]}')

manifest_file = output_dir / 'manifest.json'
with open(manifest_file, 'w') as f:
    json.dump(manifest, f, indent=2)

print(f'(OK) Manifest salvo')
"@

docker exec $CONTAINER_NAME python3 -c $generateScript

if ($LASTEXITCODE -ne 0) {
    Write-Host "Erro ao gerar programas!" -ForegroundColor Red
    exit 1
}

# Script Python inline para executar benchmark
Write-Host "`n[2/3] Executando verificacao completa..." -ForegroundColor Cyan

$benchmarkScript = @"
import sys
sys.path.insert(0, '/app/benchmark')
from benchmark_orchestrator import P4SymTestBenchmark, BenchmarkReporter
from pathlib import Path
import json

# --- CAMINHO ATUALIZADO ---
manifest_file = Path('/app/benchmark/synthetic_programs/manifest.json')

with open(manifest_file, 'r') as f:
    manifest = json.load(f)

print(f'Carregado manifest com {len(manifest)} programas')

# --- CAMINHO ATUALIZADO ---
# 1. workspace_dir: Onde os outputs/compilacoes vao -> /app/benchmark
# 2. scripts_dir: Onde os scripts run_...py estao -> /app/workspace
benchmark = P4SymTestBenchmark(
    workspace_dir=Path('/app/benchmark'),
    scripts_dir=Path('/app/workspace')
)

results = []

for idx, prog_meta in enumerate(manifest):
    print(f'\n[{idx+1}/{len(manifest)}] Processando: {prog_meta[\"id\"]}')
    
    result = benchmark.run_full_verification(
        p4_file=Path(prog_meta['p4_file']),
        topology_file=Path(prog_meta['topology_file']),
        runtime_file=Path(prog_meta['runtime_file'])
    )
    results.append(result)

# Salvar resultados
# --- CAMINHO ATUALIZADO ---
results_dir = Path('/app/benchmark/benchmark_results/run_$timestamp')
results_dir.mkdir(parents=True, exist_ok=True)

report_file = results_dir / 'benchmark_results.json'
BenchmarkReporter.generate_report(results, report_file)
BenchmarkReporter.print_summary(results)

print(f'\n(OK) Resultados salvos em: {report_file}')
"@

docker exec $CONTAINER_NAME python3 -c $benchmarkScript

if ($LASTEXITCODE -ne 0) {
    Write-Host "Erro ao executar benchmark!" -ForegroundColor Red
    exit 1
}

# Script Python inline para analise
Write-Host "`n[3/3] Gerando analises e graficos..." -ForegroundColor Cyan

$analyzeScript = @"
import sys
sys.path.insert(0, '/app/benchmark')
from benchmark_analyzer import BenchmarkAnalyzer
from pathlib import Path

# --- CAMINHO ATUALIZADO ---
results_file = Path('/app/benchmark/benchmark_results/run_$timestamp/benchmark_results.json')

if not results_file.exists():
    print(f'Erro: Arquivo de resultados nao encontrado: {results_file}')
    sys.exit(1)

analyzer = BenchmarkAnalyzer(results_file)
output_dir = results_file.parent / 'analysis'

analyzer.print_detailed_stats()
analyzer.generate_all_plots(output_dir)
analyzer.generate_summary_table(output_dir / 'summary.csv')
analyzer.generate_latex_table(output_dir / 'table.tex')

print(f'\n(OK) Analise completa!')
"@

docker exec $CONTAINER_NAME python3 -c $analyzeScript

# Copia resultados de volta
Write-Host "`nCopiando resultados..." -ForegroundColor Yellow

$resultsPath = ".\results_$timestamp"

# Cria diretorio local
New-Item -ItemType Directory -Force -Path $resultsPath | Out-Null

# Copia arquivos do container
# --- CAMINHO ATUALIZADO ---
docker cp ${CONTAINER_NAME}:/app/benchmark/benchmark_results/run_$timestamp/. $resultsPath

Write-Host "(OK) Resultados copiados para: $resultsPath" -ForegroundColor Green

Write-Host "`n==================================" -ForegroundColor Blue
Write-Host "Benchmark Concluido!" -ForegroundColor Green
Write-Host "==================================" -ForegroundColor Blue
Write-Host "Resultados salvos em: $resultsPath" -ForegroundColor Cyan
Write-Host "Graficos disponiveis em: $resultsPath\analysis\" -ForegroundColor Cyan
Write-Host "`nPara visualizar:" -ForegroundColor Yellow
Write-Host "  cd $resultsPath\analysis" -ForegroundColor White
Write-Host "  start *.png" -ForegroundColor White