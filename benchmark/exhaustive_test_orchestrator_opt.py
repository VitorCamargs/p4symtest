#!/usr/bin/env python3
"""
Orquestrador de Teste Exaustivo do P4SymTest (vComCachePersistente)

Este script:
1. Gera programas P4 sintéticos (com lógica de ingress paralela)
2. Compila cada programa
3. GERA/CARREGA CACHE de análise persistente (deparser + tabelas)
4. Executa o parser para obter estados iniciais
5. Explora TODOS os caminhos possíveis através das condicionais (EM PARALELO)
6. SIMULA execução de tabelas usando o cache persistente
7. SIMULA execução do deparser usando o cache persistente
8. Coleta métricas detalhadas (tempo, memória ZERADA)
9. Gera relatórios e gráficos
"""

import json
import time
import subprocess
# import psutil # Não mais necessário
import os
import sys
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Set, Tuple, Optional
import shutil
import logging
from collections import defaultdict
import concurrent.futures
import threading # Para Lock (se necessário no futuro)

# Imports do gerador e analisador
try:
    from synthetic_p4_generator import SyntheticP4Generator
except ImportError:
    print("Erro: Não foi possível encontrar 'synthetic_p4_generator.py'.")
    sys.exit(1)

# Não precisamos mais importar a lógica do deparser aqui

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(threadName)s] %(message)s')
log = logging.getLogger(__name__)

# Cache Global carregado do arquivo
ANALYSIS_CACHE: Dict[str, Any] = {} # Populado por load_or_generate_cache

# --- Estruturas de Dados --- (Mantidas)
@dataclass
class PipelinePath:
    path_id: str; tables: List[str]; conditions: List[str]; condition_values: List[bool]
@dataclass
class ExecutionMetrics:
    config_id: str; run_number: int; parser_time_s: float; parser_mem_mb: float; parser_states_out: int
    total_paths: int; paths_explored: int; total_table_executions: int; total_table_time_s: float
    avg_table_time_s: float; max_table_mem_mb: float; deparser_time_s: float; deparser_mem_mb: float
    total_time_s: float; success: bool; error: Optional[str] = None

# --- Path Explorer --- (Mantido)
class PipelinePathExplorer:
    # ... (código exatamente como antes) ...
    def __init__(self, fsm_data: Dict):
        self.fsm_data = fsm_data
        self.ingress_pipeline = next((p for p in fsm_data.get('pipelines', []) if p['name'] == 'ingress'), None)
        if not self.ingress_pipeline: raise ValueError("Pipeline 'ingress' não encontrado no FSM")
    def find_all_paths(self) -> List[PipelinePath]:
        paths = []; init_node = self.ingress_pipeline.get('init_table')
        if init_node: self._explore_node(init_node, [], [], [], paths)
        log.info(f"Exploração concluída: {len(paths)} caminhos encontrados")
        return paths
    def _explore_node(self, node_name: str, tables: List[str], conditions: List[str], cond_values: List[bool], paths: List[PipelinePath]):
        if node_name is None:
            path_id = self._generate_path_id(tables, cond_values)
            paths.append(PipelinePath(path_id, tables.copy(), conditions.copy(), cond_values.copy())); return
        table = next((t for t in self.ingress_pipeline.get('tables', []) if t['name'] == node_name), None)
        if table:
            next_node = table.get('base_default_next')
            self._explore_node(next_node, tables + [node_name], conditions, cond_values, paths); return
        conditional = next((c for c in self.ingress_pipeline.get('conditionals', []) if c['name'] == node_name), None)
        if conditional:
            true_next = conditional.get('true_next'); false_next = conditional.get('false_next')
            self._explore_node(true_next, tables, conditions + [node_name], cond_values + [True], paths)
            self._explore_node(false_next, tables, conditions + [node_name], cond_values + [False], paths)
    def _generate_path_id(self, tables: List[str], cond_values: List[bool]) -> str:
        table_part = "_".join(t.split('.')[-1] for t in tables) if tables else "empty"
        cond_part = "".join("T" if v else "F" for v in cond_values)
        return f"{table_part}_{cond_part}" if cond_part else table_part


