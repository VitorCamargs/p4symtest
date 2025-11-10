#!/usr/bin/env python3
"""
Orquestrador de Teste Exaustivo do P4SymTest (Versão com Cache)
"""

import json
import time
import subprocess
import psutil
import os
import sys
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Set, Tuple, Optional
import shutil
import logging
from collections import defaultdict
import concurrent.futures 

# Imports do gerador e analisador
try:
    from synthetic_p4_generator import SyntheticP4Generator
    from deparser_optimizer import optimize_and_process_deparser, expand_deparser_results
except ImportError as e:
    print(f"Erro: Não foi possível importar módulos necessários: {e}")
    sys.exit(1)

# <<< MUDANÇA 1: Imports do cache
from table_execution_cache import TableExecutionCache, optimize_table_input, expand_table_results
# >>> FIM MUDANÇA 1

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)

# --- Estruturas de Dados ---

@dataclass
class PipelinePath:
    """Representa um caminho completo através do pipeline"""
    path_id: str
    tables: List[str]          # Tabelas na ordem de execução
    conditions: List[str]      # Condicionais atravessadas
    condition_values: List[bool] # Valores das condicionais (True/False)
    
@dataclass
class ExecutionMetrics:
    """Métricas de uma execução completa"""
    config_id: str
    run_number: int
    
    # Parser
    parser_time_s: float
    parser_mem_mb: float
    parser_states_out: int
    
    # Pipeline paths
    total_paths: int
    paths_explored: int
    
    # Tables (agregado)
    total_table_executions: int
    total_table_time_s: float
    avg_table_time_s: float
    max_table_mem_mb: float
    
    # Deparser
    deparser_time_s: float
    deparser_mem_mb: float
    
    # Overall
    total_time_s: float
    success: bool
    error: Optional[str] = None

# --- Path Explorer ---

class PipelinePathExplorer:
    """Explora todos os caminhos possíveis através do pipeline"""
    
    def __init__(self, fsm_data: Dict):
        self.fsm_data = fsm_data
        self.ingress_pipeline = next(
            (p for p in fsm_data.get('pipelines', []) if p['name'] == 'ingress'),
            None
        )
        if not self.ingress_pipeline:
            raise ValueError("Pipeline 'ingress' não encontrado no FSM")
    
    def find_all_paths(self) -> List[PipelinePath]:
        """Encontra todos os caminhos possíveis através do pipeline"""
        paths = []
        init_node = self.ingress_pipeline.get('init_table')
        
        if init_node:
            self._explore_node(init_node, [], [], [], paths)
        
        log.info(f"Exploração concluída: {len(paths)} caminhos encontrados")
        return paths
    
    def _explore_node(self, node_name: str, tables: List[str], 
                      conditions: List[str], cond_values: List[bool],
                      paths: List[PipelinePath]):
        """Explora recursivamente um nó do pipeline"""
        
        if node_name is None:
            # Fim do caminho
            path_id = self._generate_path_id(tables, cond_values)
            paths.append(PipelinePath(
                path_id=path_id,
                tables=tables.copy(),
                conditions=conditions.copy(),
                condition_values=cond_values.copy()
            ))
            return
        
        # Verifica se é uma tabela
        table = next(
            (t for t in self.ingress_pipeline.get('tables', []) 
             if t['name'] == node_name),
            None
        )
        
        if table:
            # É uma tabela
            next_node = table.get('base_default_next')
            self._explore_node(
                next_node,
                tables + [node_name],
                conditions,
                cond_values,
                paths
            )
            return
        
        # Verifica se é uma condicional
        conditional = next(
            (c for c in self.ingress_pipeline.get('conditionals', [])
             if c['name'] == node_name),
            None
        )
        
        if conditional:
            # É uma condicional - explora ambos os ramos
            
            # Ramo TRUE
            true_next = conditional.get('true_next')
            self._explore_node(
                true_next,
                tables,
                conditions + [node_name],
                cond_values + [True],
                paths
            )
            
            # Ramo FALSE
            false_next = conditional.get('false_next')
            self._explore_node(
                false_next,
                tables,
                conditions + [node_name],
                cond_values + [False],
                paths
            )
    
    def _generate_path_id(self, tables: List[str], cond_values: List[bool]) -> str:
        """Gera ID único para um caminho"""
        table_part = "_".join(t.split('.')[-1] for t in tables) if tables else "empty"
        cond_part = "".join("T" if v else "F" for v in cond_values)
        return f"{table_part}_{cond_part}" if cond_part else table_part

