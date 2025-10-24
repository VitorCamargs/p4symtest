#!/usr/bin/env python3
"""
Exemplos de Uso do Framework de Benchmark P4SymTest
Demonstra diferentes cenários de teste e análise
"""

from pathlib import Path
from synthetic_p4_generator import SyntheticP4Generator
from benchmark_orchestrator import P4SymTestBenchmark, BenchmarkReporter
import json

# ============================================
# EXEMPLO 1: Teste de Escalabilidade do Parser
# ============================================
def example_parser_scalability():
    """
    Testa como o tempo de verificação escala com o número de estados do parser
    Mantém ingress/egress constantes para isolar impacto do parser
    """
    print("\n" + "="*70)
    print("EXEMPLO 1: Escalabilidade do Parser")
    print("="*70)
    
    generator = SyntheticP4Generator()
    benchmark = P4SymTestBenchmark()
    output_dir = Path("./benchmark_examples/parser_scalability")
    
    # Configurações: Aumenta apenas parser states
    parser_states_range = [3, 5, 7, 10, 12, 15]
    results = []
    
    for parser_states in parser_states_range:
        print(f"\n--- Testando com {parser_states} estados no parser ---")
        
        # Gera programa
        metadata = generator.generate_program(
            parser_states=parser_states,
            ingress_tables=2,  # Constante
            egress_tables=1,   # Constante
            headers_per_state=1,
            actions_per_table=2,
            output_dir=output_dir
        )
        
        # Executa benchmark
        result = benchmark.run_full_verification(
            p4_file=Path(metadata['p4_file']),
            topology_file=Path(metadata['topology_file']),
            runtime_file=Path(metadata['runtime_file'])
        )
        results.append(result)
    
    # Salva e analisa
    report_file = output_dir / "results.json"
    BenchmarkReporter.generate_report(results, report_file)
    BenchmarkReporter.print_summary(results)
    
    # Análise específica
    print("\nAnálise de Escalabilidade do Parser:")
    print(f"{'Parser States':<15} {'Tempo (s)':<12} {'Crescimento'}")
    print("-" * 45)
    
    prev_time = None
    for i, r in enumerate(results):
        if r.success:
            time = r.total_duration_seconds
            growth = f"{time/prev_time:.2f}x" if prev_time else "baseline"
            print(f"{parser_states_range[i]:<15} {time:<12.3f} {growth}")
            prev_time = time


# ============================================
# EXEMPLO 2: Teste de Escalabilidade do Ingress
# ============================================
def example_ingress_scalability():
    """
    Testa impacto do número de tabelas ingress no tempo de verificação
    """
    print("\n" + "="*70)
    print("EXEMPLO 2: Escalabilidade do Pipeline Ingress")
    print("="*70)
    
    generator = SyntheticP4Generator()
    benchmark = P4SymTestBenchmark()
    output_dir = Path("./benchmark_examples/ingress_scalability")
    
    # Configurações: Aumenta apenas ingress tables
    ingress_tables_range = [2, 4, 6, 8, 10]
    results = []
    
    for ingress_tables in ingress_tables_range:
        print(f"\n--- Testando com {ingress_tables} tabelas ingress ---")
        
        metadata = generator.generate_program(
            parser_states=5,   # Constante
            ingress_tables=ingress_tables,
            egress_tables=2,   # Constante
            headers_per_state=1,
            actions_per_table=3,
            output_dir=output_dir
        )
        
        result = benchmark.run_full_verification(
            p4_file=Path(metadata['p4_file']),
            topology_file=Path(metadata['topology_file']),
            runtime_file=Path(metadata['runtime_file'])
        )
        results.append(result)
    
    report_file = output_dir / "results.json"
    BenchmarkReporter.generate_report(results, report_file)
    
    # Análise de tempo por tabela
    print("\nTempo Médio por Tabela Ingress:")
    print(f"{'N Tables':<12} {'Tempo Total (s)':<18} {'Tempo/Tabela (s)'}")
    print("-" * 50)
    
    for i, r in enumerate(results):
        if r.success:
            total_time = r.total_duration_seconds
            # Soma tempo de todas as tabelas ingress
            ingress_time = sum(
                m.duration_seconds for m in r.component_metrics 
                if 'Ingress:' in m.component
            )
            avg_per_table = ingress_time / ingress_tables_range[i] if ingress_tables_range[i] > 0 else 0
            print(f"{ingress_tables_range[i]:<12} {total_time:<18.3f} {avg_per_table:.3f}")


