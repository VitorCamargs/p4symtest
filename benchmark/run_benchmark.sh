#!/bin/bash
#
# Script Completo de Benchmark do P4SymTest
# Gera programas sintéticos, executa verificação e analisa resultados
#

set -e  # Exit on error

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Função de log
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Diretórios
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="$SCRIPT_DIR/backend/workspace"
SYNTHETIC_DIR="$BACKEND_DIR/synthetic_programs"
RESULTS_DIR="$BACKEND_DIR/benchmark_results"

# Cria timestamp para esta execução
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
RUN_DIR="$RESULTS_DIR/run_$TIMESTAMP"

log_info "========================================"
log_info "P4SymTest Benchmark Pipeline"
log_info "========================================"
log_info "Timestamp: $TIMESTAMP"
log_info "Diretório de resultados: $RUN_DIR"
log_info ""

# Cria diretórios
mkdir -p "$RUN_DIR"
mkdir -p "$SYNTHETIC_DIR"

# Copia scripts de benchmark para workspace
log_info "Preparando ambiente..."
cp "$SCRIPT_DIR/synthetic_p4_generator.py" "$BACKEND_DIR/"
cp "$SCRIPT_DIR/benchmark_orchestrator.py" "$BACKEND_DIR/"
cp "$SCRIPT_DIR/benchmark_analyzer.py" "$BACKEND_DIR/"

cd "$BACKEND_DIR"

# ==============================================
# PASSO 1: GERAÇÃO DE PROGRAMAS SINTÉTICOS
# ==============================================
log_info "PASSO 1/3: Gerando programas P4 sintéticos..."

# Configurações de teste (podem ser personalizadas)
# Formato: parser_states,ingress_tables,egress_tables,headers_per_state,actions_per_table
CONFIGS=(
    "3,2,1,1,2"    # Pequeno
    "5,3,2,1,3"    # Médio
    "7,4,2,1,3"    # Grande
    "10,5,3,2,4"   # Muito Grande
    "12,6,4,2,4"   # Extra Grande
)

# Limpa diretório anterior
rm -rf "$SYNTHETIC_DIR"
mkdir -p "$SYNTHETIC_DIR"

# Cria programas
python3 <<EOF
from synthetic_p4_generator import SyntheticP4Generator
from pathlib import Path
import json

generator = SyntheticP4Generator(seed=42)
manifest = []

configs = [
    (3, 2, 1, 1, 2),   # Pequeno
    (5, 3, 2, 1, 3),   # Médio
    (7, 4, 2, 1, 3),   # Grande
    (10, 5, 3, 2, 4),  # Muito Grande
    (12, 6, 4, 2, 4),  # Extra Grande
]

output_dir = Path("$SYNTHETIC_DIR")
print(f"Gerando {len(configs)} programas sintéticos...")

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
    print(f"✓ Gerado: {metadata['id']}")

# Salva manifest
manifest_file = output_dir / "manifest.json"
with open(manifest_file, 'w') as f:
    json.dump(manifest, f, indent=2)

print(f"\n✓ Manifest salvo em: {manifest_file}")
EOF

if [ $? -eq 0 ]; then
    log_success "Programas sintéticos gerados com sucesso!"
else
    log_error "Falha ao gerar programas sintéticos"
    exit 1
fi

# ==============================================
# PASSO 2: EXECUÇÃO DE BENCHMARK
# ==============================================
log_info ""
log_info "PASSO 2/3: Executando benchmark..."
log_info "Isso pode levar vários minutos dependendo da complexidade..."
log_info ""

# Executa benchmark
python3 benchmark_orchestrator.py "$SYNTHETIC_DIR/manifest.json" 2>&1 | tee "$RUN_DIR/benchmark_log.txt"

if [ ${PIPESTATUS[0]} -eq 0 ]; then
    log_success "Benchmark executado com sucesso!"
    
    # Move resultados para diretório desta execução
    mv "$SYNTHETIC_DIR/benchmark_results.json" "$RUN_DIR/"
    
else
    log_error "Falha na execução do benchmark"
    exit 1
fi

# ==============================================
# PASSO 3: ANÁLISE E VISUALIZAÇÃO
# ==============================================
log_info ""
log_info "PASSO 3/3: Gerando análises e gráficos..."

python3 benchmark_analyzer.py "$RUN_DIR/benchmark_results.json" 2>&1 | tee -a "$RUN_DIR/analysis_log.txt"

if [ ${PIPESTATUS[0]} -eq 0 ]; then
    log_success "Análise concluída!"
else
    log_warning "Análise concluída com avisos"
fi

# ==============================================
# RESUMO FINAL
# ==============================================
log_info ""
log_info "========================================"
log_info "BENCHMARK CONCLUÍDO!"
log_info "========================================"
log_info ""
log_success "Resultados salvos em: $RUN_DIR"
log_info ""
log_info "Arquivos gerados:"
log_info "  - benchmark_results.json    : Dados brutos de benchmark"
log_info "  - benchmark_log.txt         : Log de execução"
log_info "  - analysis/                 : Gráficos e análises"
log_info "    ├── *.png                 : Gráficos de performance"
log_info "    ├── summary.csv           : Tabela resumo (CSV)"
log_info "    └── table.tex             : Tabela para LaTeX"
log_info ""

# Lista arquivos gerados
if [ -d "$RUN_DIR/analysis" ]; then
    log_info "Gráficos gerados:"
    ls -lh "$RUN_DIR/analysis/"*.png 2>/dev/null | awk '{print "  - " $9}' || true
fi

log_info ""
log_success "Pipeline de benchmark concluído com sucesso!"
log_info "Para visualizar os gráficos, abra os arquivos PNG em $RUN_DIR/analysis/"
log_info ""