# --- Executor ---

class ExhaustivePipelineExecutor:
    """Executa testes exaustivos do pipeline"""
    
    def __init__(self, workspace_dir: Path, scripts_dir: Path):
        self.workspace_dir = workspace_dir
        self.scripts_dir = scripts_dir
        
        # Comandos
        self.p4c_cmd = "/usr/local/bin/p4c --target bmv2 --arch v1model"
        self.parser_script = scripts_dir / "run_parser.py"
        self.table_script = scripts_dir / "run_table.py"
        self.deparser_script = scripts_dir / "run_deparser.py"
        
        # <<< MUDANÇA 2: Inicialização do cache
        self.table_cache_dir = workspace_dir / ".table_cache"
        self.table_cache_dir.mkdir(exist_ok=True)
        self.table_caches = {}  # {table_name: TableExecutionCache}
        # >>> FIM MUDANÇA 2
        
        # Validação
        for script in [self.parser_script, self.table_script, self.deparser_script]:
            if not script.exists():
                raise FileNotFoundError(f"Script não encontrado: {script}")

    # <<< MUDANÇA 2: Método helper do cache
    def _get_table_cache(self, table_name: str, run_num: int) -> TableExecutionCache:
        """Obtém ou cria cache para uma tabela"""
        cache_key = f"{table_name}_run{run_num}"
        
        if cache_key not in self.table_caches:
            cache_file = self.table_cache_dir / f"{cache_key}.json"
            self.table_caches[cache_key] = TableExecutionCache(cache_file)
        
        return self.table_caches[cache_key]
    # >>> FIM MUDANÇA 2
    
    def compile_p4(self, p4_file: Path, output_dir: Path) -> Tuple[bool, Optional[Path], float]:
        """Compila programa P4"""
        log.info(f"   [Compilando] {p4_file.name}...")
        
        fsm_json = output_dir / f"{p4_file.stem}.json"
        cmd = f"{self.p4c_cmd} -o {output_dir} {p4_file}"
        
        start = time.time()
        try:
            result = subprocess.run(
                cmd, shell=True, cwd=p4_file.parent,
                capture_output=True, text=True, timeout=300
            )
            duration = time.time() - start
            
            if result.returncode == 0 and fsm_json.exists():
                log.info(f"   ✓ Compilado em {duration:.3f}s")
                return True, fsm_json, duration
            else:
                log.error(f"   ✗ Compilação falhou: {result.stderr}")
                return False, None, duration
        except Exception as e:
            log.error(f"   ✗ Erro na compilação: {e}")
            return False, None, time.time() - start
    
    def run_parser(self, fsm_file: Path, output_file: Path) -> Tuple[bool, float, float, int]:
        """Executa análise do parser"""
        cmd = ["python3", str(self.parser_script), str(fsm_file), str(output_file)]
        
        start = time.time()
        mem_peak_mb = 0.0 # Memória não é mais medida
        
        try:
            proc = subprocess.Popen(
                cmd, cwd=self.scripts_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, 
                text=True
            )
            
            try:
                stdout_data, stderr_data = proc.communicate(timeout=300)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout_data, stderr_data = proc.communicate()
                log.error(f"   ✗ Timeout no parser: {stderr_data}")
                return False, time.time() - start, mem_peak_mb, 0

            duration = time.time() - start
            
            if proc.returncode != 0:
                log.error(f"   ✗ Erro no parser: {stderr_data}")
                return False, duration, mem_peak_mb, 0
            
            states = 0
            if output_file.exists():
                with open(output_file, 'r') as f:
                    data = json.load(f)
                    states = len(data) if isinstance(data, list) else 0
            
            return True, duration, mem_peak_mb, states
            
        except Exception as e:
            log.error(f"   ✗ Erro no parser: {e}")
            return False, time.time() - start, mem_peak_mb, 0
    
    def run_table(self, fsm_file: Path, topology_file: Path, runtime_file: Path,
                  input_states: Path, switch_id: str, table_name: str,
                  output_states: Path) -> Tuple[bool, float, float]:
        """Executa análise de uma tabela"""
        cmd = [
            "python3", str(self.table_script),
            str(fsm_file), str(topology_file), str(runtime_file),
            str(input_states), switch_id, table_name, str(output_states)
        ]
        
        start = time.time()
        mem_peak_mb = 0.0 # Memória não é mais medida
        
        try:
            proc = subprocess.Popen(
                cmd, cwd=self.scripts_dir,
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.PIPE, 
                text=True
            )
            
            try:
                stdout_data, stderr_data = proc.communicate(timeout=300)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout_data, stderr_data = proc.communicate()
                log.error(f"   ✗ Timeout na tabela {table_name}: {stderr_data}")
                return False, time.time() - start, mem_peak_mb
            
            duration = time.time() - start
            
            if proc.returncode != 0:
                log.warning(f"   ✗ Erro na tabela {table_name}: {stderr_data}")
            
            return proc.returncode == 0, duration, mem_peak_mb
            
        except Exception as e:
            log.error(f"   ✗ Erro na tabela {table_name}: {e}")
            return False, time.time() - start, mem_peak_mb
    
    def run_deparser(self, fsm_file: Path, input_states: Path, 
                     output_file: Path) -> Tuple[bool, float, float]:
        """Executa análise do deparser"""
        cmd = [
            "python3", str(self.deparser_script),
            str(fsm_file), str(input_states), str(output_file)
        ]
        
        start = time.time()
        mem_peak_mb = 0.0 # Memória não é mais medida
        
        try:
            proc = subprocess.Popen(
                cmd, cwd=self.scripts_dir,
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.PIPE, 
                text=True
            )
            
            try:
                stdout_data, stderr_data = proc.communicate(timeout=300)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout_data, stderr_data = proc.communicate()
                log.error(f"   ✗ Timeout no deparser: {stderr_data}")
                return False, time.time() - start, mem_peak_mb
            
            duration = time.time() - start
            
            if proc.returncode != 0:
                log.error(f"   ✗ Erro no deparser: {stderr_data}")
            
            return proc.returncode == 0, duration, mem_peak_mb
            
        except Exception as e:
            log.error(f"   ✗ Erro no deparser: {e}")
            return False, time.time() - start, mem_peak_mb

    # <<< MUDANÇA 3: Método run_table_cached (COM CACHE)
    def run_table_cached(
        self, 
        fsm_file: Path, 
        topology_file: Path, 
        runtime_file: Path,
        input_states: Path, 
        switch_id: str, 
        table_name: str,
        output_states: Path,
        run_num: int,
        fsm_data: Dict = None
    ) -> Tuple[bool, float, float]:
        """Executa análise de uma tabela COM CACHE"""
        
        # Carrega FSM se não foi fornecido
        if fsm_data is None:
            with open(fsm_file) as f:
                fsm_data = json.load(f)
        
        # Carrega estados de entrada
        with open(input_states) as f:
            original_states = json.load(f)
        
        if not original_states:
            # Nenhum estado, apenas cria arquivo vazio
            with open(output_states, 'w') as f:
                json.dump([], f)
            return True, 0.0, 0.0
        
        start = time.time()
        mem_peak_mb = 0.0
        
        try:
            # Obtém cache
            cache = self._get_table_cache(table_name, run_num)
            
            # Encontra definição da tabela
            pipeline_name = 'ingress' if 'ingress' in table_name.lower() else 'egress'
            pipeline = next((p for p in fsm_data.get('pipelines', []) if p['name'] == pipeline_name), None)
            
            if not pipeline:
                # Fallback: executa sem cache
                return self.run_table(fsm_file, topology_file, runtime_file,
                                     input_states, switch_id, table_name, output_states)
            
            table_def = next((t for t in pipeline.get('tables', []) if t['name'] == table_name), None)
            
            if not table_def:
                # Fallback: executa sem cache
                return self.run_table(fsm_file, topology_file, runtime_file,
                                     input_states, switch_id, table_name, output_states)
            
            # FASE 1: Verificar cache
            cached_results = []
            states_to_process = []
            
            for idx, state in enumerate(original_states):
                hit, cached_result = cache.lookup(state, table_name, table_def, fsm_data)
                
                if hit:
                    cached_results.append((idx, cached_result))
                else:
                    states_to_process.append((idx, state))
            
            # Se todos em cache, retorna direto
            if not states_to_process:
                final_results = []
                cache_map = {idx: res for idx, res in cached_results}
                
                for idx, state in enumerate(original_states):
                    cached = cache_map.get(idx)
                    if cached:
                        result = state.copy()
                        result['field_updates'] = cached.get('field_updates', result.get('field_updates', {}))
                        result['z3_constraints_smt2'] = cached.get('new_constraints', result.get('z3_constraints_smt2', []))
                        result['was_cached'] = True
                        final_results.append(result)
                    else:
                        final_results.append(state)
                
                with open(output_states, 'w') as f:
                    json.dump(final_results, f, indent=2)
                
                duration = time.time() - start
                return True, duration, mem_peak_mb
            
            # FASE 2: Otimizar estados para processar
            states_only = [s for _, s in states_to_process]
            unique_states, index_mapping = optimize_table_input(
                states_only, table_name, table_def, fsm_data, cache
            )
            
            # FASE 3: Processar estados únicos
            temp_input = input_states.parent / f".temp_{table_name}_{input_states.name}"
            temp_output = output_states.parent / f".temp_{table_name}_{output_states.name}"
            
            with open(temp_input, 'w') as f:
                json.dump(unique_states, f)
            
            # Executa run_table original
            success, _, _ = self.run_table(
                fsm_file, topology_file, runtime_file,
                temp_input, switch_id, table_name, temp_output
            )
            
            if not success:
                temp_input.unlink(missing_ok=True)
                temp_output.unlink(missing_ok=True)
                return False, time.time() - start, mem_peak_mb
            
            # Carrega resultados
            with open(temp_output) as f:
                processed_results = json.load(f)
            
            # FASE 4: Atualizar cache
            hash_to_result = {}
            for idx, state in enumerate(unique_states):
                if idx < len(processed_results):
                    result = processed_results[idx]
                    state_hash = cache._compute_table_state_hash(
                        state, table_name, cache.table_relevant_fields[table_name]
                    )
                    hash_to_result[state_hash] = result
                    cache.store(state, result, table_name, table_def, fsm_data)
            
            # FASE 5: Expandir resultados
            full_results = []
            processed_idx_map = {states_to_process[i][0]: i for i in range(len(states_to_process))}
            
            for orig_idx, state in enumerate(original_states):
                cached = next((r for i, r in cached_results if i == orig_idx), None)
                
                if cached:
                    result = state.copy()
                    result['field_updates'] = cached.get('field_updates', result.get('field_updates', {}))
                    result['z3_constraints_smt2'] = cached.get('new_constraints', result.get('z3_constraints_smt2', []))
                    result['was_cached'] = True
                else:
                    proc_idx = processed_idx_map.get(orig_idx)
                    if proc_idx is not None:
                        state_hash = index_mapping.get(proc_idx)
                        result = hash_to_result.get(state_hash, state).copy()
                        result['description'] = state.get('description', 'Unknown')
                        result['was_cached'] = False
                    else:
                        result = state
                
                full_results.append(result)
            
            # Salva resultado final
            with open(output_states, 'w') as f:
                json.dump(full_results, f, indent=2)
            
            # Limpa temporários
            temp_input.unlink(missing_ok=True)
            temp_output.unlink(missing_ok=True)
            
            # Salva cache
            cache.save_cache()
            
            duration = time.time() - start
            return True, duration, mem_peak_mb
            
        except Exception as e:
            log.error(f"   ✗ Erro na tabela cached {table_name}: {e}")
            return False, time.time() - start, mem_peak_mb
    # >>> FIM MUDANÇA 3

