#!/usr/bin/env python3
"""
Orquestrador de Execução Modular com Suporte a Branching (Objetivo 3 - v6 Final Simplificado)

Analisa estaticamente o FSM JSON (usando 'conditionals' nos controles Ingress/Egress NOMEADOS)
para traçar caminhos e executa cada caminho sequencialmente,
assumindo a ordem fixa Parser -> Ingress -> Egress -> Deparser.
"""

import json
import time
import subprocess
import psutil
import os
import sys
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional, Tuple, Set, Union
import shutil
import logging
import itertools

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

def load_json(filepath: Path) -> Optional[Dict]:
    """Carrega dados de um arquivo JSON de forma segura."""
    if not filepath.exists():
        log.error(f"Erro: Arquivo não encontrado: {filepath}")
        return None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        log.error(f"Erro: Falha ao decodificar JSON: {filepath} ({e})")
        return None
    except Exception as e:
        log.error(f"Erro inesperado ao carregar {filepath}: {e}", exc_info=True)
        return None

# --- Classe de Execução Modular (Reutilizada) ---
class ModularExecutor:
    """Executa scripts modulares (parser, table, deparser)."""

    def __init__(self, workspace_dir: Path, scripts_dir: Path):
        self.workspace_dir = workspace_dir
        self.scripts_dir = scripts_dir
        self.parser_script = scripts_dir / "run_parser.py" #
        self.table_script = scripts_dir / "run_table.py" #
        self.deparser_script = scripts_dir / "run_deparser.py" #
        for script in [self.parser_script, self.table_script, self.deparser_script]:
            if not script.exists():
                raise FileNotFoundError(f"Script modular não encontrado: {script}")

    def _run_script(self, script_path: Path, args: List[str], cwd: Path = None, timeout: int = 300) -> (bool, str, float):
        """Executa um script Python e retorna status, stdout/stderr combinado e duração."""
        cmd_list = ["python3", str(script_path)] + [str(arg) for arg in args]
        cmd_str = " ".join(map(str, cmd_list))
        log.debug(f"    Executando: {cmd_str}")
        start_time = time.time(); output = ""; error_details = ""
        try:
            result = subprocess.run(
                cmd_list, cwd=cwd or self.scripts_dir, capture_output=True,
                text=True, encoding='utf-8', timeout=timeout, shell=False
            )
            duration = time.time() - start_time
            output = result.stdout or ""; error_details = result.stderr or ""
            if result.returncode == 0:
                if error_details: log.warning(f"    [Aviso {script_path.name}]: {error_details.strip()}")
                return True, output, duration
            else:
                error_msg = f"{script_path.name} falhou (Code {result.returncode})"
                output_short = (output[:500] + '...') if len(output) > 500 else output
                error_short = (error_details[:500] + '...') if len(error_details) > 500 else error_details
                error_msg += f"\n-- STDOUT (trunc) --\n{output_short}\n-- STDERR (trunc) --\n{error_short}"
                log.error(f"    ✗ {error_msg}")
                return False, f"{output}\n{error_details}", duration
        except subprocess.TimeoutExpired: log.error(f"    [ERRO] TIMEOUT: {cmd_str}"); return False, "Timeout Expirado", time.time() - start_time
        except Exception as e: log.error(f"    [ERRO] EXCECAO: {cmd_str}\n{e}", exc_info=True); return False, str(e), time.time() - start_time

    def run_parser(self, fsm_json: Path, output_json: Path, parser_name: str) -> bool: # Adiciona parser_name
        log.info(f"-> Executando Parser: {parser_name}...")
        # run_parser.py não usa o nome do parser, apenas o FSM
        success, _, duration = self._run_script(self.parser_script, [fsm_json, output_json])
        if success: log.info(f"  ✓ Parser concluído em {duration:.3f}s. Saída: {output_json.name}")
        return success

    def run_table(self, fsm_json: Path, topology: Path, runtime: Path,
                    input_states: Path, switch_id: str, table_name: str,
                    output_states: Path) -> bool:
        log.info(f"-> Executando Tabela: {table_name}...")
        args = [fsm_json, topology, runtime, input_states, switch_id, table_name, output_states]
        if not all(f.exists() for f in [fsm_json, topology, runtime, input_states]):
             log.error(f"Arquivos de entrada não encontrados para run_table ({table_name})."); return False
        success, _, duration = self._run_script(self.table_script, args)
        if success:
            output_valid = False
            if output_states.exists():
                 try:
                     if output_states.stat().st_size > 2:
                         with open(output_states, 'r') as f: json.load(f); output_valid = True
                 except Exception as e: log.warning(f"  ! Erro validar JSON {output_states.name}: {e}")
            if output_valid: log.info(f"  ✓ Tabela '{table_name}' concluída em {duration:.3f}s. Saída: {output_states.name}")
            else: log.warning(f"  ! Tabela '{table_name}' executada ({duration:.3f}s), mas saída vazia/inválida: {output_states.name}")
        return success

    def run_deparser(self, fsm_json: Path, input_states: Path, output_packets: Path, deparser_name: str) -> bool: # Adiciona fsm e nome
        log.info(f"-> Executando Deparser: {deparser_name}...")
        if not input_states or not input_states.exists(): log.error(f"Entrada '{input_states}' ñ encontrada p/ run_deparser."); return False
        # run_deparser.py também não usa o nome, apenas FSM, entrada e saída
        success, _, duration = self._run_script(self.deparser_script, [fsm_json, input_states, output_packets])
        if success: log.info(f"  ✓ Deparser concluído em {duration:.3f}s. Saída: {output_packets.name}")
        return success