# --- Executor Simplificado (Só Compila e Roda Parser) ---
class PreprocessorExecutor:
    """Executa apenas compilação e parser."""
    def __init__(self, workspace_dir: Path, scripts_dir: Path):
        self.workspace_dir = workspace_dir
        self.scripts_dir = scripts_dir
        self.p4c_cmd = "/usr/local/bin/p4c --target bmv2 --arch v1model"
        self.parser_script = scripts_dir / "run_parser.py"
        if not self.parser_script.exists(): raise FileNotFoundError(f"Script não encontrado: {self.parser_script}")

    def compile_p4(self, p4_file: Path, output_dir: Path) -> Tuple[bool, Optional[Path], float]:
        log.info(f"   [Compilando] {p4_file.name}...")
        fsm_json = output_dir / f"{p4_file.stem}.json"
        cmd = f"{self.p4c_cmd} -o {output_dir} {p4_file}"
        start = time.time(); duration = 0.0
        try:
            result = subprocess.run(cmd, shell=True, cwd=p4_file.parent, capture_output=True, text=True, timeout=300)
            duration = time.time() - start
            if result.returncode == 0 and fsm_json.exists(): log.info(f"   ✓ Compilado em {duration:.3f}s"); return True, fsm_json, duration
            else: log.error(f"   ✗ Compilação falhou: {result.stderr}"); return False, None, duration
        except Exception as e: log.error(f"   ✗ Erro na compilação: {e}"); return False, None, time.time() - start

    def run_parser(self, fsm_file: Path, output_file: Path) -> Tuple[bool, float, float, int]:
        cmd = ["python3", str(self.parser_script), str(fsm_file), str(output_file)]
        start = time.time(); mem_peak_mb = 0.0; duration = 0.0
        try:
            proc = subprocess.Popen(cmd, cwd=self.scripts_dir, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            try: stdout_data, stderr_data = proc.communicate(timeout=300)
            except subprocess.TimeoutExpired: proc.kill(); stdout_data, stderr_data = proc.communicate(); log.error(f"   ✗ Timeout no parser: {stderr_data}"); return False, time.time() - start, mem_peak_mb, 0
            duration = time.time() - start
            if proc.returncode != 0: log.error(f"   ✗ Erro no parser: {stderr_data}"); return False, duration, mem_peak_mb, 0
            states = 0
            if output_file.exists():
                with open(output_file, 'r') as f: data = json.load(f)
                states = len(data) if isinstance(data, list) else 0
            return True, duration, mem_peak_mb, states
        except Exception as e: log.error(f"   ✗ Erro no parser: {e}"); return False, time.time() - start, mem_peak_mb, 0

# --- Lógica de Simulação Usando Cache ---

def get_table_match_result(state_dict: dict, table_cache: dict) -> Tuple[str, Dict]:
    """
    Determina qual regra (ou default) da tabela dá match no estado atual.
    Retorna (cache_key_da_regra, action_info).
    """
    relevant_fields = table_cache.get("relevant_fields", [])
    cache = table_cache.get("cache", {})

    # Simplificação: Assume que as chaves no cache são 'match_rule_X' e 'default'.
    # Precisamos de uma lógica para *avaliar* as condições de match.
    # Esta função está INCOMPLETA. Precisaria comparar os valores do state_dict
    # com as condições implícitas nas chaves 'match_rule_X'.
    # Por enquanto, retorna 'default' como fallback.

    # Lógica de match (simplificada - apenas retorna default):
    # TODO: Implementar a comparação do state_dict com as assinaturas das regras
    #       armazenadas em cache[rule_key]["match_signature"]
    matched_rule_key = "default"

    action_info = cache.get(matched_rule_key)
    if not action_info:
        log.error(f"Ação não encontrada no cache para a chave '{matched_rule_key}'")
        return matched_rule_key, {"action_name": "ERROR_ACTION", "action_params": {}}

    return matched_rule_key, action_info


def apply_action(state_dict: dict, action_name: str, action_params: dict) -> dict:
    """
    Aplica as modificações de uma ação P4 a um dicionário de estado.
    Retorna o dicionário de estado modificado.
    """
    # Esta função precisa simular as primitivas P4 (assign, add_header, etc.)
    # Exemplo MUITO simplificado:
    new_state = state_dict.copy() # MUITO IMPORTANTE: Copiar para não modificar o original

    if action_name == "NoAction" or action_name == "Unknown_Default":
        pass # Nenhuma modificação
    elif action_name == "MyIngress.drop" or action_name == "MyEgress.drop": # Assumindo drop
        # Em P4, mark_to_drop modifica standard_metadata.egress_spec
        # Precisamos saber o valor exato (ex: 511 para porta 9 bits)
        new_state["standard_metadata.egress_spec"] = 511 # Simplificação!
    elif action_name.startswith("MyIngress.table"):
        # Ex: table0_action0(bit<9> port) -> standard_metadata.egress_spec = port; meta.stage0 = 0;
        stage_num_str = action_name.split('table')[1].split('_')[0]
        action_num_str = action_name.split('action')[1]
        port = action_params.get("port")
        if port is not None:
             new_state["standard_metadata.egress_spec"] = port
        new_state[f"scalars.stage{stage_num_str}"] = int(action_num_str) # Assume 'scalars' para metadata
    elif action_name.startswith("MyEgress.egress_table"):
         # Ex: egress_table0_action0(bit<48> mac) -> hdr.ethernet.srcAddr = mac; meta.egress_stage0 = 0;
        stage_num_str = action_name.split('table')[1].split('_')[0]
        action_num_str = action_name.split('action')[1]
        mac = action_params.get("mac")
        if mac is not None:
             new_state["ethernet.srcAddr"] = mac # Assume nome direto sem 'hdr.'
        new_state[f"scalars.egress_stage{stage_num_str}"] = int(action_num_str)

    # TODO: Adicionar simulação para outras ações se necessário (add_header, modify_field, etc.)

    return new_state


def simulate_path_with_cache(
    path: PipelinePath,
    parser_states: List[dict], # Estados resultantes do parser
    table_cache_global: dict,
    fsm_data: dict # Necessário para obter definições de tabela
    ) -> List[dict]:
    """
    Simula a execução de um caminho, usando o cache de tabelas.
    Retorna a lista de estados finais para este caminho.
    """
    current_states = parser_states # Começa com os estados do parser
    total_table_simulations = 0

    # Simula cada tabela no caminho
    for table_name in path.tables:
        if table_name not in table_cache_global:
            log.error(f"Cache não encontrado para a tabela {table_name}. Pulando simulação.")
            return [] # Retorna vazio se faltar cache

        table_cache = table_cache_global[table_name]
        next_states = []
        start_time = time.time()

        for input_state in current_states:
            # 1. Determina qual regra deu match (usando lógica simplificada por enquanto)
            _match_key, action_info = get_table_match_result(input_state, table_cache)
            action_name = action_info['action_name']
            action_params = action_info['action_params']

            # 2. Aplica a ação ao estado
            output_state = apply_action(input_state, action_name, action_params)

            # 3. Adiciona metadados (histórico, etc.) - Opcional aqui
            # output_state["history"] = input_state.get("history", []) + [f"Applied:{table_name}->{action_name}"]

            next_states.append(output_state)
            total_table_simulations += 1

        duration = time.time() - start_time
        # log.debug(f"Simulada tabela {table_name} em {duration:.4f}s ({len(current_states)} -> {len(next_states)} estados)")
        current_states = next_states # Saída vira entrada para a próxima tabela

    # log.debug(f"Caminho {path.path_id} simulado. Total de simulações de tabela: {total_table_simulations}")
    return current_states # Retorna os estados após a última tabela


def get_deparser_result_from_cache(
    state_dict: dict,
    deparser_cache: dict
    ) -> Optional[List[Dict]]:
    """Consulta o cache do deparser para obter o resultado de emissão."""
    relevant_fields = deparser_cache.get("relevant_fields", [])
    cache = deparser_cache.get("cache", {})

    # Gera a chave para este estado
    key_parts = []
    for hdr_name, field_name in relevant_fields:
        # Assume que a chave relevante é apenas $valid$ por enquanto
        if field_name == '$valid$':
            default_val = False
            # Tenta encontrar o valor de validade no estado
            found_value = default_val
            for key_attempt in [f"{hdr_name}.$valid$", f"hdr.{hdr_name}.$valid$"]:
                 if key_attempt in state_dict:
                      # Converte para boolean para consistência com a chave do cache
                      found_value = bool(state_dict[key_attempt]) 
                      break
            key_parts.append(found_value)
        # Ignora outros campos por enquanto na chave de lookup (baseado na pré-computação simples)

    signature_tuple = tuple(key_parts)
    cache_key = str(signature_tuple) # Chave JSON é string

    if cache_key in cache:
        return cache[cache_key]
    else:
        # Cache MISS! Isso não deveria acontecer se a pré-computação foi completa
        # para todas as combinações de validade.
        log.warning(f"Cache MISS para Deparser! Assinatura: {cache_key}. Estado idx: {state_dict.get('input_state_index', -1)}. Retornando erro.")
        # Retorna um status de erro ou None
        return [{"header": "CACHE_MISS", "status": f"Assinatura {cache_key} não encontrada"}]


# --- Função Principal de Orquestração ---

def load_or_generate_cache(cache_filepath: Path, fsm_filepath: Path, runtime_filepath: Path) -> bool:
    """Carrega o cache do arquivo ou chama o script para gerá-lo."""
    global ANALYSIS_CACHE
    if cache_filepath.exists():
        log.info(f"Carregando cache de análise de {cache_filepath}...")
        cache_data = load_json_file(cache_filepath)
        if cache_data:
            # Validação básica (opcional): verificar hashes?
            log.info("Cache carregado com sucesso.")
            ANALYSIS_CACHE = cache_data
            return True
        else:
            log.warning("Falha ao carregar cache existente. Tentando gerar novamente.")

    # Cache não existe ou falhou ao carregar, tenta gerar
    log.info(f"Gerando cache de análise (pode demorar)... Output: {cache_filepath}")
    cache_gen_script = Path(__file__).parent / "generate_analysis_cache.py"
    if not cache_gen_script.exists():
        log.error(f"Script gerador de cache não encontrado: {cache_gen_script}")
        return False

    cmd = ["python3", str(cache_gen_script), str(fsm_filepath), str(runtime_filepath), str(cache_filepath)]
    try:
        # Roda o gerador de cache. Mostra a saída dele.
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=1800) # Timeout longo
        log.info("Script gerador de cache executado com sucesso.")
        log.debug(f"Saída do gerador de cache:\n{result.stdout}")
        # Tenta carregar o cache recém-gerado
        cache_data = load_json_file(cache_filepath)
        if cache_data:
            ANALYSIS_CACHE = cache_data
            return True
        else:
            log.error("Falha ao carregar o cache recém-gerado.")
            return False
    except subprocess.CalledProcessError as e:
        log.error(f"Erro ao executar o script gerador de cache:")
        log.error(f"  Comando: {' '.join(cmd)}")
        log.error(f"  Stderr:\n{e.stderr}")
        return False
    except subprocess.TimeoutExpired:
        log.error("Timeout ao executar o script gerador de cache.")
        return False
    except Exception as e:
        log.error(f"Erro inesperado ao executar gerador de cache: {e}")
        return False