# ============================================
# EXEMPLO 3: Teste de Estados Simultâneos
# ============================================
def example_state_explosion():
    """
    Testa comportamento com crescimento de estados simbólicos simultâneos
    Aumenta headers_per_state para criar mais caminhos no parser
    """
    print("\n" + "="*70)
    print("EXEMPLO 3: Estados Simbólicos Simultâneos")
    print("="*70)
    
    generator = SyntheticP4Generator()
    benchmark = P4SymTestBenchmark()
    output_dir = Path("./benchmark_examples/state_explosion")
    
    # Configurações: Aumenta headers por estado = mais estados simultâneos
    configs = [
        (4, 1),  # 4 estados parser, 1 header/estado
        (4, 2),  # 4 estados parser, 2 headers/estado
        (6, 1),  # 6 estados parser, 1 header/estado
        (6, 2),  # 6 estados parser, 2 headers/estado
    ]
    
    results = []
    
    for parser_states, headers_per_state in configs:
        print(f"\n--- Parser: {parser_states} estados, {headers_per_state} header(s)/estado ---")
        
        metadata = generator.generate_program(
            parser_states=parser_states,
            ingress_tables=3,
            egress_tables=1,
            headers_per_state=headers_per_state,
            actions_per_table=2,
            output_dir=output_dir
        )
        
        result = benchmark.run_full_verification(
            p4_file=Path(metadata['p4_file']),
            topology_file=Path(metadata['topology_file']),
            runtime_file=Path(metadata['runtime_file'])
        )
        results.append(result)
    
    report_file = output_dir / "results.json"
    BenchmarkReporter.generate_report(results, report_file)
    
    # Análise de explosão de estados
    print("\nAnálise de Estados Simultâneos:")
    print(f"{'Config':<20} {'Max Estados':<15} {'Tempo (s)':<12} {'Memória (MB)'}")
    print("-" * 65)
    
    for i, r in enumerate(results):
        if r.success:
            config = f"{configs[i][0]}p x {configs[i][1]}h"
            max_states = max(
                (m.output_states for m in r.component_metrics),
                default=0
            )
            print(f"{config:<20} {max_states:<15} {r.total_duration_seconds:<12.3f} {r.total_memory_peak_mb:.2f}")


# ============================================
# EXEMPLO 4: Comparação Ingress vs Egress
# ============================================
def example_ingress_vs_egress():
    """
    Compara overhead de tabelas ingress vs egress
    """
    print("\n" + "="*70)
    print("EXEMPLO 4: Comparação Ingress vs Egress")
    print("="*70)
    
    generator = SyntheticP4Generator()
    benchmark = P4SymTestBenchmark()
    output_dir = Path("./benchmark_examples/ingress_vs_egress")
    
    # Configurações: Varia ingress/egress mantendo total constante
    configs = [
        ("Ingress-heavy", 6, 2),
        ("Balanced", 4, 4),
        ("Egress-heavy", 2, 6),
    ]
    
    results = []
    
    for name, ingress_tables, egress_tables in configs:
        print(f"\n--- Config: {name} ({ingress_tables}i / {egress_tables}e) ---")
        
        metadata = generator.generate_program(
            parser_states=5,
            ingress_tables=ingress_tables,
            egress_tables=egress_tables,
            headers_per_state=1,
            actions_per_table=3,
            output_dir=output_dir
        )
        
        result = benchmark.run_full_verification(
            p4_file=Path(metadata['p4_file']),
            topology_file=Path(metadata['topology_file']),
            runtime_file=Path(metadata['runtime_file'])
        )
        results.append(result)
    
    report_file = output_dir / "results.json"
    BenchmarkReporter.generate_report(results, report_file)
    
    # Análise comparativa
    print("\nComparação Ingress vs Egress:")
    print(f"{'Configuração':<15} {'Ingress':<10} {'Egress':<10} {'Tempo Ing(s)':<15} {'Tempo Egr(s)':<15}")
    print("-" * 75)
    
    for i, r in enumerate(results):
        if r.success:
            config_name = configs[i][0]
            ingress_t = configs[i][1]
            egress_t = configs[i][2]
            
            # Soma tempos ingress
            ing_time = sum(
                m.duration_seconds for m in r.component_metrics 
                if 'Ingress:' in m.component
            )
            
            # Soma tempos egress
            egr_time = sum(
                m.duration_seconds for m in r.component_metrics 
                if 'Egress:' in m.component
            )
            
            print(f"{config_name:<15} {ingress_t:<10} {egress_t:<10} {ing_time:<15.3f} {egr_time:<15.3f}")