# --- Funções de Análise do Grafo ---

def get_action_name(action_body: List) -> Optional[str]:
    """Extrai o nome da tabela ou controle de uma ação 'apply_*'."""
    # ... (código inalterado) ...
    if not action_body or not isinstance(action_body, list) or len(action_body) < 1: return None
    action_spec = action_body[0]; op = action_spec.get("op"); params = action_spec.get("parameters")
    if not isinstance(action_spec, dict) or not op or not params: return None
    if op == "apply_table": param = params[0]; return param.get("value") if isinstance(param, dict) and param.get("type") == "table" else None
    if op == "apply_control": param = params[0]; return param.get("value") if isinstance(param, dict) and param.get("type") == "control" else None
    return None

def extract_control_paths(control_name: str, fsm_data: Dict, control_cache: Dict) -> Optional[List[List[str]]]:
    """
    Analisa recursivamente a seção 'conditionals' de um controle para extrair
    todas as sequências possíveis de ações (nomes de tabelas/controles).
    Retorna None em caso de erro grave.
    """
    # ... (código da função extract_control_paths praticamente inalterado da v2.4) ...
    if control_name in control_cache: return control_cache[control_name]
    log.debug(f"Analisando controle: {control_name}")
    control_info = next((c for c in fsm_data.get("controls", []) if c["name"] == control_name), None)
    if not control_info: log.error(f"Definição controle '{control_name}' ñ encontrada."); control_cache[control_name]=None; return None
    conditionals = control_info.get("conditionals", []) #
    conditional_map = {cond["id"]: cond for cond in conditionals}
    action_bodies = {}; [action_bodies.update({a["action_id"]:a["body"]}) for a in control_info.get("actions", []) if "action_id" in a and "body" in a]
    start_node_id = 0
    if conditionals:
        all_next_ids_num = set().union(*(set(filter(lambda x: isinstance(x,int), [c.get("true_next"), c.get("false_next")])) for c in conditionals))
        possible_roots = {c["id"] for c in conditionals} - all_next_ids_num
        if len(possible_roots)==1: start_node_id=possible_roots.pop(); log.debug(f"Nó raiz: {start_node_id}")
        elif conditionals: start_node_id=conditionals[0]['id']; log.warning(f"Raiz ñ clara {control_name}, assume ID {start_node_id}")
    memo = {}
    def traverse(node_id: Optional[Union[int, str]]) -> List[List[str]]:
        state_key = node_id;
        if state_key in memo: return memo[state_key]
        log.debug(f"  Visitando nó: {node_id} ({type(node_id)})")
        if isinstance(node_id, str): log.debug(f"    Nó final (str): '{node_id}'. Caminho: [[{node_id}]]"); result = [[node_id]]; memo[state_key]=result; return result
        if node_id is None: log.debug(f"    Fim (None). Caminho: [[]]"); result = [[]]; memo[state_key]=result; return result
        conditional_node = conditional_map.get(node_id)
        if not conditional_node: log.error(f"ID conditional {node_id} ñ encontrado ({control_name})."); result=[[]]; memo[state_key]=result; return result
        action_sequence = []
        body = action_bodies.get(node_id, [])
        for action_step in body:
             action_call = action_step if isinstance(action_step, dict) else (action_step[0] if isinstance(action_step, list) and action_step else None)
             if action_call: action_name = get_action_name([action_call]);
             if action_name: action_sequence.append(action_name)
        log.debug(f"    Ações nó {node_id}: {action_sequence}")
        true_next=conditional_node.get("true_next"); false_next=conditional_node.get("false_next")
        true_paths=traverse(true_next); false_paths=traverse(false_next)
        combined_paths = []
        for t_path in true_paths: combined_paths.append(action_sequence + t_path)
        for f_path in false_paths:
            full_f_path = action_sequence + f_path
            if not any(full_f_path == existing for existing in combined_paths): combined_paths.append(full_f_path)
        final_paths = combined_paths
        log.debug(f"    Retornando Nó {node_id}. Caminhos: {final_paths}"); memo[state_key]=final_paths; return final_paths
    if not conditionals:
        log.debug(f"{control_name} s/ conditionals, corpo linear (ID 0).")
        linear_path = []
        body = action_bodies.get(0, [])
        for action_step in body:
             action_call = action_step if isinstance(action_step, dict) else (action_step[0] if isinstance(action_step, list) and action_step else None)
             if action_call: action_name = get_action_name([action_call]);
             if action_name: linear_path.append(action_name)
        all_paths = [linear_path]
    else: all_paths = traverse(start_node_id)
    unique_paths_set=set(); final_unique_paths=[]; has_non_empty=any(p for p in all_paths)
    for p in all_paths:
        clean_p=[item for item in p if item is not None]; path_tuple=tuple(clean_p)
        if path_tuple not in unique_paths_set:
            if clean_p or not has_non_empty: final_unique_paths.append(clean_p); unique_paths_set.add(path_tuple)
    if not final_unique_paths:
         if action_bodies.get(0, []) == [] and not conditionals : final_unique_paths = [[]]
         else: log.error(f"Ñ determinou caminhos p/ {control_name}."); control_cache[control_name]=None; return None
    log.debug(f"Caminhos {control_name}: {final_unique_paths}"); control_cache[control_name]=final_unique_paths; return final_unique_paths


