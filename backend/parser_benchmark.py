#!/usr/bin/env python3
"""
Benchmark Isolado do Parser P4
Testa escalabilidade do parser variando:
- Número de estados (profundidade)
- Número de transições por estado (largura)
"""

import json
import time
import subprocess
import psutil
import os
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict
import matplotlib.pyplot as plt
import pandas as pd
import shutil
import logging

# Configuração de logging
# Define o encoding para UTF-8 para evitar problemas no Windows/Docker
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("parser_benchmark.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# --- Estruturas de Dados ---

@dataclass
class ParserBenchmarkResult:
    """Resultado de benchmark do parser"""
    prog_id: str
    num_states: int
    num_transitions: int
    total_headers: int
    
    compile_time_s: float = 0.0
    compile_success: bool = False
    
    parser_time_s: float = 0.0
    parser_mem_peak_mb: float = 0.0
    parser_output_states: int = 0
    parser_success: bool = False
    
    error_stage: str = None
    error_message: str = None

# --- Gerador de P4 Sintético ---

class ParserBenchmarkGenerator:
    """Gera programas P4 focados em testar o parser"""
    
    def __init__(self):
        self.ethertype_base = 0x8000
        self.protocol_base = 0x1000
    
    def generate_parser_focused_program(self,
                                       num_states: int,
                                       transitions_per_state: int,
                                       output_dir: Path) -> Dict:
        """
        Gera programa P4 com parser complexo
        """
        prog_id = f"parser_bench_s{num_states}_t{transitions_per_state}"
        
        p4_headers = ""
        headers_struct = "    ethernet_t eth;\n"
        emit_headers = ""
        total_headers = 0

        # Gere headers
        for i in range(num_states):
            for j in range(transitions_per_state):
                header_name = f"hdr_s{i}_t{j}"
                header_type = f"hdr_s{i}_t{j}_t"
                
                p4_headers += f"header {header_type} {{\n    bit<16> proto_id;\n}}\n\n"
                headers_struct += f"    {header_type} {header_name};\n"
                emit_headers += f"        packet.emit(hdr.{header_name});\n"
                total_headers += 1

        # --- GERAÇÃO P4 (ordem corrigida) ---
        
        p4_declarations = ""
        p4_implementations = ""
        
        # --- 1. Gere as declarações e implementações dos estados (exceto start) ---
        for i in range(num_states):
            for j in range(transitions_per_state):
                state_name = f"parse_state_{i}_{j}"
                header_name = f"hdr_s{i}_t{j}"
                
                p4_declarations += f"    state {state_name};\n"
                
                p4_implementations += f"    state {state_name} {{\n"
                p4_implementations += f"        hdr.{header_name}.setValid();\n"
                p4_implementations += f"        transition select(hdr.{header_name}.proto_id) {{\n"
                
                for k in range(transitions_per_state):
                    next_i = i + 1
                    next_j = k
                    
                    if next_i >= num_states:
                        next_state_name = "accept"
                    else:
                        next_state_name = f"parse_state_{next_i}_{next_j}"
                    
                    val = f"0x{self.protocol_base + k:04x}"
                    p4_implementations += f"            {val}: {next_state_name};\n"
                
                p4_implementations += "            default: accept;\n"
                p4_implementations += "        }\n"
                p4_implementations += "    }\n\n"

        # --- 2. Gere o 'start' state ---
        p4_start_state = "    state start {\n"
        p4_start_state += f"        transition select(hdr.eth.etherType) {{\n"
        
        for i in range(transitions_per_state):
            val = f"0x{self.ethertype_base + i:04x}"
            state_name = f"parse_state_0_{i}"
            p4_start_state += f"            {val}: {state_name};\n"
            
        p4_start_state += "            default: accept;\n"
        p4_start_state += "        }\n    }\n\n"

        # --- 3. Combine tudo na ordem correta ---
        p4_parser = p4_declarations + "\n" + p4_start_state + p4_implementations
        
        # --- Template P4 Completo ---

        p4_program = f"""
#include <core.p4>
#include <v1model.p4>

/* * Definição do header ethernet_t
 */
header ethernet_t {{
    bit<48> dstAddr;
    bit<48> srcAddr;
    bit<16> etherType;
}}

{p4_headers}

/* * Estrutura 'Headers' (H maiúsculo)
 */
struct Headers {{
{headers_struct}
}}

struct metadata {{
    // Vazio por enquanto
}}

/*
 * *** CORREÇÃO DE CASE SENSITIVE ***
 * Use 'Headers' (H maiúsculo) aqui
 */
parser MyParser(packet_in packet,
                out Headers hdr, 
                inout metadata meta,
                inout standard_metadata_t standard_metadata)
{{
{p4_parser}
}}

/*
 * *** CORREÇÃO DE CASE SENSITIVE ***
 */
control MyIngress(inout Headers hdr,
                  inout metadata meta,
                  inout standard_metadata_t standard_metadata)
{{
    apply {{
        // Mínimo para compilar
    }}
}}

/*
 * *** CORREÇÃO DE CASE SENSITIVE ***
 */
control MyEgress(inout Headers hdr,
                 inout metadata meta,
                 inout standard_metadata_t standard_metadata)
{{
    apply {{
        // Mínimo para compilar
    }}
}}

/*
 * *** CORREÇÃO DE CASE SENSITIVE ***
 */
control MyDeparser(packet_out packet, in Headers hdr)
{{
    apply {{
        packet.emit(hdr.eth);
{emit_headers}
    }}
}}

V1Switch(
    MyParser(),
    MyIngress(),
    MyEgress(),
    MyDeparser()
) main;
"""
        
        # Salva o programa P4
        prog_dir = output_dir / prog_id
        prog_dir.mkdir(parents=True, exist_ok=True)
        
        p4_file_path = prog_dir / "programa.p4"
        with open(p4_file_path, 'w', encoding='utf-8') as f:
            f.write(p4_program)
            
        return {
            "id": prog_id,
            "p4_file": str(p4_file_path),
            "num_states": num_states, # Profundidade
            "transitions_per_state": transitions_per_state, # Largura
            "total_headers": total_headers,
            "output_dir": str(prog_dir)
        }

# --- Executor de Benchmark ---

class ParserBenchmarkRunner:
    """Executa os passos do benchmark para o parser"""
    
    def __init__(self, workspace_dir: Path, scripts_dir: Path):
        self.workspace_dir = workspace_dir
        self.scripts_dir = scripts_dir
        self.p4c_cmd = "p4c --target bmv2 --arch v1model"
        self.parser_script = scripts_dir / "run_parser.py"

    def _run_command(self, cmd: str, cwd: Path) -> (bool, str, float):
        """Executa um comando e mede o tempo"""
        start_time = time.time()
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=300, # Timeout de 5 mins
                encoding='utf-8' # Garante encoding
            )
            duration = time.time() - start_time
            
            if result.returncode == 0:
                return True, result.stdout, duration
            else:
                return False, result.stderr, duration
                
        except subprocess.TimeoutExpired:
            log.warning(f"Comando excedeu timeout: {cmd}")
            return False, "Timeout Expirado", time.time() - start_time
        except Exception as e:
            log.error(f"Erro ao executar comando: {e}")
            return False, str(e), time.time() - start_time

    def _compile_p4(self, p4_file: Path, output_dir: Path) -> (bool, str, float):
        """Compila P4 para JSON FSM"""
        fsm_json_file = output_dir / "programa.json"
        cmd = f"{self.p4c_cmd} -o {output_dir} {p4_file}"
        
        success, output, duration = self._run_command(cmd, p4_file.parent)
        
        if not success or not fsm_json_file.exists():
            log.error(f"Falha na compilação: {output}") 
            return False, output, duration
            
        return True, str(fsm_json_file), duration

    def _analyze_parser(self, fsm_json_file: Path, output_json_file: Path) -> (bool, float, float, int, str):
        """Executa run_parser.py e mede performance"""
        cmd = f"python3 {self.parser_script} {fsm_json_file} {output_json_file}"
        
        process = None
        mem_peak = 0
        
        start_time = time.time()
        try:
            proc = subprocess.Popen(
                cmd.split(),
                cwd=self.scripts_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8'
            )
            process = psutil.Process(proc.pid)
            
            while proc.poll() is None:
                try:
                    mem_info = process.memory_info()
                    mem_peak = max(mem_peak, mem_info.rss)
                except psutil.NoSuchProcess:
                    break
                time.sleep(0.01)

            stdout, stderr = proc.communicate(timeout=300)
            duration = time.time() - start_time
            
            if proc.returncode != 0:
                return False, duration, mem_peak / (1024**2), 0, stderr

            output_states = 0
            if output_json_file.exists():
                try:
                    with open(output_json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        output_states = len(data) if isinstance(data, list) else 0
                except json.JSONDecodeError:
                    log.error(f"Erro ao ler JSON de saída: {output_json_file}")
                    return False, duration, mem_peak / (1024**2), 0, "Erro ao decodificar JSON de saida"
            
            return True, duration, mem_peak / (1024**2), output_states, ""

        except subprocess.TimeoutExpired:
            if process:
                try: process.kill() 
                except: pass
            log.warning(f"Execução do parser excedeu timeout: {cmd}")
            return False, time.time() - start_time, mem_peak / (1024**2), 0, "Timeout Expirado"
        except Exception as e:
            if process:
                try: process.kill()
                except: pass
            log.error(f"Erro ao executar parser: {e}")
            return False, time.time() - start_time, mem_peak / (1024**2), 0, str(e)


    def run_parser_benchmark(self, metadata: Dict) -> ParserBenchmarkResult:
        """Executa o pipeline completo de benchmark para um P4"""
        
        prog_id = metadata['id']
        p4_file = Path(metadata['p4_file'])
        output_dir = Path(metadata['output_dir'])
        
        log.info("\n" + "="*60)
        log.info(f"Parser Benchmark: {prog_id}")
        log.info(f"  Profundidade (Estados): {metadata['num_states']}")
        log.info(f"  Largura (Transições/Estado): {metadata['transitions_per_state']}")
        log.info(f"  Headers Totais: {metadata['total_headers']}")
        log.info("="*60 + "\n")

        result = ParserBenchmarkResult(
            prog_id=prog_id,
            num_states=metadata['num_states'],
            num_transitions=metadata['transitions_per_state'],
            total_headers=metadata['total_headers']
        )
        
        # 1. Compilar P4
        log.info("[1/2] Compilando P4...")
        compile_success, compile_output_msg, compile_time = self._compile_p4(p4_file, output_dir)
        
        result.compile_time_s = round(compile_time, 4)
        result.compile_success = compile_success
        
        if not compile_success:
            log.error(f"✗ Erro: Compilação falhou: {compile_output_msg}")
            result.error_stage = "compile"
            result.error_message = compile_output_msg
            return result
        
        log.info(f"✓ Compilado em {compile_time:.3f}s")
        fsm_json_file = Path(compile_output_msg) # Se sucesso, a msg é o caminho
        
        # 2. Analisar Parser
        log.info("[2/2] Analisando Parser (run_parser.py)...")
        parser_output_file = output_dir / "parser_states_output.json"
        
        success, duration, mem_peak, states, error = self._analyze_parser(fsm_json_file, parser_output_file)
        
        result.parser_time_s = round(duration, 4)
        result.parser_mem_peak_mb = round(mem_peak, 2)
        result.parser_output_states = states
        result.parser_success = success
        
        if not success:
            log.error(f"✗ Erro: Execução do parser falhou: {error}")
            result.error_stage = "parser_run"
            result.error_message = error
            return result
            
        log.info(f"✓ Análise concluída em: {duration:.3f}s")
        log.info(f"✓ Pico de memória: {mem_peak:.2f} MB")
        log.info(f"✓ Estados de saída gerados: {states}")
        
        return result

# --- Analisador de Resultados ---

class ParserBenchmarkAnalyzer:
    """Gera gráficos e CSV dos resultados"""
    
    def __init__(self, results: List[ParserBenchmarkResult], output_dir: Path):
        self.output_dir = output_dir
        self.df = pd.DataFrame([asdict(r) for r in results])
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.csv_path = self.output_dir / "parser_benchmark_results.csv"
        self.df.to_csv(self.csv_path, index=False, encoding='utf-8')
        log.info(f"\nResultados salvos em: {self.csv_path}")
        
    def print_summary(self):
        """Imprime estatísticas básicas no console"""
        print("\n" + "--- Resumo Estatístico (Testes com Sucesso) ---")
        
        success_df = self.df[self.df['parser_success'] == True]
        
        if success_df.empty:
            print("Nenhum benchmark concluído com sucesso.")
        else:
            print(success_df[['prog_id', 'parser_time_s', 'parser_mem_peak_mb', 'parser_output_states']].to_string(index=False))
            
            print("\n--- Correlações ---")
            try:
                correlations = success_df[['total_headers', 'parser_time_s', 'parser_mem_peak_mb', 'parser_output_states']].corr()
                print(correlations)
            except Exception as e:
                log.warning(f"Não foi possível calcular correlação: {e}")

        error_df = self.df[self.df['parser_success'] == False]
        if not error_df.empty:
            print("\n" + "--- Resumo de Erros ---")
            print(error_df[['prog_id', 'error_stage', 'error_message']].to_string(index=False))


    def generate_plots(self):
        """Gera gráficos de escalabilidade"""
        
        success_df = self.df[self.df['parser_success'] == True].copy()
        if success_df.empty:
            log.warning("Nenhum dado de sucesso para plotar.")
            return

        try:
            success_df['total_headers'] = pd.to_numeric(success_df['total_headers'])
            success_df['parser_time_s'] = pd.to_numeric(success_df['parser_time_s'])
            success_df['parser_output_states'] = pd.to_numeric(success_df['parser_output_states'])
            success_df['parser_mem_peak_mb'] = pd.to_numeric(success_df['parser_mem_peak_mb'])

            if success_df.empty:
                 log.warning("Nenhum dado numérico de sucesso para plotar.")
                 return

            # Tempo x Headers
            plt.figure(figsize=(10, 6))
            plt.plot(success_df['total_headers'], success_df['parser_time_s'], marker='o', linestyle='-')
            plt.title('Escalabilidade do Parser: Tempo de Execução')
            plt.xlabel('Headers Totais (Complexidade)')
            plt.ylabel('Tempo de Execução (segundos)')
            plt.grid(True)
            plt.savefig(self.output_dir / "plot_time_vs_headers.png")
            plt.close()

            # Estados Saída x Headers
            plt.figure(figsize=(10, 6))
            plt.plot(success_df['total_headers'], success_df['parser_output_states'], marker='x', linestyle='--', color='r')
            plt.title('Escalabilidade do Parser: Explosão de Estados')
            plt.xlabel('Headers Totais (Complexidade)')
            plt.ylabel('Estados de Saída Gerados')
            plt.grid(True)
            plt.savefig(self.output_dir / "plot_states_vs_headers.png")
            plt.close()

            # Memória x Headers
            plt.figure(figsize=(10, 6))
            plt.plot(success_df['total_headers'], success_df['parser_mem_peak_mb'], marker='s', linestyle=':', color='g')
            plt.title('Escalabilidade do Parser: Uso de Memória')
            plt.xlabel('Headers Totais (Complexidade)')
            plt.ylabel('Pico de Memória (MB)')
            plt.grid(True)
            plt.savefig(self.output_dir / "plot_memory_vs_headers.png")
            plt.close()

            log.info(f"Gráficos de análise salvos em: {self.output_dir}")
        
        except Exception as e:
            log.error(f"Erro ao gerar gráficos: {e}")


# --- Orquestrador Principal ---

if __name__ == "__main__":
    
    print("="*70)
    print("BENCHMARK ISOLADO DO PARSER")
    print("="*70)

    # Configurações de teste: (num_states/profundidade, transitions_per_state/largura)
    test_configs = [
        (3, 2),    # Pequeno
        (5, 2),    #
        (8, 2),    # Médio
        (10, 3),   # Grande
        (12, 3),   # Muito grande
        (15, 3),   # Extra grande
        (20, 2),   # Profundo mas simples
    ]
    
    # --- CAMINHOS PARA DOCKER ---
    # O script é executado de /app/parser_benchmark.py
    # Os scripts 'run_*.py' estão em /app/workspace/
    base_dir = Path("/app") 
    workspace_dir = base_dir / "workspace"
    scripts_dir = base_dir / "workspace"
    
    # Define o diretório de saída dentro do workspace (que é montado)
    bench_output_dir = workspace_dir / "parser_benchmark_output"
    
    if bench_output_dir.exists():
        log.info(f"Limpando diretório de saída antigo: {bench_output_dir}")
        shutil.rmtree(bench_output_dir)
    bench_output_dir.mkdir(parents=True, exist_ok=True)
    
    
    generator = ParserBenchmarkGenerator()
    runner = ParserBenchmarkRunner(workspace_dir, scripts_dir)
    
    results = []
    
    log.info(f"\nExecutando {len(test_configs)} configurações...")
    
    for num_states, trans_per_state in test_configs:
        try:
            metadata = generator.generate_parser_focused_program(
                num_states=num_states,
                transitions_per_state=trans_per_state,
                output_dir=bench_output_dir
            )
            
            result = runner.run_parser_benchmark(metadata)
            results.append(result)
            
        except Exception as e:
            log.error(f"Erro catastrófico no benchmark s{num_states}_t{trans_per_state}: {e}", exc_info=True)
            results.append(ParserBenchmarkResult(
                prog_id=f"parser_bench_s{num_states}_t{trans_per_state}",
                num_states=num_states,
                num_transitions=trans_per_state,
                total_headers=0,
                error_stage="orchestrator",
                error_message=str(e)
            ))
    
    # Análise
    log.info("\n" + "="*70)
    log.info("GERANDO ANÁLISES...")
    log.info("="*70)
    
    try:
        analysis_dir = bench_output_dir / "analysis"
        analyzer = ParserBenchmarkAnalyzer(results, analysis_dir)
        
        analyzer.print_summary()
        analyzer.generate_plots()
    
    except Exception as e:
        log.error(f"Falha ao gerar análise: {e}", exc_info=True)
    
    log.info("\nBenchmark do Parser concluído.")