# ============================================
# EXEMPLO 5: Benchmark Completo (Grid Search)
# ============================================
def example_full_grid_search():
    """
    Testa combinações de complexidade (grid search)
    Útil para encontrar limites práticos do sistema
    """
    print("\n" + "="*70)
    print("EXEMPLO 5: Grid Search Completo")
    print("="*70)
    print("AVISO: Este teste pode demorar MUITO tempo!")
    print("="*70)
    
    generator = SyntheticP4Generator()
    benchmark = P4SymTestBenchmark()
    output_dir = Path("./benchmark_examples/grid_search")
    
    # Grid de configurações
    parser_range = [3, 5, 7]
    ingress_range = [2, 4, 6]
    egress_range = [1, 2, 3]
    
    total_configs = len(parser_range) * len(ingress_range) * len(egress_range)
    print(f"\nTotal de configurações: {total_configs}")
    
    results = []
    config_count = 0
    
    for parser_states in parser_range:
        for ingress_tables in ingress_range:
            for egress_tables in egress_range:
                config_count += 1
                print(f"\n[{config_count}/{total_configs}] P={parser_states}, I={ingress_tables}, E={egress_tables}")
                
                metadata = generator.generate_program(
                    parser_states=parser_states,
                    ingress_tables=ingress_tables,
                    egress_tables=egress_tables,
                    headers_per_state=1,
                    actions_per_table=3,
                    output_dir=output_dir
                )
                
                result = benchmark.run_full_verification(
                    p4_file=Path(metadata['p4_file']),
                    topology_file=Path(metadata['topology_file']),
                    runtime_file=Path(metadata['runtime_file'])
                )
                results.append(result)
    
    report_file = output_dir / "results.json"
    BenchmarkReporter.generate_report(results, report_file)
    BenchmarkReporter.print_summary(results)
    
    # Encontra configuração mais rápida e mais lenta
    successful = [r for r in results if r.success]
    if successful:
        fastest = min(successful, key=lambda r: r.total_duration_seconds)
        slowest = max(successful, key=lambda r: r.total_duration_seconds)
        
        print("\n" + "="*70)
        print("Configuração MAIS RÁPIDA:")
        print(f"  Parser: {fastest.parser_states_count}, Ingress: {fastest.ingress_tables_count}, Egress: {fastest.egress_tables_count}")
        print(f"  Tempo: {fastest.total_duration_seconds:.3f}s")
        
        print("\nConfiguração MAIS LENTA:")
        print(f"  Parser: {slowest.parser_states_count}, Ingress: {slowest.ingress_tables_count}, Egress: {slowest.egress_tables_count}")
        print(f"  Tempo: {slowest.total_duration_seconds:.3f}s")
        print(f"  Fator: {slowest.total_duration_seconds / fastest.total_duration_seconds:.2f}x mais lento")


