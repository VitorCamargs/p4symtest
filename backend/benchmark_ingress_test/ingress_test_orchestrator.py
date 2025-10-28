#!/usr/bin/env python3
"""
Orquestrador de Teste Isolado da Tabela Ingress (OBJETIVO 2 - COMPLETO v4)

Este script:
1. Gera P4s sintéticos com complexidade de PARSER e AÇÕES crescente.
2. Compila os P4s.
3. Executa run_parser.py para gerar a entrada real para a tabela.
4. Executa 'run_table.py' 5 VEZES para cada combinação.
5. ANALISA O STDOUT do run_table.py para contar alcançabilidade.
6. Coleta métricas e gera relatórios (CSV, Boxplots, HEATMAP, etc.).
"""

import json
import time
import subprocess
import psutil
import os
import sys
import re # Importa regex para parsing
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import List, Dict
import shutil
import logging
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns 

# --- Importa o gerador P4 ---
try:
    from synthetic_p4_generator import SyntheticP4Generator
except ImportError:
    print("Erro: Nao foi possivel encontrar 'synthetic_p4_generator.py'.")
    print("Certifique-se de que esta no mesmo diretorio.")
    sys.exit(1)

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

# --- Estrutura de Resultados ---
@dataclass
class IngressTableResult:
    id: str
    parser_states_config: int 
    parser_output_states: int 
    num_actions: int          
    run_number: int
    compile_time_s: float
    parser_time_s: float       
    table_time_s: float
    table_mem_peak_mb: float
    table_output_states: int
    success: bool             # Movido para antes dos defaults
    # --- Campos com Defaults ---
    reachable_states: int = 0 # Contado do stdout
    unreachable_states: int = 0 # Contado do stdout
    error: str = None
    params_config: Dict = field(default_factory=dict) 


# --- Classe de Execução ---

