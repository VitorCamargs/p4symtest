#!/bin/bash
#
# Script de Benchmark para Docker (Windows)
#

set -e

# Cores
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}[INFO]${NC} Iniciando Benchmark P4SymTest (Docker Mode)"

# Diretórios (dentro do container)
WORKSPACE_DIR="/app/backend/workspace"
SYNTHETIC_DIR="$WORKSPACE_DIR/synthetic_programs"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
RESULTS_DIR="$WORKSPACE_DIR/benchmark_results/run_$TIMESTAMP"

# Criar diretórios
mkdir -p "$RESULTS_DIR"
mkdir -p "$SYNTHETIC_DIR"

# Navegar para workspace
cd "$WORKSPACE_DIR"

# PASSO 1: Gerar programas sintéticos
echo -e "${BLUE}[INFO]${NC} Gerando programas P4 sintéticos..."

python3 << 'EOF'
import sys
sys.path.insert(0, '/app/benchmark')
from synthetic_p4_generator import SyntheticP4Generator
from pathlib import Path
import json

generator = SyntheticP4Generator(seed=42)
manifest = []

# Configurações de teste (começar pequeno para teste rápido)
configs = [
    (3, 2, 1, 1, 2),   # Pequeno
    (5, 3, 2, 1, 3),   # Médio
]

output_dir = Path("/app/backend/workspace/synthetic_programs")
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

manifest_file = output_dir / "manifest.json"
with open(manifest_file, 'w') as f:
    json.dump(manifest, f, indent=2)

print(f"\n✓ Manifest salvo em: {manifest_file}")
EOF

# PASSO 2: Executar benchmark
echo -e "${BLUE}[INFO]${NC} Executando benchmark..."

python3 << 'EOF'
import sys
sys.path.insert(0, '/app/benchmark')
from benchmark_orchestrator import P4SymTestBenchmark, BenchmarkReporter
from pathlib import Path
import json

manifest_file = Path("/app/backend/workspace/synthetic_programs/manifest.json")

with open(manifest_file, 'r') as f:
    manifest = json.load(f)

print(f"Carregado manifest com {len(manifest)} programas")

benchmark = P4SymTestBenchmark(workspace_dir=Path("/app/backend/workspace"))
results = []

for idx, prog_meta in enumerate(manifest):
    print(f"\n[{idx+1}/{len(manifest)}] Processando: {prog_meta['id']}")
    
    result = benchmark.run_full_verification(
        p4_file=Path(prog_meta['p4_file']),
        topology_file=Path(prog_meta['topology_file']),
        runtime_file=Path(prog_meta['runtime_file'])
    )
    results.append(result)

# Salvar resultados
import os
timestamp = os.environ.get('TIMESTAMP', 'test')
results_dir = Path(f"/app/backend/workspace/benchmark_results/run_{timestamp}")
results_dir.mkdir(parents=True, exist_ok=True)

report_file = results_dir / "benchmark_results.json"
BenchmarkReporter.generate_report(results, report_file)
BenchmarkReporter.print_summary(results)

# Salvar caminho para próximo passo
with open('/tmp/results_path.txt', 'w') as f:
    f.write(str(report_file))
EOF

# PASSO 3: Análise
echo -e "${BLUE}[INFO]${NC} Gerando análises..."

python3 << 'EOF'
import sys
sys.path.insert(0, '/app/benchmark')
from benchmark_analyzer import BenchmarkAnalyzer
from pathlib import Path

with open('/tmp/results_path.txt', 'r') as f:
    results_file = Path(f.read().strip())

analyzer = BenchmarkAnalyzer(results_file)
output_dir = results_file.parent / "analysis"

analyzer.print_detailed_stats()
analyzer.generate_all_plots(output_dir)
analyzer.generate_summary_table(output_dir / "summary.csv")
analyzer.generate_latex_table(output_dir / "table.tex")

print(f"\n✓ Análise completa!")
print(f"  Resultados em: {results_file.parent}")
EOF

echo -e "${GREEN}[SUCCESS]${NC} Benchmark concluído!"