# --- FUNÇÃO ATUALIZADA para usar sequência fixa ---
def generate_full_paths(fsm_data: Dict) -> Optional[Tuple[List[List[str]], Dict[str, str], Dict[str, str]]]:
    """
    Gera todas as sequências completas de componentes do pipeline,
    assumindo a ordem fixa Parser -> Ingress -> Egress -> Deparser.
    Extrai os NOMES P/I/E/D do FSM para identificar os controles corretos.
    Retorna tupla (caminhos, mapa_tipos, mapa_nomes_estagios) ou None.
    """
    component_names = {'parser': None, 'ingress': None, 'egress': None, 'deparser': None}
    component_map = {} # Mapa geral nome -> tipo

    try:
        # 1. Mapeia todos os componentes definidos
        for p in fsm_data.get("parsers", []): component_map[p["name"]] = "parser"
        for c in fsm_data.get("controls", []): component_map[c["name"]] = "control"
        for d in fsm_data.get("deparsers", []): component_map[d["name"]] = "deparser"
        for control in fsm_data.get("controls", []):
            control_name = control.get("name")
            if not control_name: continue
            for table in control.get("tables", []):
                table_name = table.get("name")
                if not table_name: continue
                full_table_name = f"{control_name}.{table_name}"
                component_map[full_table_name] = "table"

        # 2. Encontra a instância V1Switch e extrai os nomes P/I/E/D
        #    Esta parte ainda é necessária para saber *quais* controles são Ingress/Egress
        main_switch_instance = None
        for inst in fsm_data.get("control_instantiations", []):
             if inst.get("control_type") == "V1Switch":
                  main_switch_instance = inst; break
        if not main_switch_instance:
            log.error("Instância 'V1Switch' não encontrada em 'control_instantiations'."); return None

        component_params = main_switch_instance.get("parameters")
        if not component_params or not isinstance(component_params, list):
            log.error("Parâmetros ('parameters') não encontrados na V1Switch."); return None

        expected_types_order = ["parser", "control", "control", "deparser"]
        found_names = [None] * len(expected_types_order)
        param_idx, comp_idx = 0, 0
        while comp_idx < len(expected_types_order) and param_idx < len(component_params):
             param = component_params[param_idx]; param_idx += 1
             if isinstance(param, dict) and "type" in param and "value" in param:
                  comp_name, comp_type = param["value"], param["type"]
                  if comp_type not in ["parser", "control", "deparser"]: continue # Pula checksums etc.
                  if comp_type == expected_types_order[comp_idx]:
                       found_names[comp_idx] = comp_name; comp_idx += 1
                  else:
                       log.error(f"'{comp_name}' ({comp_type}) fora da ordem P->I->E->D."); return None
             else: log.warning(f"Parâmetro V1Switch inválido: {param}")

        if not all(found_names):
             log.error(f"Não encontrou todos P/I/E/D. Encontrados: {found_names}"); return None

        component_names['parser'], component_names['ingress'], component_names['egress'], component_names['deparser'] = found_names
        log.info(f"Sequência Principal Identificada: [{component_names['parser']} -> {component_names['ingress']} -> {component_names['egress']} -> {component_names['deparser']}]")

    except Exception as e:
        log.error(f"Erro ao extrair sequência principal: {e}", exc_info=True); return None

    # --- Extrai caminhos internos dos controles Ingress e Egress NOMEADOS ---
    control_cache = {}
    ingress_paths = extract_control_paths(component_names['ingress'], fsm_data, control_cache)
    if ingress_paths is None: log.error(f"Falha extrair caminhos Ingress '{component_names['ingress']}'."); return None
    ingress_paths = ingress_paths if any(ingress_paths) else [[]] # Garante [[]] se vazio

    egress_paths = extract_control_paths(component_names['egress'], fsm_data, control_cache)
    if egress_paths is None: log.error(f"Falha extrair caminhos Egress '{component_names['egress']}'."); return None
    egress_paths = egress_paths if any(egress_paths) else [[]]

    # --- Combina os caminhos ---
    paths_per_stage = [
        [[component_names['parser']]], # Sempre começa com o parser
        ingress_paths,                 # Caminhos internos do Ingress
        egress_paths,                  # Caminhos internos do Egress
        [[component_names['deparser']]]  # Sempre termina com o deparser
    ]
    combined_path_tuples = list(itertools.product(*paths_per_stage))
    full_paths = [[item for sublist in path_tuple for item in sublist if item] for path_tuple in combined_path_tuples]

    log.info(f"Total de {len(full_paths)} caminhos completos encontrados.")
    full_paths.sort(key=len); [log.info(f"  Caminho {i+1}: {p}") for i, p in enumerate(full_paths)]

    # Retorna também o mapeamento de nomes dos estágios P/I/E/D
    return full_paths, component_map, component_names