# --- [Função Helper para Paralelismo] ---

def process_path(executor: ExhaustivePipelineExecutor,
                 path: PipelinePath,
                 path_idx: int,
                 run_num: int,
                 common_args: dict) -> Tuple[bool, List[float], List[float], Optional[Path]]:
    """
    Processa um único caminho do pipeline, executando suas tabelas em série.
    Retorna (sucesso, tempos, memórias, caminho_do_arquivo_final)
    """
    
    work_dir = common_args['work_dir']
    parser_output = common_args['parser_output']
    fsm_file = common_args['fsm_file']
    topology_file = common_args['topology_file']
    runtime_file = common_args['runtime_file']

    if path_idx % 20 == 0:
        log.info(f"      [Thread] Iniciando caminho {path_idx+1}/{common_args['total_paths']}: {path.path_id}")

    current_states = parser_output
    table_times = []
    table_mems = []
    
    if not path.tables:
        return (True, table_times, table_mems, parser_output)

    for table_idx, table_name in enumerate(path.tables):
        table_output = work_dir / f"run{run_num}_path{path_idx}_table{table_idx}.json"
        
        # <<< MUDANÇA 4: Usar run_table_cached
        table_ok, table_time, table_mem = executor.run_table_cached(
            fsm_file, topology_file, runtime_file,
            current_states, "s1", table_name, table_output,
            run_num, fsm_data=common_args.get('fsm_data')
        )
        # >>> FIM MUDANÇA 4
        
        if not table_ok:
            log.warning(f"      ✗ Tabela {table_name} falhou no caminho {path.path_id}")
            return (False, table_times, table_mems, None)
        
        table_times.append(table_time)
        table_mems.append(table_mem)
        current_states = table_output

    return (True, table_times, table_mems, current_states)