# ============================================
# EXEMPLO 6: Análise de Componente Específico
# ============================================
def example_component_analysis():
    """
    Analisa tempo de cada componente isoladamente
    Útil para identificar gargalos
    """
    print("\n" + "="*70)
    print("EXEMPLO 6: Análise Detalhada por Componente")
    print("="*70)
    
    generator = SyntheticP4Generator()
    benchmark = P4SymTestBenchmark()
    output_dir = Path("./benchmark_examples/component_analysis")
    
    # Gera programa médio
    metadata = generator.generate_program(
        parser_states=7,
        ingress_tables=4,
        egress_tables=2,
        headers_per_state=1,
        actions_per_table=3,
        output_dir=output_dir
    )
    
    print("\nExecutando verificação completa...")
    result = benchmark.run_full_verification(
        p4_file=Path(metadata['p4_file']),
        topology_file=Path(metadata['topology_file']),
        runtime_file=Path(metadata['runtime_file'])
    )
    
    if result.success:
        print("\n" + "="*70)
        print("ANÁLISE DETALHADA POR COMPONENTE")
        print("="*70)
        
        # Agrupa por tipo
        component_data = {}
        for metric in result.component_metrics:
            comp_type = metric.component.split(':')[0]
            if comp_type not in component_data:
                component_data[comp_type] = {
                    'times': [],
                    'memories': [],
                    'input_states': [],
                    'output_states': []
                }
            
            component_data[comp_type]['times'].append(metric.duration_seconds)
            component_data[comp_type]['memories'].append(metric.memory_peak_mb)
            component_data[comp_type]['input_states'].append(metric.input_states)
            component_data[comp_type]['output_states'].append(metric.output_states)
        
        # Imprime análise
        for comp_type, data in sorted(component_data.items()):
            print(f"\n{comp_type}:")
            print(f"  Execuções: {len(data['times'])}")
            print(f"  Tempo total: {sum(data['times']):.3f}s ({sum(data['times'])/result.total_duration_seconds*100:.1f}% do total)")
            print(f"  Tempo médio: {sum(data['times'])/len(data['times']):.3f}s")
            print(f"  Memória média: {sum(data['memories'])/len(data['memories']):.2f} MB")
            
            if max(data['input_states']) > 0:
                print(f"  Estados: {min(data['input_states'])} → {max(data['output_states'])}")
                # Calcula taxa de crescimento de estados
                total_in = sum(data['input_states'])
                total_out = sum(data['output_states'])
                if total_in > 0:
                    growth = (total_out / total_in - 1) * 100
                    print(f"  Crescimento de estados: {growth:+.1f}%")


# ============================================
# MENU INTERATIVO
# ============================================
def main():
    """Menu interativo para executar exemplos"""
    print("\n" + "="*70)
    print("P4SymTest - Exemplos de Benchmark")
    print("="*70)
    print("\nSelecione um exemplo para executar:")
    print("\n1. Escalabilidade do Parser")
    print("2. Escalabilidade do Pipeline Ingress")
    print("3. Teste de Estados Simultâneos")
    print("4. Comparação Ingress vs Egress")
    print("5. Grid Search Completo (DEMORADO)")
    print("6. Análise Detalhada por Componente")
    print("7. Executar TODOS os exemplos")
    print("0. Sair")
    
    choice = input("\nEscolha (0-7): ").strip()
    
    examples = {
        '1': example_parser_scalability,
        '2': example_ingress_scalability,
        '3': example_state_explosion,
        '4': example_ingress_vs_egress,
        '5': example_full_grid_search,
        '6': example_component_analysis,
    }
    
    if choice == '7':
        print("\nExecutando TODOS os exemplos...")
        for func in examples.values():
            func()
    elif choice in examples:
        examples[choice]()
    elif choice == '0':
        print("\nSaindo...")
        return
    else:
        print("\nOpção inválida!")
        return
    
    print("\n" + "="*70)
    print("Exemplo concluído!")
    print("="*70)


if __name__ == "__main__":
    import sys
    
    # Se executado com argumento, roda exemplo específico
    if len(sys.argv) > 1:
        example_num = sys.argv[1]
        examples = {
            '1': example_parser_scalability,
            '2': example_ingress_scalability,
            '3': example_state_explosion,
            '4': example_ingress_vs_egress,
            '5': example_full_grid_search,
            '6': example_component_analysis,
        }
        
        if example_num in examples:
            examples[example_num]()
        else:
            print(f"Erro: Exemplo {example_num} não existe")
            print("Uso: python3 benchmark_examples.py [1-6]")
    else:
        # Menu interativo
        main()