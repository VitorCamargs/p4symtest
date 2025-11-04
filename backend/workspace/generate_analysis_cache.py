#!/usr/bin/env python3
"""
generate_analysis_cache.py

Script para pré-calcular os resultados da análise simbólica
para componentes P4 (deparser e tabelas) e salvá-los em um cache JSON persistente.
"""

import json
import sys
import itertools
import hashlib
from pathlib import Path
from typing import Dict, List, Tuple, Any
import logging

# Assume que a lógica de análise do deparser está no arquivo vizinho
try:
    from deparser_analyzer import (
        create_z3_fields,
        analyze_single_state_emission,
        get_relevant_deparser_fields
        # Não precisamos de get_deparser_cache_key aqui
    )
    # Precisaremos de Z3 para a análise do deparser
    from z3 import BitVec, Solver, sat, unsat, unknown, Z3Exception, parse_smt2_string
except ImportError as e:
    print(f"Erro: Falha ao importar 'deparser_analyzer.py' ou 'z3'. {e}")
    print("Certifique-se de que 'deparser_analyzer.py' existe e 'pip install z3-solver' foi executado.")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

# --- Funções Auxiliares ---

def load_json_file(filepath: Path) -> Optional[Dict]:
    """Carrega um arquivo JSON com tratamento de erro."""
    if not filepath.is_file():
        log.error(f"Arquivo não encontrado: {filepath}")
        return None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        log.error(f"Erro ao decodificar JSON em {filepath}: {e}")
        return None
    except Exception as e:
        log.error(f"Erro inesperado ao ler {filepath}: {e}")
        return None

def get_file_hash(filepath: Path) -> str:
    """Calcula o hash SHA256 do conteúdo de um arquivo."""
    hasher = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            while chunk := f.read(4096):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        log.warning(f"Não foi possível calcular o hash de {filepath}: {e}")
        return "error"

# --- Análise Estática dos Componentes ---

def analyze_deparser_static(fsm_data: dict) -> Dict:
    """
    Pré-calcula os resultados do deparser para diferentes classes de equivalência
    baseadas na validade dos headers.
    """
    log.info("Iniciando análise estática do Deparser...")
    deparser_cache_data = {"relevant_fields": [], "cache": {}}

    try:
        relevant_fields_tuples = get_relevant_deparser_fields(fsm_data)
        # Filtra para pegar apenas os campos '$valid$' que realmente afetam a emissão
        validity_fields = [f for f in relevant_fields_tuples if f[1] == '$valid$']
        deparser_cache_data["relevant_fields"] = validity_fields
        log.info(f"Campos de validade relevantes para o deparser: {[f'{f[0]}.{f[1]}' for f in validity_fields]}")

        # Cria os campos Z3 necessários (uma vez)
        fields_z3 = create_z3_fields(fsm_data)
        deparser_order = fsm_data.get('deparsers', [{}])[0].get('order', [])

        # Gera todas as combinações de True/False para os campos de validade
        num_valid_fields = len(validity_fields)
        total_combinations = 1 << num_valid_fields # 2^N
        log.info(f"Analisando {total_combinations} combinações de validade...")

        count = 0
        for validity_combination in itertools.product([False, True], repeat=num_valid_fields):
            # Cria um estado 'representativo' para esta combinação
            representative_state = {"input_state_index": count, "description": f"Validity combo {count}"}
            constraints = []
            signature_parts = []
            for i, (hdr_name, field_name) in enumerate(validity_fields):
                is_valid = validity_combination[i]
                # Adiciona restrição Z3 SMT-LIB (simples para validade)
                valid_var_smt_name = f"{hdr_name}.{field_name}" # Ex: ethernet.$valid$
                constraint = f"(= {valid_var_smt_name} #b{'1' if is_valid else '0'})"
                constraints.append(constraint)
                signature_parts.append(is_valid) # Usa True/False diretamente na assinatura

            representative_state["z3_constraints_smt2"] = constraints
            
            # Executa a análise Z3 para este estado representativo
            # A função analyze_single_state_emission já lida com SMT e Z3
            _is_sat, emission_status = analyze_single_state_emission(
                representative_state, fsm_data, fields_z3, deparser_order
            )

            # Armazena no cache usando a combinação como chave
            signature_tuple = tuple(signature_parts)
            deparser_cache_data["cache"][str(signature_tuple)] = emission_status # Chave JSON deve ser string

            count += 1
            if count % 100 == 0 or count == total_combinations:
                 log.info(f"... {count}/{total_combinations} combinações analisadas.")

        log.info(f"Análise estática do Deparser concluída. {len(deparser_cache_data['cache'])} entradas no cache.")

    except Exception as e:
        log.error(f"Erro durante a análise estática do deparser: {e}", exc_info=True)
        # Retorna cache vazio ou parcial em caso de erro grave
        deparser_cache_data["error"] = str(e)

    return deparser_cache_data


