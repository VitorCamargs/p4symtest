#!/usr/bin/env python3
"""
Analisador e Visualizador de Resultados de Benchmark P4SymTest
Gera gráficos e estatísticas detalhadas
"""

import json
import matplotlib
matplotlib.use('Agg')  # Backend não-interativo para Docker
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
from typing import Dict, List
import pandas as pd
from datetime import datetime


class BenchmarkAnalyzer:
    """Analisa resultados de benchmark e gera visualizações"""
    
    def __init__(self, results_file: Path):
        self.results_file = results_file
        with open(results_file, 'r') as f:
            self.data = json.load(f)
        
        self.results = self.data['results']
        self.successful = [r for r in self.results if r['success']]
    
    def generate_all_plots(self, output_dir: Path):
        """Gera todos os gráficos de análise"""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"Gerando visualizações em {output_dir}...")
        
        try:
            # 1. Tempo vs Complexidade
            self._plot_time_vs_complexity(output_dir / "time_vs_complexity.png")
            print("  ✓ time_vs_complexity.png")
            
            # 2. Memória vs Complexidade
            self._plot_memory_vs_complexity(output_dir / "memory_vs_complexity.png")
            print("  ✓ memory_vs_complexity.png")
            
            # 3. Breakdown por Componente
            self._plot_component_breakdown(output_dir / "component_breakdown.png")
            print("  ✓ component_breakdown.png")
            
            # 4. Tempo acumulado por Pipeline Stage
            self._plot_cumulative_time(output_dir / "cumulative_time.png")
            print("  ✓ cumulative_time.png")
            
            # 5. Escalabilidade (Estados vs Tempo)
            self._plot_scalability(output_dir / "scalability.png")
            print("  ✓ scalability.png")
            
            # 6. Distribuição de Tempos
            self._plot_time_distribution(output_dir / "time_distribution.png")
            print("  ✓ time_distribution.png")
            
            # 7. Heatmap de Performance
            self._plot_performance_heatmap(output_dir / "performance_heatmap.png")
            print("  ✓ performance_heatmap.png")
            
            print(f"\n✓ 7 gráficos gerados com sucesso!")
        except Exception as e:
            print(f"\n✗ Erro ao gerar gráficos: {e}")
            import traceback
            traceback.print_exc()
    
    def _plot_time_vs_complexity(self, output_file: Path):
        """Gráfico: Tempo total vs Complexidade do programa"""
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        fig.suptitle('Tempo de Execução vs Complexidade do Programa', fontsize=14, fontweight='bold')
        
        # Parser States
        x = [r['parser_states_count'] for r in self.successful]
        y = [r['total_duration_seconds'] for r in self.successful]
        axes[0].scatter(x, y, alpha=0.6, s=100)
        axes[0].set_xlabel('Parser States')
        axes[0].set_ylabel('Tempo Total (s)')
        axes[0].set_title('Parser States')
        axes[0].grid(True, alpha=0.3)
        
        # Ingress Tables
        x = [r['ingress_tables_count'] for r in self.successful]
        y = [r['total_duration_seconds'] for r in self.successful]
        axes[1].scatter(x, y, alpha=0.6, s=100, color='orange')
        axes[1].set_xlabel('Ingress Tables')
        axes[1].set_ylabel('Tempo Total (s)')
        axes[1].set_title('Ingress Tables')
        axes[1].grid(True, alpha=0.3)
        
        # Egress Tables
        x = [r['egress_tables_count'] for r in self.successful]
        y = [r['total_duration_seconds'] for r in self.successful]
        axes[2].scatter(x, y, alpha=0.6, s=100, color='green')
        axes[2].set_xlabel('Egress Tables')
        axes[2].set_ylabel('Tempo Total (s)')
        axes[2].set_title('Egress Tables')
        axes[2].grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()
    
    def _plot_memory_vs_complexity(self, output_file: Path):
        """Gráfico: Uso de memória vs Complexidade"""
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        fig.suptitle('Pico de Memória vs Complexidade do Programa', fontsize=14, fontweight='bold')
        
        # Parser States
        x = [r['parser_states_count'] for r in self.successful]
        y = [r['total_memory_peak_mb'] for r in self.successful]
        axes[0].scatter(x, y, alpha=0.6, s=100, color='purple')
        axes[0].set_xlabel('Parser States')
        axes[0].set_ylabel('Memória Pico (MB)')
        axes[0].set_title('Parser States')
        axes[0].grid(True, alpha=0.3)
        
        # Ingress Tables
        x = [r['ingress_tables_count'] for r in self.successful]
        y = [r['total_memory_peak_mb'] for r in self.successful]
        axes[1].scatter(x, y, alpha=0.6, s=100, color='purple')
        axes[1].set_xlabel('Ingress Tables')
        axes[1].set_ylabel('Memória Pico (MB)')
        axes[1].set_title('Ingress Tables')
        axes[1].grid(True, alpha=0.3)
        
        # Egress Tables
        x = [r['egress_tables_count'] for r in self.successful]
        y = [r['total_memory_peak_mb'] for r in self.successful]
        axes[2].scatter(x, y, alpha=0.6, s=100, color='purple')
        axes[2].set_xlabel('Egress Tables')
        axes[2].set_ylabel('Memória Pico (MB)')
        axes[2].set_title('Egress Tables')
        axes[2].grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()
    
    def _plot_component_breakdown(self, output_file: Path):
        """Gráfico: Breakdown de tempo por tipo de componente"""
        # Agrega tempos por tipo de componente
        component_times = {}
        
        for result in self.successful:
            for metric in result['component_metrics']:
                comp_type = metric['component'].split(':')[0]
                if comp_type not in component_times:
                    component_times[comp_type] = []
                component_times[comp_type].append(metric['duration_seconds'])
        
        if not component_times:
            print("  ⚠ Sem dados para component_breakdown")
            return
        
        # Calcula médias
        component_avg = {k: np.mean(v) for k, v in component_times.items()}
        
        # Gráfico de barras
        fig, ax = plt.subplots(figsize=(10, 6))
        
        components = sorted(component_avg.keys())
        values = [component_avg[c] for c in components]
        colors = plt.cm.Set3(np.linspace(0, 1, len(components)))
        
        bars = ax.bar(components, values, color=colors, alpha=0.8)
        ax.set_ylabel('Tempo Médio (s)', fontsize=12)
        ax.set_xlabel('Tipo de Componente', fontsize=12)
        ax.set_title('Tempo Médio de Execução por Tipo de Componente', fontsize=14, fontweight='bold')
        ax.grid(axis='y', alpha=0.3)
        
        # Adiciona valores no topo das barras
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{height:.3f}s',
                   ha='center', va='bottom', fontsize=9)
        
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()
    
    def _plot_cumulative_time(self, output_file: Path):
        """Gráfico: Tempo acumulado ao longo do pipeline"""
        fig, ax = plt.subplots(figsize=(12, 6))
        
        # Para cada programa, plota linha de tempo acumulado
        for result in self.successful[:10]:  # Primeiros 10 para legibilidade
            times = []
            cumulative = 0
            
            for metric in result['component_metrics']:
                if metric['success']:
                    cumulative += metric['duration_seconds']
                    times.append(cumulative)
            
            if times:
                ax.plot(range(len(times)), times, marker='o', alpha=0.6, 
                       label=result['program_id'][:15])
        
        ax.set_xlabel('Estágio do Pipeline', fontsize=12)
        ax.set_ylabel('Tempo Acumulado (s)', fontsize=12)
        ax.set_title('Tempo Acumulado ao Longo do Pipeline de Verificação', 
                    fontsize=14, fontweight='bold')
        ax.legend(loc='upper left', fontsize=8)
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()
    
    def _plot_scalability(self, output_file: Path):
        """Gráfico: Escalabilidade (Estados simultâneos vs Tempo)"""
        fig, ax = plt.subplots(figsize=(10, 6))
        
        # Para cada programa, pega o número máximo de estados simultâneos e tempo
        max_states = []
        times = []
        
        for result in self.successful:
            # Encontra o máximo de estados em qualquer ponto
            max_s = 0
            for metric in result['component_metrics']:
                max_s = max(max_s, metric.get('input_states', 0), 
                          metric.get('output_states', 0))
            
            if max_s > 0:
                max_states.append(max_s)
                times.append(result['total_duration_seconds'])
        
        if max_states:
            ax.scatter(max_states, times, s=100, alpha=0.6, color='red')
            ax.set_xlabel('Máximo de Estados Simultâneos', fontsize=12)
            ax.set_ylabel('Tempo Total (s)', fontsize=12)
            ax.set_title('Escalabilidade: Estados Simultâneos vs Tempo de Execução', 
                        fontsize=14, fontweight='bold')
            ax.grid(True, alpha=0.3)
            
            # Linha de tendência
            if len(max_states) > 1:
                z = np.polyfit(max_states, times, 2)
                p = np.poly1d(z)
                x_line = np.linspace(min(max_states), max(max_states), 100)
                ax.plot(x_line, p(x_line), "--", alpha=0.5, color='red', 
                       label='Tendência (poly2)')
                ax.legend()
        
        plt.tight_layout()
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()
    
    def _plot_time_distribution(self, output_file: Path):
        """Gráfico: Distribuição de tempos de execução"""
        fig, axes = plt.subplots(2, 2, figsize=(12, 10))
        fig.suptitle('Distribuição de Tempos de Execução', fontsize=14, fontweight='bold')
        
        # Total
        times = [r['total_duration_seconds'] for r in self.successful]
        if times:
            axes[0, 0].hist(times, bins=15, alpha=0.7, color='steelblue', edgecolor='black')
            axes[0, 0].set_xlabel('Tempo Total (s)')
            axes[0, 0].set_ylabel('Frequência')
            axes[0, 0].set_title('Tempo Total')
            axes[0, 0].axvline(np.mean(times), color='red', linestyle='--', label=f'Média: {np.mean(times):.2f}s')
            axes[0, 0].legend()
        
        # Parser
        parser_times = []
        for r in self.successful:
            for m in r['component_metrics']:
                if m['component'] == 'Parser':
                    parser_times.append(m['duration_seconds'])
        
        if parser_times:
            axes[0, 1].hist(parser_times, bins=15, alpha=0.7, color='green', edgecolor='black')
            axes[0, 1].set_xlabel('Tempo (s)')
            axes[0, 1].set_ylabel('Frequência')
            axes[0, 1].set_title('Parser')
            axes[0, 1].axvline(np.mean(parser_times), color='red', linestyle='--', 
                             label=f'Média: {np.mean(parser_times):.3f}s')
            axes[0, 1].legend()
        
        # Ingress (agregado)
        ingress_times = []
        for r in self.successful:
            for m in r['component_metrics']:
                if 'Ingress:' in m['component']:
                    ingress_times.append(m['duration_seconds'])
        
        if ingress_times:
            axes[1, 0].hist(ingress_times, bins=15, alpha=0.7, color='orange', edgecolor='black')
            axes[1, 0].set_xlabel('Tempo por Tabela (s)')
            axes[1, 0].set_ylabel('Frequência')
            axes[1, 0].set_title('Tabelas Ingress')
            axes[1, 0].axvline(np.mean(ingress_times), color='red', linestyle='--',
                             label=f'Média: {np.mean(ingress_times):.3f}s')
            axes[1, 0].legend()
        
        # Egress (agregado)
        egress_times = []
        for r in self.successful:
            for m in r['component_metrics']:
                if 'Egress:' in m['component']:
                    egress_times.append(m['duration_seconds'])
        
        if egress_times:
            axes[1, 1].hist(egress_times, bins=15, alpha=0.7, color='purple', edgecolor='black')
            axes[1, 1].set_xlabel('Tempo por Tabela (s)')
            axes[1, 1].set_ylabel('Frequência')
            axes[1, 1].set_title('Tabelas Egress')
            axes[1, 1].axvline(np.mean(egress_times), color='red', linestyle='--',
                             label=f'Média: {np.mean(egress_times):.3f}s')
            axes[1, 1].legend()
        
        plt.tight_layout()
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()
    
    def _plot_performance_heatmap(self, output_file: Path):
        """Gráfico: Heatmap de performance (Ingress x Egress)"""
        # Cria matriz de performance
        ingress_vals = sorted(set(r['ingress_tables_count'] for r in self.successful))
        egress_vals = sorted(set(r['egress_tables_count'] for r in self.successful))
        
        if not ingress_vals or not egress_vals:
            print("  ⚠ Dados insuficientes para heatmap")
            return
        
        # Matriz de tempos
        time_matrix = np.zeros((len(egress_vals), len(ingress_vals)))
        count_matrix = np.zeros((len(egress_vals), len(ingress_vals)))
        
        for r in self.successful:
            i_idx = ingress_vals.index(r['ingress_tables_count'])
            e_idx = egress_vals.index(r['egress_tables_count'])
            time_matrix[e_idx, i_idx] += r['total_duration_seconds']
            count_matrix[e_idx, i_idx] += 1
        
        # Média onde há dados
        with np.errstate(divide='ignore', invalid='ignore'):
            avg_matrix = np.divide(time_matrix, count_matrix)
            avg_matrix[np.isnan(avg_matrix)] = 0
        
        # Plotagem
        fig, ax = plt.subplots(figsize=(10, 8))
        im = ax.imshow(avg_matrix, cmap='YlOrRd', aspect='auto')
        
        ax.set_xticks(range(len(ingress_vals)))
        ax.set_yticks(range(len(egress_vals)))
        ax.set_xticklabels(ingress_vals)
        ax.set_yticklabels(egress_vals)
        
        ax.set_xlabel('Número de Tabelas Ingress', fontsize=12)
        ax.set_ylabel('Número de Tabelas Egress', fontsize=12)
        ax.set_title('Heatmap de Tempo de Execução (s)', fontsize=14, fontweight='bold')
        
        # Adiciona valores nas células
        for i in range(len(egress_vals)):
            for j in range(len(ingress_vals)):
                if count_matrix[i, j] > 0:
                    ax.text(j, i, f'{avg_matrix[i, j]:.2f}',
                           ha="center", va="center", color="black", fontsize=9)
        
        # Colorbar
        cbar = plt.colorbar(im, ax=ax)
        cbar.set_label('Tempo Médio (s)', rotation=270, labelpad=20)
        
        plt.tight_layout()
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()
    
    def generate_summary_table(self, output_file: Path):
        """Gera tabela CSV com resumo dos resultados"""
        rows = []
        
        for r in self.successful:
            row = {
                'Program': r['program_id'],
                'Parser_States': r['parser_states_count'],
                'Ingress_Tables': r['ingress_tables_count'],
                'Egress_Tables': r['egress_tables_count'],
                'Total_Time_s': round(r['total_duration_seconds'], 3),
                'Memory_Peak_MB': round(r['total_memory_peak_mb'], 2),
                'Components_Executed': len(r['component_metrics'])
            }
            
            # Adiciona tempos por componente
            for metric in r['component_metrics']:
                comp_name = metric['component'].replace(':', '_').replace('.', '_')
                row[f'{comp_name}_time_s'] = round(metric['duration_seconds'], 3)
                row[f'{comp_name}_input_states'] = metric['input_states']
                row[f'{comp_name}_output_states'] = metric['output_states']
            
            rows.append(row)
        
        df = pd.DataFrame(rows)
        df.to_csv(output_file, index=False)
        print(f"✓ Tabela CSV salva em: {output_file}")
    
    def generate_latex_table(self, output_file: Path):
        """Gera tabela LaTeX para artigo/relatório"""
        latex = r"""\begin{table}[h]
\centering
\caption{Resultados de Benchmark do P4SymTest}
\label{tab:benchmark}
\begin{tabular}{|l|c|c|c|c|c|}
\hline
\textbf{Programa} & \textbf{Parser} & \textbf{Ingress} & \textbf{Egress} & \textbf{Tempo (s)} & \textbf{Mem (MB)} \\
 & \textbf{States} & \textbf{Tables} & \textbf{Tables} & & \\
\hline
"""
        
        for r in self.successful:
            latex += f"{r['program_id']} & "
            latex += f"{r['parser_states_count']} & "
            latex += f"{r['ingress_tables_count']} & "
            latex += f"{r['egress_tables_count']} & "
            latex += f"{r['total_duration_seconds']:.2f} & "
            latex += f"{r['total_memory_peak_mb']:.1f} \\\\\n"
        
        # Linha de média
        if self.successful:
            avg_time = np.mean([r['total_duration_seconds'] for r in self.successful])
            avg_mem = np.mean([r['total_memory_peak_mb'] for r in self.successful])
            
            latex += r"\hline" + "\n"
            latex += f"\\textbf{{Média}} & - & - & - & {avg_time:.2f} & {avg_mem:.1f} \\\\\n"
        
        latex += r"\hline" + "\n"
        latex += r"""\end{tabular}
\end{table}"""
        
        with open(output_file, 'w') as f:
            f.write(latex)
        
        print(f"✓ Tabela LaTeX salva em: {output_file}")
    
    def print_detailed_stats(self):
        """Imprime estatísticas detalhadas no console"""
        print("\n" + "="*70)
        print("ESTATÍSTICAS DETALHADAS DO BENCHMARK")
        print("="*70)
        
        summary = self.data['summary']
        print(f"\nResumo Geral:")
        print(f"  Programas totais: {summary['total_programs']}")
        print(f"  Bem-sucedidos: {summary['successful']}")
        print(f"  Falhados: {summary['failed']}")
        print(f"  Tempo total: {summary['total_duration_seconds']:.2f}s")
        print(f"  Tempo médio: {summary['avg_duration_seconds']:.2f}s")
        print(f"  Memória máxima: {summary['max_memory_mb']:.2f} MB")
        
        # Estatísticas de tempo por tipo de componente
        component_times = {}
        for r in self.successful:
            for m in r['component_metrics']:
                comp_type = m['component'].split(':')[0]
                if comp_type not in component_times:
                    component_times[comp_type] = []
                component_times[comp_type].append(m['duration_seconds'])
        
        if component_times:
            print(f"\nTempo por Tipo de Componente (média ± desvio):")
            for comp, times in sorted(component_times.items()):
                mean = np.mean(times)
                std = np.std(times)
                print(f"  {comp:20s}: {mean:.3f}s ± {std:.3f}s (n={len(times)})")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Uso: python3 benchmark_analyzer.py <benchmark_results.json>")
        print("\nExemplo:")
        print("  python3 benchmark_analyzer.py synthetic_programs/benchmark_results.json")
        sys.exit(1)
    
    results_file = Path(sys.argv[1])
    
    if not results_file.exists():
        print(f"Erro: Arquivo de resultados não encontrado: {results_file}")
        sys.exit(1)
    
    # Cria analisador
    analyzer = BenchmarkAnalyzer(results_file)
    
    # Diretório de saída para gráficos
    output_dir = results_file.parent / "analysis"
    
    # Gera todas as análises
    print("Iniciando análise de resultados...")
    
    analyzer.print_detailed_stats()
    analyzer.generate_all_plots(output_dir)
    analyzer.generate_summary_table(output_dir / "summary.csv")
    analyzer.generate_latex_table(output_dir / "table.tex")
    
    print(f"\n✓ Análise completa!")
    print(f"  Gráficos salvos em: {output_dir}")
    print(f"  Tabela CSV: {output_dir / 'summary.csv'}")
    print(f"  Tabela LaTeX: {output_dir / 'table.tex'}")