# --- Main ---

def main():
    log.info("="*70)
    log.info("INICIANDO TESTE EXAUSTIVO DO P4SYMTEST")
    log.info("="*70)
    
    NUM_RUNS = 5
    log.info(f"Configurado para {NUM_RUNS} execuções por configuração")
    
    scripts_dir = Path("/app/workspace")
    output_base_dir = Path("/app/workspace/exhaustive_test_run")
    
    if output_base_dir.exists():
        log.info(f"Limpando diretório antigo: {output_base_dir}")
        shutil.rmtree(output_base_dir)
    
    p4_output_dir = output_base_dir / "synthetic_p4s"
    p4_output_dir.mkdir(parents=True, exist_ok=True)
    
    test_configs = [
        (8, 8, 1),
        (8, 10, 1),
        (8, 12, 1),
        (8, 14, 1),
    ]
    
    log.info(f"Gerando {len(test_configs)} configurações P4 (apenas lógica 'parallel')...")
    generator = SyntheticP4Generator(seed=42)
    all_metadata = []
    
    for p_states, i_tables, e_tables in test_configs:
        
        base_params = {
            'parser_states': p_states,
            'ingress_tables': i_tables,
            'egress_tables': e_tables,
            'headers_per_state': 1,
            'actions_per_table': 2
        }

        try:
            meta_par = generator.generate_program(
                **base_params,
                ingress_logic_type='parallel',
                prog_id_suffix="_par",
                output_dir=p4_output_dir
            )
            all_metadata.append(meta_par)
        except Exception as e:
            log.error(f"Erro ao gerar P4 (parallel) para {base_params}: {e}", exc_info=True)

    
    log.info(f"Total de {len(all_metadata)} programas gerados. Iniciando execução...")
    
    executor = ExhaustivePipelineExecutor(
        workspace_dir=scripts_dir,
        scripts_dir=scripts_dir
    )
    
    all_metrics = []
    
    for i, meta in enumerate(all_metadata):
        log.info("\n" + "="*70)
        log.info(f"Processando Teste [{i+1}/{len(all_metadata)}]: {meta['id']}")
        log.info(f"Params: {meta['config']}")
        log.info("="*70)
        
        p4_file = Path(meta['p4_file'])
        topology_file = Path(meta['topology_file'])
        runtime_file = Path(meta['runtime_file'])
        
        work_dir = p4_file.parent / f"{meta['id']}_work"
        work_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. COMPILAR
        compile_ok, fsm_file, comp_time = executor.compile_p4(p4_file, work_dir)
        if not compile_ok:
            log.error("Falha na compilação, pulando...")
            continue
        
        # 2. EXPLORAR CAMINHOS
        log.info("   [Explorando caminhos do pipeline]...")
        try:
            with open(fsm_file, 'r') as f:
                fsm_data = json.load(f)
            
            explorer = PipelinePathExplorer(fsm_data)
            all_paths = explorer.find_all_paths()
            log.info(f"   ✓ {len(all_paths)} caminhos encontrados")
            
            paths_file = work_dir / "pipeline_paths.json"
            with open(paths_file, 'w') as f:
                json.dump([asdict(p) for p in all_paths], f, indent=2)
            
        except Exception as e:
            log.error(f"   ✗ Erro ao explorar caminhos: {e}")
            continue
        
        # 3. EXECUTAR MÚLTIPLAS VEZES
        for run_num in range(1, NUM_RUNS + 1):
            log.info(f"\n   --- Execução {run_num}/{NUM_RUNS} ---")
            
            run_start = time.time()
            
            # 3.1 PARSER
            parser_output = work_dir / f"run{run_num}_parser_states.json"
            parse_ok, parse_time, parse_mem, parse_states = executor.run_parser(
                fsm_file, parser_output
            )
            
            if not parse_ok:
                log.error(f"   ✗ Parser falhou na run {run_num}")
                continue
            
            log.info(f"   ✓ Parser: {parse_time:.3f}s, {parse_mem:.1f}MB, "
                     f"{parse_states} estados")
            
            
            # 3.2 EXECUTAR TODOS OS CAMINHOS (EM PARALELO)
            MAX_PATH_WORKERS = os.cpu_count() or 4
            
            log.info(f"   [Paralelizando] Explorando {len(all_paths)} caminhos com {MAX_PATH_WORKERS} workers...")
            
            table_times_all = []
            table_mems_all = []
            final_state_files_for_deparser = []
            paths_explored = 0

            # <<< MUDANÇA 5: Adicionar fsm_data ao common_args
            common_args = {
                'work_dir': work_dir,
                'parser_output': parser_output,
                'fsm_file': fsm_file,
                'topology_file': topology_file,
                'runtime_file': runtime_file,
                'total_paths': len(all_paths), # Para o log
                'fsm_data': fsm_data
            }
            # >>> FIM MUDANÇA 5

            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_PATH_WORKERS) as pool:
                futures = {
                    pool.submit(process_path, executor, path, path_idx, run_num, common_args): path
                    for path_idx, path in enumerate(all_paths)
                }
                
                for future in concurrent.futures.as_completed(futures):
                    path = futures[future]
                    try:
                        success, times, mems, final_state_file = future.result()
                        
                        if success:
                            paths_explored += 1
                            table_times_all.extend(times)
                            table_mems_all.extend(mems)
                            if final_state_file:
                                final_state_files_for_deparser.append(final_state_file)
                        else:
                            log.warning(f"   ✗ Caminho {path.path_id} falhou e foi pulado.")

                    except Exception as e:
                        log.error(f"   ✗ Erro catastrófico ao processar {path.path_id}: {e}", exc_info=True)

            log.info(f"   ✓ {paths_explored}/{len(all_paths)} caminhos explorados com sucesso.")

            # 3.3 DEPARSER
            deparser_input = work_dir / f"run{run_num}_final_states.json"
            
            log.info(f"   [Deparser] Iniciando merge de estados...")
            all_final_states = []
            unique_state_files = set(final_state_files_for_deparser)
            log.info(f"   [Deparser] Mergando {len(unique_state_files)} arquivos de estado...")

            for state_file in unique_state_files:
                if state_file.exists():
                    try:
                        with open(state_file, 'r') as f:
                            all_final_states.extend(json.load(f))
                    except json.JSONDecodeError:
                        log.warning(f"   ✗ Arquivo JSON inválido/vazio pulado: {state_file}")
                else:
                    log.warning(f"   ✗ Arquivo de estado final esperado não encontrado: {state_file}")
            
            log.info(f"   [Deparser] Total de {len(all_final_states)} estados para deparsing.")

            if not all_final_states:
                log.warning("   ✗ Nenhum estado final foi produzido, pulando deparser.")
                deparse_ok = False
                deparse_time = 0.0
                deparse_mem = 0.0
            else:
                log.info(f"   [Deparser] Otimizando estados equivalentes...")
                try:
                    optimized_file, opt_map = optimize_and_process_deparser(
                        all_final_states, work_dir, run_num
                    )
                    deparser_input = optimized_file
                except Exception as e:
                    log.warning(f"   ✗ Erro na otimização: {e}. Usando estados não otimizados.")
                    opt_map = None
                    deparser_input = work_dir / f"run{run_num}_final_states.json"
                    with open(deparser_input, 'w') as f:
                        json.dump(all_final_states, f)
            
                log.info(f"   [Deparser] EXECUTANDO SUBPROCESSO run_deparser.py...")
                deparser_output = work_dir / f"run{run_num}_deparser.json"
                deparse_ok, deparse_time, deparse_mem = executor.run_deparser(
                    fsm_file, deparser_input, deparser_output
                )
                log.info(f"   [Deparser] SUBPROCESSO CONCLUÍDO.")

                if deparse_ok and opt_map is not None:
                    log.info(f"   [Deparser] Expandindo resultados para todos os caminhos...")
                    try:
                        expanded_file = expand_deparser_results(
                            deparser_output, opt_map, work_dir, run_num
                        )
                        deparser_output = expanded_file
                        log.info(f"   [Deparser] ✓ Resultados expandidos disponíveis")
                    except Exception as e:
                        log.warning(f"   ✗ Erro na expansão: {e}. Usando resultados otimizados.")
            
            log.info(f"   ✓ Deparser: {deparse_time:.3f}s, {deparse_mem:.1f}MB")
            
            # <<< MUDANÇA 6: Salvar estatísticas do cache
            log.info(f"   [Cache] Salvando estatísticas...")
            cache_stats = {}
            for cache_key, cache in executor.table_caches.items():
                stats = cache.get_stats()
                cache_stats[cache_key] = stats
                log.info(f"            {cache_key}: Hit Rate = {stats['hit_rate']*100:.1f}%")
            
            cache_stats_file = work_dir / f"run{run_num}_cache_stats.json"
            with open(cache_stats_file, 'w') as f:
                json.dump(cache_stats, f, indent=2)
            # >>> FIM MUDANÇA 6
            
            # 3.4 MÉTRICAS
            total_time = time.time() - run_start
            
            metrics = ExecutionMetrics(
                config_id=meta['id'],
                run_number=run_num,
                parser_time_s=parse_time,
                parser_mem_mb=parse_mem,
                parser_states_out=parse_states,
                total_paths=len(all_paths),
                paths_explored=paths_explored,
                total_table_executions=len(table_times_all),
                total_table_time_s=sum(table_times_all),
                avg_table_time_s=sum(table_times_all) / len(table_times_all) if table_times_all else 0,
                max_table_mem_mb=max(table_mems_all) if table_mems_all else 0,
                deparser_time_s=deparse_time,
                deparser_mem_mb=deparse_mem,
                total_time_s=total_time,
                success= (paths_explored == len(all_paths)) 
            )
            
            all_metrics.append(asdict(metrics))
            
            log.info(f"   ✓ Run {run_num} concluída em {total_time:.2f}s total")
    
    # --- ANÁLISE ---
    log.info("\n" + "="*70)
    log.info("GERANDO ANÁLISE E RELATÓRIOS")
    log.info("="*70)
    
    if not all_metrics:
        log.error("Nenhuma métrica foi coletada. Análise não pode ser gerada.")
        log.info("TESTE EXAUSTIVO FALHOU")
        return

    try:
        import pandas as pd
        import matplotlib.pyplot as plt
        
        analysis_dir = output_base_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. CSV RAW
        df = pd.DataFrame(all_metrics)
        csv_raw = analysis_dir / "exhaustive_test_raw.csv"
        df.to_csv(csv_raw, index=False)
        log.info(f"CSV raw salvo: {csv_raw}")
        
        # 2. AGREGADOS
        try:
            df['complexity'] = df['config_id'].str.extract(r'_p(\d+)_').astype(int)
        except Exception:
            log.warning("Não foi possível extrair 'complexity' do config_id. Usando config_id.")
            df['complexity'] = df['config_id']

        
        df_agg = df.groupby('config_id').agg(
            parser_time_s=('parser_time_s', 'mean'),
            parser_mem_mb=('parser_mem_mb', 'mean'),
            total_paths=('total_paths', 'first'),
            total_table_executions=('total_table_executions', 'mean'),
            total_table_time_s=('total_table_time_s', 'mean'),
            deparser_time_s=('deparser_time_s', 'mean'),
            total_time_s=('total_time_s', 'mean'),
            success_rate=('success', 'mean'),
            complexity_sort_col=('complexity', 'first') 
        ).sort_values(by='complexity_sort_col').reset_index()
        
        csv_agg = analysis_dir / "exhaustive_test_aggregated.csv"
        df_agg.to_csv(csv_agg, index=False)
        log.info(f"CSV agregado salvo: {csv_agg}")
        
        # 3. GRÁFICOS
        
        plt.figure(figsize=(12, 7))
        df.sort_values(by='complexity').boxplot(column='total_time_s', by='complexity', patch_artist=True)
        plt.title('Tempo Total de Execução vs Complexidade (Lógica Paralela)')
        plt.suptitle('')
        plt.xlabel('Complexidade (Estados do Parser)')
        plt.ylabel('Tempo Total (s)')
        plt.savefig(analysis_dir / "plot_total_time_boxplot.pdf")
        plt.close()
        
        plt.figure(figsize=(10, 6))
        path_counts = df.groupby('complexity')['total_paths'].first().sort_index()
        plt.plot(path_counts.index, path_counts.values, marker='o', color='red')
        plt.title('Explosão de Caminhos no Pipeline')
        plt.xlabel('Complexidade (Estados do Parser)')
        plt.ylabel('Número de Caminhos Únicos')
        plt.grid(True)
        plt.savefig(analysis_dir / "plot_path_explosion.pdf")
        plt.close()
        
        plt.figure(figsize=(12, 7))
        df_time = df.groupby('complexity').agg(
            parser_time_s=('parser_time_s', 'mean'),
            total_table_time_s=('total_table_time_s', 'mean'),
            deparser_time_s=('deparser_time_s', 'mean')
        ).sort_index()
        
        df_time.plot(kind='bar', stacked=True, 
                     color=['#3498db', '#e74c3c', '#2ecc71'])
        plt.title('Breakdown de Tempo por Componente (Lógica Paralela)')
        plt.xlabel('Complexidade (Estados do Parser)')
        plt.ylabel('Tempo (s)')
        plt.legend(['Parser', 'Tabelas (Total)', 'Deparser'])
        plt.tight_layout()
        plt.savefig(analysis_dir / "plot_time_breakdown.pdf")
        plt.close()
        
        log.info(f"Gráficos salvos em: {analysis_dir}")
        
        # 4. RESUMO
        print("\n" + "="*70)
        print("RESUMO DOS RESULTADOS (Médias)")
        print("="*70)
        
        df_agg_print = df_agg.drop(columns=['complexity_sort_col'])
        df_agg_print = df_agg_print.round(3)
        print(df_agg_print.to_string(index=False))
        
    except ImportError:
        log.warning("Pandas ou Matplotlib não encontrados. Pulando geração de relatórios CSV e gráficos.")
    except Exception as e:
        log.error(f"Erro na análise: {e}", exc_info=True)
    
    log.info("\n" + "="*70)
    log.info("TESTE EXAUSTIVO CONCLUÍDO")
    log.info("="*70)

if __name__ == "__main__":
    os.chdir(Path(__file__).parent.resolve())
    main()