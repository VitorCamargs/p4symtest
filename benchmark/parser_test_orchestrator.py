#!/usr/bin/env python3
"""
Orquestrador de Teste Isolado do Parser (Com Múltiplas Execuções e Boxplot)

Este script:
1. Usa o 'synthetic_p4_generator.py' para criar programas P4.
2. Compila o P4 (1 vez por configuração).
3. Executa o 'run_parser.py' 5 VEZES por configuração.
4. Coleta métricas e calcula médias/medianas.
5. Gera relatórios (CSV e gráficos BOXPLOT) baseados nos dados brutos.
"""

import json
import time
import subprocess
import psutil
import os
import sys
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict
import shutil
import logging

# --- Importa os scripts existentes do benchmark ---
try:
    from synthetic_p4_generator import SyntheticP4Generator
    from benchmark_analyzer import BenchmarkAnalyzer
except ImportError:
    print("Erro: Nao foi possivel encontrar 'synthetic_p4_generator.py' ou 'benchmark_analyzer.py'.")
    print("Certifique-se de que estao no mesmo diretorio.")
    sys.exit(1)

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

# --- Estrutura de Resultados ---
@dataclass
class ParserOnlyResult:
    id: str
    params: Dict
    run_number: int              # Qual execução (1 a 5)
    compile_time_s: float      # Tempo de compilação (só > 0 na run 1)
    parser_time_s: float       # Tempo de execução do parser
    parser_mem_peak_mb: float  # Pico de memória
    parser_output_states: int  # Estados de saída
    success: bool
    error: str = None

# --- Classe de Execução ---

