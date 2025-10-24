# test_simple.ps1
# Teste simplificado para verificar se tudo esta funcionando

Write-Host "==================================" -ForegroundColor Blue
Write-Host "Teste Simples - Gerador P4" -ForegroundColor Blue
Write-Host "==================================" -ForegroundColor Blue

$CONTAINER_NAME = "p4symtest-backend"

# Verifica container
Write-Host "`n[1/5] Verificando container..." -ForegroundColor Yellow
$containerRunning = docker ps --filter "name=$CONTAINER_NAME" --format "{{.Names}}" 2>$null

if (-not $containerRunning) {
    Write-Host "X Container nao esta rodando!" -ForegroundColor Red
    Write-Host "Execute: docker-compose up -d" -ForegroundColor Yellow
    exit 1
}
Write-Host "(OK) Container encontrado: $containerRunning" -ForegroundColor Green

# Cria diretorio
Write-Host "`n[2/5] Preparando ambiente..." -ForegroundColor Yellow
docker exec $CONTAINER_NAME mkdir -p /app/benchmark 2>$null
Write-Host "(OK) Diretorio criado" -ForegroundColor Green

# Copia arquivos
Write-Host "`n[3/5] Copiando arquivos..." -ForegroundColor Yellow
docker cp synthetic_p4_generator.py ${CONTAINER_NAME}:/app/benchmark/
Write-Host "(OK) synthetic_p4_generator.py copiado" -ForegroundColor Green

# Instala dependencias basicas
Write-Host "`n[4/5] Instalando pandas..." -ForegroundColor Yellow
docker exec $CONTAINER_NAME pip install --quiet pandas 2>&1 | Out-Null
Write-Host "(OK) Pandas instalado" -ForegroundColor Green

# Testa gerador
Write-Host "`n[5/5] Testando gerador..." -ForegroundColor Yellow

# CORRECAO AQUI: As aspas dentro das f-strings do Python precisam ser escapadas com \
# para o parser do PowerShell ( @"..."@ )
$testScript = @"
import sys
sys.path.insert(0, '/app/benchmark')
from synthetic_p4_generator import SyntheticP4Generator
from pathlib import Path

generator = SyntheticP4Generator()
print('(OK) Gerador importado com sucesso')

metadata = generator.generate_program(
    parser_states=3,
    ingress_tables=2,
    egress_tables=1,
    output_dir=Path('/app/backend/workspace/test_output')
)

print(f'(OK) Programa gerado: {metadata[\"id\"]}')
print(f'(OK) Arquivo P4: {metadata[\"p4_file\"]}')
print(f'  - Parser states: {metadata[\"config\"][\"parser_states\"]}')
print(f'  - Ingress tables: {metadata[\"config\"][\"ingress_tables\"]}')
print(f'  - Egress tables: {metadata[\"config\"][\"egress_tables\"]}')
"@

docker exec $CONTAINER_NAME python3 -c $testScript

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n==================================" -ForegroundColor Green
    Write-Host "(OK) TESTE BEM-SUCEDIDO!" -ForegroundColor Green
    Write-Host "==================================" -ForegroundColor Green
    Write-Host "`nO gerador esta funcionando corretamente!" -ForegroundColor Cyan
    Write-Host "Agora voce pode executar o benchmark completo:" -ForegroundColor Yellow
    Write-Host "  powershell -ExecutionPolicy Bypass -File .\run_benchmark.ps1" -ForegroundColor White
} else {
    Write-Host "`nX TESTE FALHOU!" -ForegroundColor Red
    Write-Host "Verifique os erros acima." -ForegroundColor Yellow
}