def main():
    log.info("="*70); log.info("INICIANDO TESTE EXAUSTIVO DO P4SYMTEST (vComCachePersistente)"); log.info("="*70)
    NUM_RUNS = 1; log.info(f"Configurado para {NUM_RUNS} execuções por configuração")
    scripts_dir = Path("/app/workspace"); output_base_dir = Path("/app/workspace/exhaustive_test_run")
    if output_base_dir.exists(): log.info(f"Limpando diretório antigo: {output_base_dir}"); shutil.rmtree(output_base_dir)
    p4_output_dir = output_base_dir / "synthetic_p4s"; p4_output_dir.mkdir(parents=True, exist_ok=True)
    test_configs = [(3, 2, 1), (4, 3, 1), (5, 4, 2), (6, 5, 2), (7, 6, 3), (8, 7, 3), (9, 8, 4), (10, 9, 4), (11, 10, 5)]
    log.info(f"Gerando {len(test_configs)} configurações P4 (apenas lógica 'parallel')..."); generator = SyntheticP4Generator(seed=42); all_metadata = []
    for p_states, i_tables, e_tables in test_configs:
        base_params = {'parser_states': p_states, 'ingress_tables': i_tables, 'egress_tables': e_tables, 'headers_per_state': 1, 'actions_per_table': 2}
        try:
            meta_par = generator.generate_program(**base_params, ingress_logic_type='parallel', prog_id_suffix="_par", output_dir=p4_output_dir)
            all_metadata.append(meta_par)
        except Exception as e: log.error(f"Erro ao gerar P4 (parallel) para {base_params}: {e}", exc_info=True)
    log.info(f"Total de {len(all_metadata)} programas gerados. Iniciando execução...");
    
    executor = PreprocessorExecutor(workspace_dir=scripts_dir, scripts_dir=scripts_dir); # Usa o executor simplificado
    all_metrics = []

    for i, meta in enumerate(all_metadata):
        log.info("\n" + "="*70); log.info(f"Processando Teste [{i+1}/{len(all_metadata)}]: {meta['id']}"); log.info(f"Params: {meta['config']}"); log.info("="*70)
        p4_file = Path(meta['p4_file']); topology_file = Path(meta['topology_file']); runtime_file = Path(meta['runtime_file'])
        work_dir = p4_file.parent / f"{meta['id']}_work"; work_dir.mkdir(parents=True, exist_ok=True)

        # 1. COMPILAR
        compile_ok, fsm_file_path, comp_time = executor.compile_p4(p4_file, work_dir)
        if not compile_ok: log.error("Falha na compilação, pulando..."); continue
        fsm_data = load_json_file(fsm_file_path)
        if not fsm_data: log.error("Falha ao carregar FSM JSON, pulando..."); continue

        # --- CARREGAR OU GERAR O CACHE PERSISTENTE ---
        cache_filepath = work_dir / f"{meta['id']}.cache.json"
        cache_ready = load_or_generate_cache(cache_filepath, fsm_file_path, runtime_file)
        if not cache_ready:
            log.error(f"Falha ao carregar/gerar cache para {meta['id']}. Pulando teste.")
            continue
        # ANALYSIS_CACHE agora está populado globalmente para este FSM
        current_fsm_table_cache = ANALYSIS_CACHE.get("tables", {})
        current_fsm_deparser_cache = ANALYSIS_CACHE.get("deparser", {})
        # --- FIM CACHE ---

        # 2. EXPLORAR CAMINHOS (do FSM)
        log.info("   [Explorando caminhos do pipeline]...")
        try:
            explorer = PipelinePathExplorer(fsm_data); all_paths = explorer.find_all_paths(); log.info(f"   ✓ {len(all_paths)} caminhos encontrados")
            paths_file = work_dir / "pipeline_paths.json";
            with open(paths_file, 'w') as f: json.dump([asdict(p) for p in all_paths], f, indent=2)
        except Exception as e: log.error(f"   ✗ Erro ao explorar caminhos: {e}"); continue

        # 3. EXECUTAR MÚLTIPLAS VEZES (usando cache)
        for run_num in range(1, NUM_RUNS + 1):
            log.info(f"\n   --- Execução {run_num}/{NUM_RUNS} ---"); run_start = time.time()

            # 3.1 PARSER (ainda usa subprocesso)
            parser_output_file = work_dir / f"run{run_num}_parser_states.json"; parse_ok, parse_time, parse_mem, parse_states_count = executor.run_parser(fsm_file_path, parser_output_file)
            if not parse_ok: log.error(f"   ✗ Parser falhou na run {run_num}"); continue
            log.info(f"   ✓ Parser: {parse_time:.3f}s, {parse_mem:.1f}MB, {parse_states_count} estados")
            # Carrega os estados resultantes do parser
            parser_states_list = load_json_file(parser_output_file)
            if parser_states_list is None: log.error(f"   ✗ Falha ao carregar estados do parser {parser_output_file}"); continue

            # 3.2 SIMULAR CAMINHOS E TABELAS COM CACHE
            simulation_start_time = time.time()
            final_states_per_path: List[Tuple[PipelinePath, List[dict]]] = []
            paths_explored_count = 0

            # Nota: A simulação do caminho é sequencial aqui, mas rápida.
            # Poderia ser paralelizada se a lógica apply_action fosse thread-safe.
            log.info(f"   [Simulando] Executando {len(all_paths)} caminhos usando cache...")
            processed_path_count = 0
            for path in all_paths:
                final_states = simulate_path_with_cache(path, parser_states_list, current_fsm_table_cache, fsm_data)
                final_states_per_path.append( (path, final_states) )
                paths_explored_count += 1
                processed_path_count += 1
                if processed_path_count % 50 == 0:
                     log.info(f"     ... {processed_path_count}/{len(all_paths)} caminhos simulados.")

            simulation_time = time.time() - simulation_start_time
            log.info(f"   ✓ Simulação de tabelas concluída em {simulation_time:.3f}s.")
            # Métricas agregadas das tabelas (agora são simulações)
            total_table_simulations = sum(len(s[1]) for s in final_states_per_path for _ in s[0].tables if s[1]) # Conta complexa
            avg_table_time = simulation_time / paths_explored_count if paths_explored_count else 0 # Tempo médio por *caminho* simulado

            # 3.3 ANALISAR DEPARSER COM CACHE
            deparser_start_time = time.time()
            all_deparser_results = []
            total_deparsed_states = 0
            cache_hits = 0

            log.info(f"   [Deparser Cache] Analisando estados finais dos caminhos...")
            # Coleta todos os estados finais distintos (opcional, pode analisar todos)
            final_states_to_analyze = []
            state_to_path_map = {} # Mapeia estado (por índice único?) para info do path original
            unique_state_counter = 0
            for path, final_states in final_states_per_path:
                 for state in final_states:
                     state["__original_path_id__"] = path.path_id # Adiciona info de origem
                     state["__unique_state_id__"] = unique_state_counter
                     state_to_path_map[unique_state_counter] = path.path_id
                     final_states_to_analyze.append(state)
                     unique_state_counter +=1
            log.info(f"   [Deparser Cache] Total de {len(final_states_to_analyze)} estados finais a analisar.")

            for state_dict in final_states_to_analyze:
                emission_status = get_deparser_result_from_cache(state_dict, current_fsm_deparser_cache)

                if emission_status is not None:
                     all_deparser_results.append({
                         # Usar um ID único do estado se disponível, senão pode ficar ambíguo
                         "input_state_id": state_dict.get("__unique_state_id__", -1),
                         "original_path_id": state_dict.get("__original_path_id__", "unknown"),
                         "emission_status": emission_status
                     })
                     if emission_status and not any(s['header']=='CACHE_MISS' for s in emission_status):
                          cache_hits += 1 # Conta como hit se não for miss
                total_deparsed_states += 1
                if total_deparsed_states % 500 == 0:
                     log.info(f"     ... {total_deparsed_states}/{len(final_states_to_analyze)} estados de deparser analisados (Hits: {cache_hits})")


            deparser_output_file = work_dir / f"run{run_num}_deparser_results_persistent_cache.json"
            try:
                with open(deparser_output_file, 'w') as f: json.dump(all_deparser_results, f, indent=2)
            except Exception as e: log.error(f"Falha ao salvar resultados cacheados do deparser: {e}")
            deparser_time = time.time() - deparser_start_time
            log.info(f"   ✓ Deparser (Cache): {deparser_time:.3f}s processados.")
            log.info(f"     Cache Stats: Hits={cache_hits}, Total={total_deparsed_states} estados.")
            deparse_ok = True; deparse_mem = 0.0

            # --- FIM DEPARSER COM CACHE ---

            total_time = time.time() - run_start
            metrics = ExecutionMetrics(
                config_id=meta['id'], run_number=run_num, parser_time_s=parse_time, parser_mem_mb=parse_mem,
                parser_states_out=parse_states_count, total_paths=len(all_paths), paths_explored=paths_explored_count,
                # Ajusta métricas de tabela para refletir simulação
                total_table_executions=total_table_simulations, # Número de simulações estado->tabela
                total_table_time_s=simulation_time,            # Tempo total de simulação
                avg_table_time_s=avg_table_time,               # Tempo médio por caminho simulado
                max_table_mem_mb=0.0,                          # Memória zerada
                deparser_time_s=deparser_time, deparser_mem_mb=deparse_mem, total_time_s=total_time,
                success= (paths_explored_count == len(all_paths)) )
            all_metrics.append(asdict(metrics))
            log.info(f"   ✓ Run {run_num} concluída em {total_time:.2f}s total")

    # --- ANÁLISE --- (Mantida como antes, mas ajusta labels dos gráficos)
    log.info("\n" + "="*70); log.info("GERANDO ANÁLISE E RELATÓRIOS"); log.info("="*70)
    if not all_metrics: log.error("Nenhuma métrica coletada."); log.info("TESTE EXAUSTIVO FALHOU"); return
    try:
        import pandas as pd
        import matplotlib.pyplot as plt
        analysis_dir = output_base_dir / "analysis"; analysis_dir.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(all_metrics); csv_raw = analysis_dir / "exhaustive_test_raw.csv"; df.to_csv(csv_raw, index=False); log.info(f"CSV raw salvo: {csv_raw}")
        try: df['complexity'] = df['config_id'].str.extract(r'_p(\d+)_').astype(int)
        except Exception: log.warning("Não extraiu 'complexity'."); df['complexity'] = df['config_id']
        df_agg = df.groupby('config_id').agg(parser_time_s=('parser_time_s', 'mean'), parser_mem_mb=('parser_mem_mb', 'mean'),
            total_paths=('total_paths', 'first'), total_table_executions=('total_table_executions', 'mean'),
            total_table_time_s=('total_table_time_s', 'mean'), deparser_time_s=('deparser_time_s', 'mean'),
            total_time_s=('total_time_s', 'mean'), success_rate=('success', 'mean'),
            complexity_sort_col=('complexity', 'first') ).sort_values(by='complexity_sort_col').reset_index()
        csv_agg = analysis_dir / "exhaustive_test_aggregated.csv"; df_agg.to_csv(csv_agg, index=False); log.info(f"CSV agregado salvo: {csv_agg}")
        plt.figure(figsize=(12, 7)); df.sort_values(by='complexity').boxplot(column='total_time_s', by='complexity', patch_artist=True)
        plt.title('Tempo Total vs Complexidade (Cache Persistente)'); plt.suptitle(''); plt.xlabel('Complexidade'); plt.ylabel('Tempo (s)'); plt.savefig(analysis_dir / "plot_total_time_boxplot.pdf"); plt.close()
        plt.figure(figsize=(10, 6)); path_counts = df.groupby('complexity')['total_paths'].first().sort_index(); plt.plot(path_counts.index, path_counts.values, marker='o', color='red')
        plt.title('Explosão de Caminhos'); plt.xlabel('Complexidade'); plt.ylabel('Caminhos'); plt.grid(True); plt.savefig(analysis_dir / "plot_path_explosion.pdf"); plt.close()
        plt.figure(figsize=(12, 7)); df_time = df.groupby('complexity').agg(parser_time_s=('parser_time_s', 'mean'), total_table_time_s=('total_table_time_s', 'mean'), deparser_time_s=('deparser_time_s', 'mean')).sort_index()
        df_time.plot(kind='bar', stacked=True, color=['#3498db', '#e74c3c', '#2ecc71']); plt.title('Breakdown Tempo (Cache Persistente)'); plt.xlabel('Complexidade'); plt.ylabel('Tempo (s)'); plt.legend(['Parser', 'Tabelas (Simulação)', 'Deparser (Cache)']); plt.tight_layout(); plt.savefig(analysis_dir / "plot_time_breakdown.pdf"); plt.close()
        log.info(f"Gráficos salvos em: {analysis_dir}")
        print("\n" + "="*70); print("RESUMO DOS RESULTADOS (Médias)"); print("="*70)
        df_agg_print = df_agg.drop(columns=['complexity_sort_col']); df_agg_print = df_agg_print.round(3); print(df_agg_print.to_string(index=False))
    except ImportError: log.warning("Pandas/Matplotlib não encontrados. Pulando relatórios.")
    except Exception as e: log.error(f"Erro na análise: {e}", exc_info=True)
    log.info("\n" + "="*70); log.info("TESTE EXAUSTIVO CONCLUÍDO"); log.info("="*70)


if __name__ == "__main__":
    # Garante que z3-solver esteja instalado no ambiente do orquestrador
    try:
         import z3
         log.info(f"Biblioteca Z3 encontrada (Versão: {z3.get_version_string()}).")
    except ImportError:
         log.error("Biblioteca z3-solver não encontrada. Instale com: pip install z3-solver")
         sys.exit(1)
         
    # Muda para o diretório do script para que imports relativos funcionem
    os.chdir(Path(__file__).parent.resolve())
    main()