class IngressBenchmarkRunner:
    """Executa os passos do benchmark para parser e tabela ingress."""
    
    def __init__(self, workspace_dir: Path, scripts_dir: Path):
        self.workspace_dir = workspace_dir
        self.scripts_dir = scripts_dir
        
        self.p4c_cmd = "/usr/local/bin/p4c --target bmv2 --arch v1model"
        self.parser_script = scripts_dir / "run_parser.py" 
        self.table_script = scripts_dir / "run_table.py"
        
        if not self.parser_script.exists():
             raise FileNotFoundError(f"{self.parser_script} nao encontrado")
        if not self.table_script.exists():
            raise FileNotFoundError(f"{self.table_script} nao encontrado")

    def _run_command(self, cmd: list, cwd: Path, timeout=300, capture=True) -> (bool, str, str, float, float, int):
        """Executa um comando (lista), capturando output e medindo memória."""
        cmd_str = " ".join(map(str, cmd)) 
        # log.info(f"    Executando CMD: {cmd_str}") # Log reduzido
        start_time = time.time()
        stdout_pipe = subprocess.PIPE if capture else None
        stderr_pipe = subprocess.PIPE if capture else None
        return_code = -1 
        mem_peak_rss = 0
        stdout = ""
        stderr = ""

        try:
            proc = subprocess.Popen(
                cmd, cwd=cwd, 
                stdout=stdout_pipe, stderr=stderr_pipe,
                text=True, encoding='utf-8', 
            )
            
            process = None
            try:
                process = psutil.Process(proc.pid)
                while proc.poll() is None:
                    try: 
                        mem_info = process.memory_info()
                        full_mem = process.memory_full_info()
                        mem_peak_rss = max(mem_peak_rss, getattr(full_mem, 'uss', mem_info.rss)) 
                    except (psutil.NoSuchProcess, psutil.AccessDenied): 
                        break 
                    time.sleep(0.01) 
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass 

            stdout_data, stderr_data = proc.communicate(timeout=timeout)
            duration = time.time() - start_time
            return_code = proc.returncode
            # Guarda stdout/stderr mesmo se não for explicitamente "capturado" para análise de erro
            stdout = stdout_data if stdout_data else ""
            stderr = stderr_data if stderr_data else ""

            if return_code == 0:
                # Não loga warnings por padrão
                return True, stdout, stderr, duration, mem_peak_rss / (1024**2), return_code
            else:
                error_msg = f"CMD Failed (Code {return_code})"
                # Adiciona stdout/stderr à mensagem de erro sempre que falhar
                stdout_short = (stdout[:500] + '...') if len(stdout) > 500 else stdout
                stderr_short = (stderr[:500] + '...') if len(stderr) > 500 else stderr
                error_msg += f"\nSTDOUT (truncated): {stdout_short}\nSTDERR (truncated): {stderr_short}"
                return False, stdout, stderr, duration, mem_peak_rss / (1024**2), return_code
                
        except subprocess.TimeoutExpired:
            log.error("    [ERRO] Comando deu TIMEOUT")
            if process:
                try: 
                    process.kill() 
                    proc.wait() 
                except (psutil.NoSuchProcess, psutil.AccessDenied): pass
            return False, stdout, stderr, time.time() - start_time, mem_peak_rss / (1024**2), -1
        except Exception as e:
            log.error(f"    [ERRO] Comando falhou com EXCECAO: {e}", exc_info=True) 
            if process:
                try: 
                    process.kill()
                    proc.wait() 
                except (psutil.NoSuchProcess, psutil.AccessDenied): pass
            return False, stdout, stderr, time.time() - start_time, mem_peak_rss / (1024**2), -1


    def compile_p4(self, p4_file: Path, output_dir: Path) -> (bool, Path, float, str):
        log.info(f"  [Compilando] {p4_file.name}...")
        input_stem = p4_file.stem
        fsm_json_file = output_dir / f"{input_stem}.json"
        
        cmd_str = f"{self.p4c_cmd} -o {output_dir} {p4_file}" 
        
        start_time = time.time()
        try:
            # Usa subprocess.run para compilação (não precisa medir memória)
            result = subprocess.run(
                cmd_str, shell=True, cwd=p4_file.parent, capture_output=True,
                text=True, timeout=300, encoding='utf-8'
            )
            duration = time.time() - start_time
            if result.returncode == 0:
                 if result.stderr:
                     log.warning(f"    [Aviso p4c]: {result.stderr.strip()}")
                 success = True
                 output = result.stdout # Guarda stdout mesmo se sucesso (raro ter algo)
            else:
                 # Mensagem de erro combina stdout e stderr
                 output = f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
                 success = False
        except Exception as e:
            success = False
            output = str(e)
            duration = time.time() - start_time

        if not success or not fsm_json_file.exists():
            log.error(f"  ✗ Erro na compilacao: {output}")
            return False, None, duration, output # Retorna a msg de erro
            
        log.info(f"  ✓ Compilado em {duration:.3f}s. JSON: {fsm_json_file.name}")
        # Retorna o path do JSON se sucesso, erro vazio
        return True, fsm_json_file, duration, "" 


    def run_parser_step(self, fsm_json_file: Path, output_json_file: Path) -> (bool, float, int, str):
        """Executa run_parser.py e retorna o número de estados."""
        log.info(f"  [Executando Parser] {self.parser_script.name}...")
        cmd_list = ["python3", str(self.parser_script), str(fsm_json_file), str(output_json_file)]
        
        # Executa capturando a saída
        success, stdout, stderr, duration, _, _ = self._run_command(cmd_list, self.scripts_dir)
        
        if not success:
            error_msg = f"STDOUT: {stdout}\nSTDERR: {stderr}"
            log.error(f"  ✗ Erro no run_parser: {error_msg}")
            return False, duration, 0, error_msg

        parser_output_states = 0
        if output_json_file.exists():
            try:
                with open(output_json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        parser_output_states = len(data)
                    else:
                        log.warning(f"  Formato inesperado na saída do parser: {output_json_file}. Esperava lista.")
                        parser_output_states = 0 
            except json.JSONDecodeError:
                log.error(f"  ✗ Erro ao ler JSON de saida do parser: {output_json_file}")
                return False, duration, 0, "Erro JSON Parser"
        else:
            log.warning(f"  ! Arquivo de saída do parser não encontrado: {output_json_file}")
            return False, duration, 0, "Arquivo de saída do parser não encontrado"

        
        log.info(f"  ✓ Parser concluído em {duration:.3f}s. Estados gerados: {parser_output_states}")
        return True, duration, parser_output_states, ""

    # --- FUNÇÃO ATUALIZADA PARA PARSEAR STDOUT ---
    def run_table_step(self, 
                            fsm_json_file: Path, 
                            topology_file: Path,
                            runtime_config_file: Path,
                            switch_id: str,
                            table_name: str, 
                            parser_output_file: Path, 
                            table_output_file: Path) -> (bool, float, float, int, int, int, str): 
        """Executa run_table.py capturando output, memória E PARSEANDO stdout para alcançabilidade."""
        # log.info(f"  [Executando Tabela] {self.table_script.name}...") # Log reduzido
        
        cmd_list = [
            "python3", str(self.table_script), 
            str(fsm_json_file), str(topology_file), str(runtime_config_file),
            str(parser_output_file), switch_id, table_name, str(table_output_file)
        ]

        # Executa capturando stdout/stderr e memória
        success, stdout, stderr, duration, mem_peak_mb, return_code = self._run_command(
            cmd_list, self.scripts_dir, capture=True
        )
        
        # --- PARSE STDOUT PARA ALCANÇABILIDADE ---
        table_output_states = 0
        reachable = 0
        unreachable = 0
        error_msg = ""

        if stdout: # Processa stdout se ele foi capturado
            # Conta ocorrências das strings específicas
            reachable = stdout.count("-> OK: A tabela é alcançável.")
            unreachable = stdout.count("-> AVISO: Análise pulada.") 
        
        # Define a mensagem de erro se o processo falhou
        if not success:
            # Usa a saída capturada para a mensagem de erro
            error_msg = f"run_table.py falhou (Code {return_code})\nSTDOUT:{stdout}\nSTDERR:{stderr}"
            log.error(f"  ✗ {error_msg}")
        
        # Tenta ler o JSON de saída para pegar o número de estados resultantes
        # (run_table.py original gera uma lista diretamente)
        if table_output_file.exists():
            try:
                with open(table_output_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # Assume que a saída do run_table original é uma lista
                if isinstance(data, list):
                    table_output_states = len(data)
                elif isinstance(data, dict) and "output_states" in data:
                    # Tenta lidar com o formato antigo (se run_table foi modificado)
                    log.warning(f"  Formato JSON inesperado (dict) em {table_output_file.name}. Usando 'output_states'.")
                    table_output_states = len(data.get("output_states", []))
                else:
                    log.error(f"  Tipo de dado JSON inesperado ({type(data)}) em {table_output_file.name}")
                    table_output_states = 0
                    if success: # Se o processo terminou ok mas o JSON é inválido
                        success = False
                        error_msg = f"Tipo de dado JSON inesperado ({type(data)})"

            except json.JSONDecodeError as e:
                json_err_msg = f"Erro ao decodificar JSON de saida da tabela: {table_output_file} ({e})"
                log.error(f"  ✗ {json_err_msg}")
                if success: 
                   success = False
                   error_msg = json_err_msg
            except Exception as e:
                read_err_msg = f"Erro inesperado ao ler JSON: {e}"
                log.error(f"  ✗ {read_err_msg}", exc_info=True)
                if success:
                    success = False
                    error_msg = read_err_msg
        
        # Se o processo terminou ok, mas não achou o arquivo ou JSON é inválido
        elif success: 
             log.warning(f"  ! Arquivo de saída {table_output_file.name} não encontrado ou inválido, mas processo terminou com sucesso.")
             success = False 
             error_msg = "Arquivo de saida nao encontrado ou invalido"
        # --- FIM DO PARSE ---

        if success:
            log.info(f"    ✓ Tabela concluída em: {duration:.3f}s, Mem: {mem_peak_mb:.2f} MB, Estados Saída: {table_output_states}, Alcançáveis(stdout): {reachable}/{reachable+unreachable}")
        
        # Retorna os contadores baseados no stdout
        return success, duration, mem_peak_mb, table_output_states, reachable, unreachable, error_msg


# --- Orquestrador Principal ---

def main():
    log.info("="*70)
    log.info("INICIANDO BENCHMARK ISOLADO DA TABELA INGRESS (OBJETIVO 2 - COMPLETO v4)")
    log.info("Usando 'synthetic_p4_generator.py', saída real do parser e contando alcançabilidade via stdout")
    log.info("="*70)

    NUM_RUNS = 10
    log.info(f"Configurado para {NUM_RUNS} execuções por combinação.")
    switch_id_to_test = "s1"

    scripts_dir = Path("/app/workspace")
    output_base_dir = Path("/app/workspace/ingress_benchmark_run")
    
    if output_base_dir.exists():
        log.info(f"Limpando diretorio antigo: {output_base_dir}")
        shutil.rmtree(output_base_dir)
    
    p4_output_dir = output_base_dir / "synthetic_p4s"
    p4_output_dir.mkdir(parents=True, exist_ok=True)
    
    # --- CONFIGURAÇÕES DE TESTE ---
    p4_parser_states_list = [3, 6, 9, 12, 15, 18, 21, 24, 27, 30] 
    num_actions_list = [2, 5, 10, 15]     
    
    log.info(f"Eixo P4 (Parser States Config): {p4_parser_states_list}")
    log.info(f"Eixo P4 (Ações): {num_actions_list}")

    generator = SyntheticP4Generator(seed=42)
    runner = IngressBenchmarkRunner(workspace_dir=scripts_dir, scripts_dir=scripts_dir)
    results_list = []
    compiled_programs_cache = {} 
    
    total_configs = len(p4_parser_states_list) * len(num_actions_list)
    current_config = 0

    for p_states in p4_parser_states_list:
        for num_actions in num_actions_list:
            current_config += 1
            log.info("\n" + "#"*70)
            log.info(f"Processando Configuração P4 [{current_config}/{total_configs}]: Parser States={p_states}, Actions={num_actions}")
            log.info("#"*70)

            config_key = (p_states, num_actions)
            if config_key not in compiled_programs_cache:
                log.info("\n--- Fase 1: Gerando e Compilando Programa P4 ---")
                params = {
                    'parser_states': p_states, 'headers_per_state': 1, 
                    'ingress_tables': 1, 'egress_tables': 0, 
                    'actions_per_table': num_actions
                }
                try:
                    p4_meta = generator.generate_program(output_dir=p4_output_dir, **params)
                    p4_meta['params_config'] = params 
                except Exception as e:
                    log.error(f"Falha ao GERAR P4: {e}", exc_info=True)
                    results_list.append(asdict(IngressTableResult(
                        id=f"P{p_states}_A{num_actions}_ERR", parser_states_config=p_states, 
                        parser_output_states=0, num_actions=num_actions, run_number=1,
                        compile_time_s=0, parser_time_s=0, table_time_s=0, table_mem_peak_mb=0,
                        table_output_states=0, success=False, error=f"Geracao P4 falhou: {e}",
                        params_config=params
                    )))
                    continue 

                p4_file = Path(p4_meta['p4_file'])
                compile_dir = p4_output_dir / f"{p4_meta['id']}_build"
                compile_dir.mkdir(parents=True, exist_ok=True)
                
                compile_ok, fsm_file, comp_time, comp_err = runner.compile_p4(p4_file, compile_dir)
                
                if not compile_ok:
                    log.error(f"Falha ao COMPILAR P4. Pulando esta configuração.")
                    results_list.append(asdict(IngressTableResult(
                        id=p4_meta['id'], parser_states_config=p_states,
                        parser_output_states=0, num_actions=num_actions, run_number=1,
                        compile_time_s=comp_time, parser_time_s=0, table_time_s=0, table_mem_peak_mb=0,
                        table_output_states=0, success=False, error=f"Compilacao falhou: {comp_err}",
                        params_config=params
                    )))
                    continue 
                
                compiled_programs_cache[config_key] = (p4_meta, fsm_file, comp_time)
            
            else: 
                log.info("\n--- Fase 1: P4 já compilado (cache) ---")
                p4_meta, fsm_file, comp_time = compiled_programs_cache[config_key]
                compile_dir = p4_output_dir / f"{p4_meta['id']}_build" 
                params = p4_meta['params_config'] 


            # 2. Executar o Parser
            log.info("\n--- Fase 2: Executando run_parser.py ---")
            parser_output_file = compile_dir / "parser_states_output.json" 
            
            parser_ok, p_time, p_states_out, p_err = runner.run_parser_step(fsm_file, parser_output_file)

            if not parser_ok or p_states_out == 0: # Adiciona verificação de p_states_out
                 log.error(f"Falha ao executar o parser ou nenhum estado gerado. Pulando execuções da tabela.")
                 results_list.append(asdict(IngressTableResult(
                    id=p4_meta['id'], parser_states_config=p_states,
                    parser_output_states=0, num_actions=num_actions, run_number=1,
                    compile_time_s=comp_time, parser_time_s=p_time, table_time_s=0, table_mem_peak_mb=0,
                    table_output_states=0, success=False, 
                    error=p_err if p_err else "Execucao Parser falhou ou 0 estados gerados",
                    params_config=params
                 )))
                 continue 

            # 3. Executar o Benchmark da Tabela (N runs)
            log.info("\n--- Fase 3: Executando Benchmark (run_table.py) ---")
            
            table_name = "MyIngress.ingress_table_0" 
            topology_file = Path(p4_meta['topology_file'])        
            runtime_config_file = Path(p4_meta['runtime_file'])  
                    
            log.info(f"  Benchmark: {num_actions} Ações vs {p_states_out} Estados de Entrada (Reais)")
            log.info(f"  Iniciando {NUM_RUNS} execuções...")
            
            for run_i in range(1, NUM_RUNS + 1): 
                log.info(f"    -> Executando run {run_i}/{NUM_RUNS}...")
                
                table_output_file = compile_dir / f"table_output_R{run_i}.json"
                
                run_ok, t_time, t_mem, t_states, reach, unreach, t_err = runner.run_table_step(
                    fsm_json_file=fsm_file,
                    topology_file=topology_file,
                    runtime_config_file=runtime_config_file,
                    switch_id=switch_id_to_test,
                    table_name=table_name,
                    parser_output_file=parser_output_file, 
                    table_output_file=table_output_file
                )
                
                results_list.append(asdict(IngressTableResult(
                    id=f"P{p_states}_A{num_actions}", 
                    parser_states_config=p_states, 
                    parser_output_states=p_states_out, 
                    num_actions=num_actions,
                    run_number=run_i,
                    compile_time_s=comp_time if run_i == 1 else 0.0,
                    parser_time_s=p_time if run_i == 1 else 0.0, 
                    table_time_s=t_time,
                    table_mem_peak_mb=t_mem,
                    table_output_states=t_states,
                    reachable_states=reach,       
                    unreachable_states=unreach,   
                    success=run_ok,
                    error=t_err if not run_ok else None,
                    params_config=params
                )))

    # --- Análise ---
    main_analysis(results_list, output_base_dir)


def main_analysis(results_list, output_base_dir):
    """Função separada para analisar os resultados."""
    log.info("\n" + "="*70)
    log.info("Execucao concluida. Gerando analise...")
    log.info("="*70)

    if not results_list:
        log.warning("Nenhum resultado coletado. Análise não pode ser gerada.")
        return

    try:
        analysis_dir = output_base_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Salvar dados BRUTOS
        df_raw = pd.DataFrame(results_list)
        df_raw = df_raw.drop(columns=['params_config'], errors='ignore') 
        csv_raw_path = analysis_dir / "ingress_summary_raw.csv"
        df_raw.to_csv(csv_raw_path, index=False, encoding='utf-8')
        log.info(f"CSV de resultados brutos salvo em: {csv_raw_path}")

        # 2. Calcular Agregados
        success_df = df_raw[df_raw['success'] == True].copy()
        if not success_df.empty:
            log.info("Calculando estatísticas agregadas...")
            
            df_agg = success_df.groupby(['parser_states_config', 'num_actions', 'parser_output_states']).agg(
                runs_success=('success', 'count'),
                table_time_avg=('table_time_s', 'mean'),
                table_time_median=('table_time_s', 'median'),
                table_mem_peak_avg=('table_mem_peak_mb', 'mean'),
                table_output_states_avg=('table_output_states', 'mean'),
                # Usa 'first' pois os contadores devem ser os mesmos para todos os runs da mesma config
                reachable_states=('reachable_states', 'first'), 
                unreachable_states=('unreachable_states', 'first') 
            ).reset_index()
            
            # Recalcula total aqui, mais robusto
            df_agg['total_input_states_calc'] = df_agg['reachable_states'] + df_agg['unreachable_states']
            # Usa o total calculado para o percentual
            df_agg['percent_reachable'] = (df_agg['reachable_states'] / df_agg['total_input_states_calc'].replace(0, 1) * 100).fillna(0)


            csv_agg_path = analysis_dir / "ingress_summary_aggregated.csv"
            df_agg.to_csv(csv_agg_path, index=False, encoding='utf-8')
            log.info(f"CSV de resultados agregados salvo em: {csv_agg_path}")
            log.info(f"\n--- Resumo Agregado (Sucessos) ---")
            print(df_agg[[
                'parser_states_config', 'num_actions', 'parser_output_states', 'runs_success', 
                'table_time_avg', 'table_mem_peak_avg', 'table_output_states_avg', 
                'reachable_states', 'total_input_states_calc', 'percent_reachable' 
            ]].round(3).to_string(index=False))

            # 3. Plots
            log.info("Gerando gráficos (Heatmap, Boxplots, Alcançabilidade, Estados Saída)...")

            df_agg['parser_output_states'] = pd.to_numeric(df_agg['parser_output_states'])
            df_agg['num_actions'] = pd.to_numeric(df_agg['num_actions'])
            df_agg['table_time_avg'] = pd.to_numeric(df_agg['table_time_avg'])
            success_df['parser_output_states'] = pd.to_numeric(success_df['parser_output_states'])
            success_df['num_actions'] = pd.to_numeric(success_df['num_actions'])

            # Heatmap
            try:
                # Usa 'parser_output_states' como coluna
                heatmap_data = df_agg.pivot_table(
                    index='num_actions', columns='parser_output_states', values='table_time_avg'
                )
                plt.figure(figsize=(10, 7))
                sns.heatmap(heatmap_data, annot=True, fmt=".3f", linewidths=.5, cmap="viridis")
                plt.title('Tempo Médio de Execução Tabela (s)')
                plt.xlabel('Estados Reais de Entrada (Parser Output)')
                plt.ylabel('Número de Ações na Tabela')
                plt.tight_layout()
                plt.savefig(analysis_dir / "plot_heatmap_time_vs_actions_states.pdf")
                plt.close()
            except Exception as e:
                log.error(f"Erro ao gerar heatmap: {e}")

            # Boxplots Tempo vs (Ações, Estados Reais)
            try:
                plt.figure(figsize=(max(12, len(success_df['parser_output_states'].unique()) * 1.5), 8)) # Ajusta largura
                # Cria grupo com base nos estados reais do parser
                success_df['action_state_group'] = 'A' + success_df['num_actions'].astype(str) + '_S' + success_df['parser_output_states'].astype(str)
                sorted_groups = success_df.sort_values(by=['num_actions','parser_output_states'])['action_state_group'].unique()
                
                # Usa matplotlib diretamente para mais controle
                # success_df.boxplot(...) # Método pandas pode ser limitado
                
                # Agrupa dados para boxplot
                grouped_data = [success_df[success_df['action_state_group'] == group]['table_time_s'].values for group in sorted_groups]
                
                plt.boxplot(grouped_data, labels=sorted_groups, patch_artist=True)
                plt.xticks(rotation=90) # Rotação 90 para caber mais labels
                plt.grid(True, axis='y') # Grid apenas no eixo Y
                
                plt.title('Distribuição Tempo Exec Tabela vs (Ações, Estados Reais)')
                plt.xlabel('Configuração (Ações / Estados Reais Parser)')
                plt.ylabel('Tempo (s)')
                plt.tight_layout() 
                plt.savefig(analysis_dir / "plot_boxplot_time_vs_actions_and_parser_states.pdf")
                plt.close()
            except Exception as e:
                log.error(f"Erro ao gerar boxplot combinado: {e}")

            # Gráfico de Alcançabilidade
            try:
                plt.figure(figsize=(10, 6))
                # Usa 'parser_output_states' como índice
                reach_pivot = df_agg.pivot_table(index='parser_output_states', columns='num_actions', values='percent_reachable')
                reach_pivot.plot(marker='o', ax=plt.gca()) # Plota no eixo atual
                plt.title('Percentual de Estados Alcançáveis vs Estados de Entrada')
                plt.xlabel('Numero de Estados Reais (Saída do Parser)')
                plt.ylabel('% Alcançável')
                plt.grid(True)
                plt.legend(title='Num Ações')
                plt.ylim(0, 105) 
                plt.tight_layout()
                plt.savefig(analysis_dir / "plot_reachability_vs_parser_states.pdf")
                plt.close()
            except Exception as e:
                log.error(f"Erro ao gerar gráfico de alcançabilidade: {e}")
            
            # Gráfico Estados Saída da Tabela
            try:
                plt.figure(figsize=(10, 6))
                # Usa 'parser_output_states' como índice
                output_pivot = df_agg.pivot_table(index='parser_output_states', columns='num_actions', values='table_output_states_avg')
                output_pivot.plot(marker='x', ax=plt.gca()) # Plota no eixo atual
                plt.title('Estados de Saída da Tabela vs Estados de Entrada')
                plt.xlabel('Numero de Estados Reais (Saída do Parser)')
                plt.ylabel('Estados de Saída Médios (Tabela)')
                plt.grid(True)
                plt.legend(title='Num Ações')
                plt.tight_layout()
                plt.savefig(analysis_dir / "plot_table_output_vs_parser_states.pdf")
                plt.close()
            except Exception as e:
                log.error(f"Erro ao gerar gráfico de estados de saída da tabela: {e}")


            log.info(f"Graficos salvos em: {analysis_dir} (como PDF)")
        
        else:
            log.warning("Nenhum teste executado com sucesso.")

        # Log de Erros
        error_df = df_raw[df_raw['success'] == False]
        if not error_df.empty:
            log.warning(f"\n--- Erros ---")
            pd.set_option('display.max_colwidth', 120)
            print(error_df[['id', 'run_number', 'error']].to_string(index=False))

    except Exception as e:
        log.error(f"Falha ao gerar analise: {e}", exc_info=True)

    log.info("Benchmark da Tabela Ingress concluído.")


if __name__ == "__main__":
    os.chdir(Path(__file__).parent.resolve())
    main()