def analyze_table_static(table_name: str, fsm_data: dict, runtime_data: dict) -> Dict:
    """
    Pré-calcula os resultados (ação executada e parâmetros) para cada regra
    de uma tabela específica e para a ação padrão.
    """
    log.info(f"Iniciando análise estática da Tabela: {table_name}...")
    table_cache_data = {"relevant_fields": [], "cache": {}}

    try:
        # Encontra a definição da tabela no FSM
        table_def = None
        for pipeline in fsm_data.get('pipelines', []):
            for table in pipeline.get('tables', []):
                if table['name'] == table_name:
                    table_def = table
                    break
            if table_def: break

        if not table_def:
            log.error(f"Definição da tabela '{table_name}' não encontrada no FSM.")
            table_cache_data["error"] = f"Tabela '{table_name}' não encontrada."
            return table_cache_data

        # Identifica os campos chave (relevantes)
        key_fields_info = table_def.get('key', [])
        relevant_fields = []
        for key_info in key_fields_info:
            target = key_info.get('target') # Ex: ["ethernet", "etherType"]
            if isinstance(target, list) and len(target) == 2:
                relevant_fields.append(tuple(target)) # Armazena como ('header', 'field')
            else:
                 log.warning(f"Formato de chave inesperado na tabela {table_name}: {key_info}")
        table_cache_data["relevant_fields"] = relevant_fields
        log.info(f"Campos chave relevantes para {table_name}: {relevant_fields}")

        # Extrai as regras do runtime para esta tabela
        table_runtime_entries = []
        for switch_rules in runtime_data.values(): # Itera por s1, s2, etc.
             # Pega as regras do primeiro switch, assumindo que são iguais (simplificação!)
             table_runtime_entries = switch_rules.get(table_name, [])
             if table_runtime_entries: break
        log.info(f"Encontradas {len(table_runtime_entries)} regras no runtime para {table_name}.")

        cache = {}
        processed_signatures = set()

        # Processa cada regra explícita
        rule_index = 0
        for entry in table_runtime_entries:
            match_dict = entry.get('match', {})
            action_name = entry.get('action')
            action_params = entry.get('action_params', {})

            if not action_name:
                log.warning(f"Regra {rule_index} para {table_name} sem nome de ação. Pulando.")
                continue

            # Cria a assinatura baseada nos valores de match da regra
            signature_parts = []
            valid_rule = True
            for hdr, field in relevant_fields:
                # O match no runtime.json usa nomes como "hdr.proto0.protocol"
                # Precisamos encontrar o valor correspondente
                match_key_found = False
                for mk in [f"hdr.{hdr}.{field}", f"{hdr}.{field}"]: # Tenta formatos comuns
                    if mk in match_dict:
                        signature_parts.append(match_dict[mk])
                        match_key_found = True
                        break
                if not match_key_found:
                    # Se um campo chave não está no match, a regra pode ser inválida
                    # ou o campo não é usado por *esta* regra específica (ex: wildcard implícito)
                    # Para simplificar, vamos assumir um placeholder ou pular
                    # log.warning(f"Campo chave ('{hdr}', '{field}') não encontrado no match da regra {rule_index} de {table_name}. Usando None.")
                    signature_parts.append(None) # Representa "não especificado/wildcard"

            signature_tuple = tuple(signature_parts)
            cache_key = f"match_rule_{rule_index}" # Ou usa hash(signature_tuple) ?

            # Armazena o resultado (ação + params)
            cache[cache_key] = {
                "match_signature": str(signature_tuple), # Para debug
                "action_name": action_name,
                "action_params": action_params
            }
            processed_signatures.add(signature_tuple) # Guarda as assinaturas cobertas
            rule_index += 1

        # Processa a ação padrão
        default_action_info = table_def.get('default_entry', {})
        default_action_id = default_action_info.get('action_id')
        default_action_name = "Unknown_Default"
        # Mapeia ID da ação padrão para nome (precisa ler a lista de ações)
        action_id_map = {a['id']: a['name'] for a in fsm_data.get('actions', [])}
        if default_action_id is not None and default_action_id in action_id_map:
            default_action_name = action_id_map[default_action_id]
        else:
            log.warning(f"Não foi possível encontrar o nome da ação padrão (ID: {default_action_id}) para {table_name}.")

        cache["default"] = {
             "match_signature": "default",
             "action_name": default_action_name,
             "action_params": {} # Ação padrão geralmente não tem params do runtime
        }

        table_cache_data["cache"] = cache
        log.info(f"Análise estática da Tabela {table_name} concluída. {len(cache)} entradas no cache (regras + default).")

    except Exception as e:
        log.error(f"Erro durante a análise estática da tabela {table_name}: {e}", exc_info=True)
        table_cache_data["error"] = str(e)

    return table_cache_data

# --- Ponto de Entrada Principal ---

def main():
    if len(sys.argv) != 4:
        print("Uso: python3 generate_analysis_cache.py <fsm.json> <runtime.json> <output_cache.json>")
        sys.exit(1)

    fsm_filepath = Path(sys.argv[1])
    runtime_filepath = Path(sys.argv[2])
    output_cache_filepath = Path(sys.argv[3])

    log.info(f"Carregando FSM de: {fsm_filepath}")
    fsm_data = load_json_file(fsm_filepath)
    if not fsm_data:
        sys.exit(1)

    log.info(f"Carregando Runtime de: {runtime_filepath}")
    runtime_data = load_json_file(runtime_filepath)
    if not runtime_data:
        sys.exit(1)

    # Cria a estrutura principal do cache
    analysis_cache = {
        "fsm_hash": get_file_hash(fsm_filepath),
        "runtime_hash": get_file_hash(runtime_filepath),
        "deparser": {},
        "tables": {}
    }

    # Analisa o Deparser
    analysis_cache["deparser"] = analyze_deparser_static(fsm_data)

    # Analisa cada Tabela
    all_tables = []
    for pipeline in fsm_data.get('pipelines', []):
        for table in pipeline.get('tables', []):
            all_tables.append(table['name'])

    for table_name in all_tables:
        analysis_cache["tables"][table_name] = analyze_table_static(table_name, fsm_data, runtime_data)

    # Salva o cache consolidado
    try:
        output_cache_filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(output_cache_filepath, 'w', encoding='utf-8') as f:
            json.dump(analysis_cache, f, indent=2)
        log.info(f"Cache de análise persistente salvo com sucesso em: {output_cache_filepath}")
    except Exception as e:
        log.error(f"Erro ao salvar o arquivo de cache {output_cache_filepath}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()