# --- FIM DA FUNÇÃO ATUALIZADA ---


# --- Orquestrador Principal ---

def main():
    log.info("="*70); log.info("INICIANDO ORQUESTRADOR (OBJETIVO 3 - v5 Final)"); log.info("Análise via 'conditionals', Sequência Fixa P->I->E->D"); log.info("="*70)

    scripts_dir = Path("/app/workspace")
    output_base_dir = Path("/app/workspace/branching_orchestrator_run")
    fsm_file = scripts_dir / "programa.json" #
    topology_file = scripts_dir / "topology.json" #
    runtime_file = scripts_dir / "runtime_config.json" #

    if not all(f.exists() for f in [fsm_file, topology_file, runtime_file]): log.error("Arquivos (FSM, Topo, Runtime) não encontrados."); return

    if output_base_dir.exists(): shutil.rmtree(output_base_dir)
    output_base_dir.mkdir(parents=True, exist_ok=True)
    switch_id = "s1"

    # --- Análise Estática ---
    log.info("--- Fase 1: Análise Estática do Grafo de Execução ---")
    fsm_data = load_json(fsm_file)
    if not fsm_data: log.error("Falha ao carregar FSM JSON."); return

    path_analysis_result = generate_full_paths(fsm_data) # <--- USA A FUNÇÃO CORRIGIDA
    if path_analysis_result is None: log.error("Erro na análise estática."); return
    all_execution_paths, component_map, stage_names = path_analysis_result # Recebe nomes P/I/E/D
    if not all_execution_paths: log.error("Nenhum caminho encontrado."); return

    # --- Execução Sequencial ---
    log.info("\n" + "="*70); log.info("--- Fase 2: Execução Modular por Caminho ---")
    executor = ModularExecutor(workspace_dir=output_base_dir, scripts_dir=scripts_dir)

    # Executa Parser
    parser_component_name = stage_names['parser'] # Usa o nome identificado
    parser_output_file = output_base_dir / f"{parser_component_name.replace('.','_')}_output.json"
    if not executor.run_parser(fsm_file, parser_output_file, parser_component_name): # Passa o nome
        log.error("Falha no Parser inicial."); return
    initial_state_file = parser_output_file

    # Executa cada caminho
    final_results = {}
    for idx, path in enumerate(all_execution_paths):
        path_id = f"path_{idx+1}"
        log.info("\n" + "-"*60); log.info(f"Executando Caminho {idx+1}/{len(all_execution_paths)} ({path_id}):"); log.info(f"Sequência: {path}"); log.info("-"*60)
        current_state_file = initial_state_file
        path_successful = True

        # Pula o parser (já executado)
        if not path or path[0] != parser_component_name:
             log.warning(f"Caminho {path_id} inválido. Pulando."); final_results[path_id] = "PULADO"; continue

        for i, component_name in enumerate(path[1:]):
            component_type = component_map.get(component_name)
            step_num = i + 2
            safe_comp_name = component_name.replace('.', '_').replace('[', '').replace(']', '')
            output_file_name = f"{path_id}_step{step_num}_{safe_comp_name}_out.json"
            output_file = output_base_dir / output_file_name
            log.info(f"  Passo {step_num}: '{component_name}' (Tipo: {component_type})")
            log.info(f"    Entrada: {current_state_file.name}"); log.info(f"    Saída:   {output_file.name}")

            input_valid = False
            if current_state_file.exists():
                try:
                    if current_state_file.stat().st_size > 2:
                        with open(current_state_file,'r') as f: json.load(f); input_valid = True
                except Exception as e: log.warning(f"    Entrada '{current_state_file.name}' inválida: {e}")

            if not input_valid:
                 log.warning(f"    Entrada '{current_state_file.name}' vazia/inválida. Pulando '{component_name}'.")
                 default_empty = "[]" if component_type != "deparser" else "{}"
                 try: output_file.write_text(default_empty, encoding="utf-8")
                 except Exception as e: log.error(f"    Falha criar saída vazia {output_file.name}: {e}"); path_successful = False; break
                 current_state_file = output_file; continue

            success = False
            if component_type == "table":
                success = executor.run_table(fsm_file, topology_file, runtime_file, current_state_file, switch_id, component_name, output_file)
            elif component_type == "deparser":
                 # Passa o nome correto do deparser
                 deparser_actual_name = stage_names['deparser'] 
                 success = executor.run_deparser(fsm_file, current_state_file, output_file, deparser_actual_name)
            elif component_type == "control": # Pass-through
                 log.warning(f"    Controle '{component_name}' (s/ ações?) na sequência. Pass-through.")
                 try: shutil.copyfile(current_state_file, output_file); success = True; log.info(f"    ✓ Pass-through p/ {output_file.name}")
                 except Exception as e: log.error(f"    ✗ Falha copiar p/ pass-through: {e}"); success = False
            else:
                log.error(f"    Tipo desconhecido '{component_type}' p/ '{component_name}'. Pulando.")
                output_file.write_text("[]", encoding="utf-8"); success = False

            if not success: log.error(f"  Falha no '{component_name}'. Interrompendo {path_id}."); path_successful = False; break
            current_state_file = output_file

        if path_successful:
             log.info(f"  Caminho {path_id} concluído. Resultado: {current_state_file.name}")
             final_results[path_id] = str(current_state_file.relative_to(output_base_dir))
        else: final_results[path_id] = "ERRO"

    # --- Conclusão ---
    log.info("\n" + "="*70); log.info("Execução Orquestrada concluída.")
    log.info("Resultados por caminho:"); [log.info(f"  {pid}: {res}") for pid, res in sorted(final_results.items())]
    log.info(f"Arquivos em: {output_base_dir}"); log.info("="*70)

if __name__ == "__main__":
    main()