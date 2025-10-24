# 🚀 Início Rápido - Benchmark P4SymTest

## ⚡ Execução em 3 Passos

### 1. Instalar Dependências

```bash
# Navegue para o diretório do projeto
cd p4symtest

# Instale dependências do benchmark
pip install -r requirements_benchmark.txt
```

### 2. Executar Benchmark Automático

```bash
# Dá permissão de execução
chmod +x run_benchmark.sh

# Executa pipeline completo
./run_benchmark.sh
```

**Isso irá automaticamente:**
- ✅ Gerar 5 programas P4 sintéticos (complexidade crescente)
- ✅ Executar verificação completa de cada um
- ✅ Coletar métricas de tempo e memória
- ✅ Gerar 7 gráficos de análise
- ✅ Criar tabelas CSV e LaTeX

**Tempo estimado:** 5-15 minutos (depende do hardware)

### 3. Ver Resultados

```bash
# Navegue para o diretório de resultados
cd backend/workspace/benchmark_results/run_*/

# Visualize os gráficos
ls analysis/*.png

# Veja o resumo
cat benchmark_log.txt
```

---

## 📊 Resultados Gerados

```
backend/workspace/benchmark_results/run_YYYYMMDD_HHMMSS/
├── benchmark_results.json          # Dados brutos (JSON)
├── benchmark_log.txt               # Log de execução
└── analysis/
    ├── time_vs_complexity.png      # Tempo vs Complexidade
    ├── memory_vs_complexity.png    # Memória vs Complexidade
    ├── component_breakdown.png     # Breakdown por componente
    ├── cumulative_time.png         # Tempo acumulado
    ├── scalability.png             # Escalabilidade
    ├── time_distribution.png       # Distribuição de tempos
    ├── performance_heatmap.png     # Heatmap performance
    ├── summary.csv                 # Tabela CSV
    └── table.tex                   # Tabela LaTeX
```

---

## 🎯 Exemplos de Teste Específicos

### Teste de Escalabilidade do Parser

```bash
python3 benchmark_examples.py 1
```

### Teste de Escalabilidade do Ingress

```bash
python3 benchmark_examples.py 2
```

### Teste de Estados Simultâneos

```bash
python3 benchmark_examples.py 3
```

### Comparação Ingress vs Egress

```bash
python3 benchmark_examples.py 4
```

### Grid Search Completo (⚠️ DEMORADO)

```bash
python3 benchmark_examples.py 5
```

### Análise Detalhada por Componente

```bash
python3 benchmark_examples.py 6
```

---

## 🔧 Personalização Rápida

### Modificar Configurações de Teste

Edite `run_benchmark.sh` na seção de configurações:

```bash
# Linha ~45
CONFIGS=(
    "3,2,1,1,2"    # Pequeno: 3 parser states, 2 ingress, 1 egress
    "5,3,2,1,3"    # Médio
    "7,4,2,1,3"    # Grande
    # Adicione mais configurações aqui
)
```

### Gerar Programa Específico

```python
from synthetic_p4_generator import SyntheticP4Generator
from pathlib import Path

generator = SyntheticP4Generator()

# Customize os parâmetros
metadata = generator.generate_program(
    parser_states=10,       # Ajuste aqui
    ingress_tables=5,       # Ajuste aqui
    egress_tables=3,        # Ajuste aqui
    headers_per_state=1,
    actions_per_table=4,
    output_dir=Path("./custom_programs")
)

print(f"Programa gerado: {metadata['id']}")
print(f"Arquivo P4: {metadata['p4_file']}")
```

---

## 📈 Interpretação Rápida

### Tempo Total
- **< 5s**: Programa pequeno, verificação rápida ✅
- **5-20s**: Programa médio, aceitável ⚠️
- **> 20s**: Programa grande, pode precisar otimização 🔴

### Pico de Memória
- **< 100 MB**: Uso normal ✅
- **100-500 MB**: Uso moderado ⚠️
- **> 500 MB**: Uso alto, atenção 🔴

### Estados Simultâneos
- Ideal: Crescimento linear ou controlado
- Problema: Explosão exponencial (indica possível bug no programa P4)

---

## 🐛 Problemas Comuns

### "p4c: command not found"

```bash
# Instale o compilador P4
sudo apt-get install p4lang-p4c
# ou
brew install p4lang/p4/p4c
```

### "ModuleNotFoundError: No module named 'matplotlib'"

```bash
pip install -r requirements_benchmark.txt
```

### Timeout (5 min) em programas grandes

Edite `benchmark_orchestrator.py`:

```python
# Linha ~XXX
subprocess.run(..., timeout=600)  # Aumenta para 10 min
```

### Memória insuficiente

Reduza complexidade dos programas em `run_benchmark.sh`:

```bash
CONFIGS=(
    "3,2,1,1,2"    # Apenas pequeno
    "5,3,2,1,3"    # Apenas médio
)
```

---

## 💡 Próximos Passos

Após executar o primeiro benchmark:

1. **Analise os gráficos** - Identifique padrões e gargalos
2. **Compare componentes** - Veja qual etapa consome mais tempo
3. **Teste escalabilidade** - Execute exemplos específicos
4. **Customize testes** - Crie suas próprias configurações
5. **Otimize** - Use os resultados para guiar melhorias

---

## 📚 Documentação Completa

Para mais detalhes, consulte:
- `BENCHMARK_README.md` - Documentação completa
- `benchmark_examples.py` - 6 exemplos práticos
- Código fonte dos scripts para customizações avançadas

---

## ✅ Checklist de Verificação

Antes de executar o benchmark, certifique-se:

- [ ] Python 3.8+ instalado
- [ ] p4c (compilador P4) instalado
- [ ] Dependências pip instaladas (`requirements_benchmark.txt`)
- [ ] Scripts Python do P4SymTest funcionando (`run_parser.py`, etc.)
- [ ] Espaço em disco suficiente (~500 MB para resultados)

---

**Pronto!** Execute `./run_benchmark.sh` e analise os resultados em alguns minutos! 🎉