class ParserBenchmarkRunner:
    """Executa apenas os passos de compilação e análise do parser."""
    
    def __init__(self, workspace_dir: Path, scripts_dir: Path):
        self.workspace_dir = workspace_dir
        self.scripts_dir = scripts_dir
        
        self.p4c_cmd = "/usr/local/bin/p4c --target bmv2 --arch v1model"
        self.parser_script = scripts_dir / "run_parser.py"
        
        if not self.parser_script.exists():
            log.error(f"Erro critico: 'run_parser.py' nao encontrado em {self.scripts_dir}")
            raise FileNotFoundError(f"{self.parser_script} nao encontrado")

    def _run_command(self, cmd: str, cwd: Path, timeout=300) -> (bool, str, float):
        start_time = time.time()
        try:
            result = subprocess.run(
                cmd, shell=True, cwd=cwd, capture_output=True,
                text=True, timeout=timeout, encoding='utf-8'
            )
            duration = time.time() - start_time
            
            if result.returncode == 0:
                if result.stderr:
                    log.warning(f"    [Aviso p4c]: {result.stderr.strip()}")
                return True, result.stdout, duration
            else:
                error_msg = f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
                return False, error_msg.strip(), duration
                
        except subprocess.TimeoutExpired:
            log.error("    [ERRO] Comando deu TIMEOUT")
            return False, "Timeout Expirado", time.time() - start_time
        except Exception as e:
            log.error(f"    [ERRO] Comando falhou com EXCECAO: {e}")
            return False, str(e), time.time() - start_time

    def _compile_p4(self, p4_file: Path, output_dir: Path) -> (bool, Path, float, str):
        log.info(f"  [Compilando] {p4_file.name}...")
        
        input_stem = p4_file.stem
        fsm_json_file = output_dir / f"{input_stem}.json"

        cmd = f"{self.p4c_cmd} -o {output_dir} {p4_file}"
        
        success, output, duration = self._run_command(cmd, p4_file.parent)
        
        if not success or not fsm_json_file.exists():
            log.error(f"  ✗ Erro na compilacao (ou arquivo JSON nao encontrado): {output}")
            return False, None, duration, output
            
        log.info(f"  ✓ Compilado em {duration:.3f}s. JSON: {fsm_json_file.name}")
        return True, fsm_json_file, duration, ""

    def _run_parser(self, fsm_json_file: Path, output_json_file: Path) -> (bool, float, float, int, str):
        cmd_list = ["python3", str(self.parser_script), str(fsm_json_file), str(output_json_file)]
        
        process = None
        mem_peak = 0
        start_time = time.time()
        
        try:
            proc = subprocess.Popen(
                cmd_list, cwd=self.scripts_dir,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding='utf-8'
            )
            process = psutil.Process(proc.pid)
            
            while proc.poll() is None:
                try:
                    mem_info = process.memory_info()
                    mem_peak = max(mem_peak, mem_info.rss)
                except psutil.NoSuchProcess: break
                time.sleep(0.01)

            stdout, stderr = proc.communicate(timeout=300)
            duration = time.time() - start_time
            
            if proc.returncode != 0:
                log.error(f"  ✗ Erro no run_parser: {stderr}")
                return False, duration, mem_peak / (1024**2), 0, stderr

            output_states = 0
            if output_json_file.exists():
                try:
                    with open(output_json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        output_states = len(data) if isinstance(data, list) else 0
                except json.JSONDecodeError:
                    log.error(f"  ✗ Erro ao ler JSON de saida: {output_json_file}")
                    return False, duration, mem_peak / (1024**2), 0, "Erro JSON"
            
            return True, duration, mem_peak / (1024**2), output_states, ""

        except subprocess.TimeoutExpired:
            if process:
                try: process.kill() 
                except: pass
            return False, time.time() - start_time, mem_peak / (1024**2), 0, "Timeout Expirado"
        except Exception as e:
            if process:
                try: process.kill()
                except: pass
            return False, time.time() - start_time, mem_peak / (1024**2), 0, str(e)


# --- Orquestrador Principal ---

def main():
    log.info("="*70)
    log.info("INICIANDO BENCHMARK ISOLADO DO PARSER")
    log.info("Usando 'synthetic_p4_generator.py'")
    log.info("="*70)

    NUM_RUNS = 10 
    log.info(f"Configurado para {NUM_RUNS} execuções por teste.")

    scripts_dir = Path("/app/workspace")
    output_base_dir = Path("/app/workspace/parser_benchmark_run")
    
    if output_base_dir.exists():
        log.info(f"Limpando diretorio antigo: {output_base_dir}")
        shutil.rmtree(output_base_dir)
    
    p4_output_dir = output_base_dir / "synthetic_p4s"
    p4_output_dir.mkdir(parents=True, exist_ok=True)
    
    # Configurações de teste (passo consistente)
    test_configs = [
        (3, 2),    
        (6, 2),    
        (9, 2),    
        (12, 2),   
        (15, 2),   
        (18, 2),   
        (21, 2), 
        (24, 2),
        (27, 2),
        (30, 2),  
    ]

    log.info(f"Gerando {len(test_configs)} programas P4...")
    generator = SyntheticP4Generator(seed=42)
    all_metadata = []

    for p_states, h_per_state in test_configs:
        params = {
            'parser_states': p_states, 
            'headers_per_state': h_per_state,
            'ingress_tables': 1, # Mínimo
            'egress_tables': 1,  # Mínimo
            'actions_per_table': 1 # Mínimo
        }
        try:
            meta = generator.generate_program(
                parser_states=p_states,
                headers_per_state=h_per_state,
                ingress_tables=params['ingress_tables'],
                egress_tables=params['egress_tables'],
                actions_per_table=params['actions_per_table'],
                output_dir=p4_output_dir
            )
            meta['params'] = params
            all_metadata.append(meta)
        except Exception as e:
            log.error(f"Erro ao gerar P4 para config {params}: {e}", exc_info=True)

    log.info(f"Programas gerados. Iniciando execucao...")
    
    runner = ParserBenchmarkRunner(workspace_dir=scripts_dir, scripts_dir=scripts_dir)
    results_list = []

    for i, meta in enumerate(all_metadata):
        log.info("\n" + "-"*60)
        log.info(f"Processando Teste [{i+1}/{len(all_metadata)}]: {meta['id']}")
        log.info(f"Params: {meta['params']}")
        log.info("-"*(60))
        
        # 1. Compilar P4
        p4_file = Path(meta['p4_file'])
        compile_dir = p4_file.parent / f"{meta['id']}_build"
        compile_dir.mkdir(parents=True, exist_ok=True)
        
        compile_ok, fsm_file, comp_time, comp_err = runner._compile_p4(p4_file, compile_dir)
        
        if not compile_ok:
            log.error(f"Falha na compilação, pulando este teste.")
            result = ParserOnlyResult(
                id=meta['id'], params=meta['params'], run_number=1,
                compile_time_s=comp_time, parser_time_s=0, parser_mem_peak_mb=0,
                parser_output_states=0, success=False, error=f"Compilacao falhou: {comp_err}"
            )
            results_list.append(asdict(result))
            continue
            
        # 2. Loop de Execução do Parser
        log.info(f"  Iniciando {NUM_RUNS} execuções do run_parser.py...")
        parser_output_file = compile_dir / "parser_states_output.json"
        
        for run_i in range(1, NUM_RUNS + 1):
            log.info(f"    -> Executando run {run_i}/{NUM_RUNS}...")
            
            parse_ok, p_time, p_mem, p_states, p_err = runner._run_parser(fsm_file, parser_output_file)
            
            if not parse_ok:
                log.warning(f"    ✗ Run {run_i} falhou: {p_err}")
                
            result = ParserOnlyResult(
                id=meta['id'],
                params=meta['params'],
                run_number=run_i,
                compile_time_s=comp_time if run_i == 1 else 0.0,
                parser_time_s=p_time,
                parser_mem_peak_mb=p_mem,
                parser_output_states=p_states,
                success=parse_ok,
                error=p_err if not parse_ok else None
            )
            results_list.append(asdict(result))

    # --- Análise ---
    log.info("\n" + "="*70)
    log.info("Execucao concluida. Gerando analise...")
    log.info("="*70)

    try:
        analysis_dir = output_base_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        
        import pandas as pd
        
        # 1. Salvar dados BRUTOS
        df_raw = pd.DataFrame(results_list)
        df_raw['parser_states'] = df_raw['params'].apply(lambda x: x.get('parser_states'))
        
        csv_raw_path = analysis_dir / "parser_summary_raw.csv"
        df_raw.to_csv(csv_raw_path, index=False, encoding='utf-8')
        log.info(f"CSV de resultados brutos (todas execuções) salvo em: {csv_raw_path}")

        # 2. Calcular Agregados
        success_df = df_raw[df_raw['success'] == True].copy()
        if not success_df.empty:
            log.info("Calculando estatísticas agregadas (média, mediana, etc.)...")
            
            df_agg = success_df.groupby('parser_states').agg(
                runs_success=('success', 'count'),
                parser_time_avg=('parser_time_s', 'mean'),
                parser_time_median=('parser_time_s', 'median'),
                parser_mem_peak_avg=('parser_mem_peak_mb', 'mean'),
                parser_output_states=('parser_output_states', 'first')
            ).reset_index()

            csv_agg_path = analysis_dir / "parser_summary_aggregated.csv"
            df_agg.to_csv(csv_agg_path, index=False, encoding='utf-8')
            log.info(f"CSV de resultados agregados salvo em: {csv_agg_path}")

            # 3. Plots
            import matplotlib.pyplot as plt
            
            log.info("Gerando gráficos (Boxplot e Explosão de Estados)...")
            
            # Boxplot
            plt.figure(figsize=(12, 7))
            
            success_df['parser_states'] = pd.to_numeric(success_df['parser_states'])
            success_df = success_df.sort_values(by='parser_states')
            
            # --- INÍCIO DA MODIFICAÇÃO: Salva como PDF ---
            # Adiciona patch_artist=True para preencher as caixas
            success_df.boxplot(column='parser_time_s', by='parser_states', grid=True, patch_artist=True)
            
            plt.title('Escalabilidade Parser: Distribuição do Tempo (5 execuções)')
            plt.suptitle('') 
            plt.xlabel('Numero de Estados do Parser')
            plt.ylabel('Tempo (s)')
            plt.savefig(analysis_dir / "plot_time_vs_states_boxplot.pdf") # <--- MUDADO AQUI
            plt.close()

            # Gráfico de Estados de Saída
            df_agg = df_agg.sort_values(by='parser_states')
            plt.figure(figsize=(10, 6))
            plt.plot(df_agg['parser_states'], df_agg['parser_output_states'], marker='x', color='r')
            plt.title('Escalabilidade Parser: Explosao de Estados')
            plt.xlabel('Numero de Estados do Parser (Entrada)')
            plt.ylabel('Numero de Estados Simbolicos (Saida)')
            plt.grid(True)
            plt.savefig(analysis_dir / "plot_states_vs_states.pdf") # <--- MUDADO AQUI
            plt.close()
            # --- FIM DA MODIFICAÇÃO ---
            
            log.info(f"Graficos salvos em: {analysis_dir} (como PDF)")

            log.info(f"\n--- Resumo Agregado (Sucessos) ---")
            print(df_agg.to_string(index=False))
        
        else:
            log.warning("Nenhum teste executado com sucesso. Nenhum dado agregado para mostrar.")

        # Log de Erros (dos dados brutos)
        error_df = df_raw[df_raw['success'] == False]
        if not error_df.empty:
            log.warning(f"\n--- Erros ---")
            pd.set_option('display.max_colwidth', 120)
            print(error_df[['id', 'run_number', 'params', 'error']].to_string(index=False))

    except Exception as e:
        log.error(f"Falha ao gerar analise: {e}", exc_info=True)

    log.info("Benchmark do Parser concluido.")


if __name__ == "__main__":
    os.chdir(Path(__file__).parent.resolve())
    main()