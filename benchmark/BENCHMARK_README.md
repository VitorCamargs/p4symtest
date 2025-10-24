# P4SymTest - Framework de Avaliação de Desempenho

Sistema completo para avaliar o desempenho do P4SymTest através de programas P4 sintéticos escaláveis.

## 📋 Visão Geral

O framework de benchmark consiste em 3 componentes principais:

1. **Gerador de Programas Sintéticos** (`synthetic_p4_generator.py`)
   - Gera programas P4 com complexidade configurável
   - Escaláveis em: estados do parser, tabelas ingress/egress, headers, ações

2. **Orquestrador de Benchmark** (`benchmark_orchestrator.py`)
   - Executa verificação completa end-to-end
   - Coleta métricas de tempo e memória
   - Rastreia estados simbólicos ao longo do pipeline

3. **Analisador de Resultados** (`benchmark_analyzer.py`)
   - Gera gráficos de performance
   - Calcula estatísticas detalhadas
   - Exporta dados em CSV e LaTeX

## 🚀 Início Rápido

### Execução Completa Automatizada

```bash
# Torna o script executável
chmod +x run_benchmark.sh

# Executa pipeline completo
./run_benchmark.sh
```

Isso irá:
1. Gerar programas P4 sintéticos com complexidade variada
2. Executar verificação completa de cada programa
3. Coletar métricas de desempenho
4. Gerar gráficos e análises
5. Salvar tudo em `backend/workspace/benchmark_results/run_TIMESTAMP/`

### Execução Manual (Passo a Passo)

#### 1. Gerar Programas Sintéticos

```python
from synthetic_p4_generator import SyntheticP4Generator
from pathlib import Path

generator = SyntheticP4Generator()

# Gera um programa com complexidade customizada
metadata = generator.generate_program(
    parser_states=5,        # Número de estados no parser
    ingress_tables=3,       # Número de tabelas ingress
    egress_tables=2,        # Número de tabelas egress
    headers_per_state=1,    # Headers extraídos por estado
    actions_per_table=3,    # Ações por tabela
    output_dir=Path("./synthetic_programs")
)

print(f"Programa gerado: {metadata['id']}")
```

#### 2. Executar Benchmark

```bash
cd backend/workspace

# Executa benchmark usando o manifest gerado
python3 benchmark_orchestrator.py synthetic_programs/manifest.json
```

#### 3. Analisar Resultados

```bash
# Gera gráficos e estatísticas
python3 benchmark_analyzer.py synthetic_programs/benchmark_results.json
```

## 📊 Métricas Coletadas

### Por Componente
- **Tempo de execução** (segundos)
- **Pico de memória** (MB)
- **Estados de entrada** (número de estados simbólicos)
- **Estados de saída** (estados propagados)
- **Status** (sucesso/falha)

### Agregadas
- Tempo total de verificação
- Pico de memória global
- Tempo por tipo de componente (Parser, Ingress, Egress, Deparser)
- Escalabilidade vs. número de componentes
- Escalabilidade vs. estados simultâneos

## 📈 Gráficos Gerados

O analisador gera 7 gráficos PNG:

1. **time_vs_complexity.png** - Tempo vs. Complexidade (Parser States, Ingress Tables, Egress Tables)
2. **memory_vs_complexity.png** - Memória vs. Complexidade
3. **component_breakdown.png** - Tempo médio por tipo de componente
4. **cumulative_time.png** - Tempo acumulado ao longo do pipeline
5. **scalability.png** - Estados simultâneos vs. Tempo
6. **time_distribution.png** - Distribuição de tempos de execução
7. **performance_heatmap.png** - Heatmap (Ingress x Egress)

## 📁 Estrutura de Arquivos Gerados

```
backend/workspace/
├── synthetic_programs/           # Programas P4 gerados
│   ├── synth_p3_i2_e1.p4
│   ├── synth_p3_i2_e1_topology.json
│   ├── synth_p3_i2_e1_runtime.json
│   ├── ...
│   └── manifest.json            # Índice de todos os programas
│
└── benchmark_results/
    └── run_YYYYMMDD_HHMMSS/     # Resultados desta execução
        ├── benchmark_results.json   # Dados brutos
        ├── benchmark_log.txt        # Log de execução
        ├── analysis_log.txt         # Log de análise
        └── analysis/                # Visualizações
            ├── *.png                # Gráficos
            ├── summary.csv          # Tabela CSV
            └── table.tex            # Tabela LaTeX
```

## 🔧 Configuração Customizada

### Criar Configuração de Teste Personalizada

Edite o array `CONFIGS` em `run_benchmark.sh` ou crie programas manualmente:

```python
# Exemplo: Teste de escalabilidade do parser
configs = [
    (3, 2, 1, 1, 2),   # Baseline
    (6, 2, 1, 1, 2),   # 2x parser states
    (9, 2, 1, 1, 2),   # 3x parser states
    (12, 2, 1, 1, 2),  # 4x parser states
]

# Exemplo: Teste de escalabilidade do ingress
configs = [
    (5, 2, 1, 1, 3),   # Baseline
    (5, 4, 1, 1, 3),   # 2x ingress tables
    (5, 6, 1, 1, 3),   # 3x ingress tables
    (5, 8, 1, 1, 3),   # 4x ingress tables
]
```

### Parâmetros do Gerador

```python
generator.generate_program(
    parser_states=5,        # Estados no parser (incluindo start)
    ingress_tables=3,       # Tabelas no pipeline ingress
    egress_tables=2,        # Tabelas no pipeline egress
    headers_per_state=1,    # Headers extraídos por estado parser
    actions_per_table=3,    # Ações disponíveis por tabela
    output_dir=Path("./custom_dir")
)
```

## 📌 Casos de Uso

### 1. Avaliar Escalabilidade do Parser

Teste como o tempo cresce com o aumento de estados do parser:

```python
for states in [3, 5, 8, 10, 15, 20]:
    generator.generate_program(
        parser_states=states,
        ingress_tables=2,
        egress_tables=1
    )
```

### 2. Avaliar Impacto do Pipeline Ingress

Teste complexidade crescente do pipeline:

```python
for tables in [2, 4, 6, 8, 10]:
    generator.generate_program(
        parser_states=5,
        ingress_tables=tables,
        egress_tables=1
    )
```

### 3. Avaliar Estados Simultâneos

Aumente `headers_per_state` para gerar mais estados simultâneos:

```python
generator.generate_program(
    parser_states=8,
    ingress_tables=4,
    egress_tables=2,
    headers_per_state=2  # Mais headers = mais estados simultâneos
)
```

### 4. Benchmark Completo (Pipeline End-to-End)

Varie todos os parâmetros simultaneamente:

```python
configs = [
    (3, 2, 1, 1, 2),    # Pequeno
    (6, 4, 2, 1, 3),    # Médio
    (10, 6, 3, 2, 4),   # Grande
    (15, 8, 4, 2, 5),   # Muito Grande
]
```

## 🔍 Interpretação dos Resultados

### Métricas Importantes

- **Tempo Total**: Indica eficiência geral da verificação
- **Tempo por Componente**: Identifica gargalos (Parser, Ingress, Egress)
- **Pico de Memória**: Indica viabilidade para programas grandes
- **Estados Propagados**: Mostra explosão de estados (ou controle dela)

### Análise de Escalabilidade

Observe os gráficos:
- **Linear**: Escalabilidade ideal (O(n))
- **Quadrática**: Possível problema de complexidade (O(n²))
- **Exponencial**: Explosão de estados (problema crítico)

### Identificação de Gargalos

O gráfico `component_breakdown.png` mostra onde o tempo é gasto:
- Se **Parser** domina: Otimizar análise simbólica de transições
- Se **Ingress** domina: Otimizar execução simbólica de tabelas
- Se **Egress** domina: Similar ao ingress, mas no egress pipeline
- Se **Deparser** domina: Otimizar verificação de emissão de headers

## 🐛 Troubleshooting

### Timeout de Execução

Se programas muito grandes causam timeout (5 min):

```python
# Em benchmark_orchestrator.py, linha ~XXX
subprocess.run(..., timeout=600)  # Aumenta para 10 min
```

### Memória Insuficiente

Reduza complexidade dos programas ou execute programas menores:

```python
configs = [
    (3, 2, 1, 1, 2),   # Apenas programas pequenos
    (5, 3, 2, 1, 3),
]
```

### Erros de Compilação P4

Verifique se `p4c` está instalado e no PATH:

```bash
which p4c
p4c --version
```

## 📝 Exportação de Resultados

### CSV para Análise em Excel/R/Python

```python
import pandas as pd

df = pd.read_csv("analysis/summary.csv")
print(df.describe())
```

### LaTeX para Artigos Acadêmicos

Copie o conteúdo de `analysis/table.tex` direto para seu documento LaTeX.

### JSON para Análise Customizada

```python
import json

with open("benchmark_results.json", 'r') as f:
    data = json.load(f)

# Análise customizada
for result in data['results']:
    print(f"{result['program_id']}: {result['total_duration_seconds']}s")
```

## 🎯 Próximos Passos

Após executar o benchmark:

1. **Analise os gráficos** para identificar padrões
2. **Compare com baseline** (se você tiver dados anteriores)
3. **Identifique gargalos** usando component_breakdown
4. **Otimize** os componentes críticos
5. **Re-execute** o benchmark para validar melhorias

## 📚 Referências

- **Documentação P4**: https://p4.org/specs/
- **Z3 Theorem Prover**: https://github.com/Z3Prover/z3
- **P4 Compiler (p4c)**: https://github.com/p4lang/p4c

---

**Nota**: Este framework é projetado para avaliar o P4SymTest em ambiente controlado. Para produção, considere adicionar timeouts mais longos e tratamento de erros mais robusto.