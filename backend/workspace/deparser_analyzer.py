# deparser_analyzer.py
import logging
from typing import List, Dict, Tuple, Optional
from z3 import Solver, BitVec, sat, unsat, unknown, parse_smt2_string, Z3Exception

log = logging.getLogger(__name__)

# --- Funções de Análise do Deparser ---

def create_z3_fields(fsm_data: dict) -> Dict[Tuple[str, str], BitVec]:
    """Cria as variáveis BitVec do Z3 para todos os headers e seus campos."""
    fields_z3 = {}
    header_types_lookup = {ht['name']: ht for ht in fsm_data.get('header_types', [])}
    headers_lookup = {h['name']: h for h in fsm_data.get('headers', [])}

    for h_name, h in headers_lookup.items():
        ht_name = h.get('header_type')
        if ht_name and ht_name in header_types_lookup:
            for f_info in header_types_lookup[ht_name].get('fields', []):
                if len(f_info) >= 2:
                    f_name_full, f_width = f_info[0], f_info[1]
                    # Lida com nomes como "metadata.field" pegando só "field"
                    f_name_short = f_name_full.split('.')[-1]
                    if isinstance(f_name_full, str) and isinstance(f_width, int) and f_width > 0:
                        z3_var_name = f"{h_name}.{f_name_short}"
                        try:
                            fields_z3[(h_name, f_name_short)] = BitVec(z3_var_name, f_width)
                        except Z3Exception as e:
                            log.error(f"Erro Z3 ao criar BitVec '{z3_var_name}' width {f_width}: {e}")
                            # Continua tentando criar outros campos

        # Adiciona o campo de validade
        valid_var_name = f"{h_name}.$valid$"
        try:
             fields_z3[(h_name, '$valid$')] = BitVec(valid_var_name, 1)
        except Z3Exception as e:
            log.error(f"Erro Z3 ao criar BitVec '{valid_var_name}' width 1: {e}")

    return fields_z3

def analyze_single_state_emission(
    state_dict: dict,
    fsm_data: dict,
    fields_z3: dict, # Dicionário pré-calculado de campos Z3
    deparser_order: list # Ordem de emissão do deparser
    ) -> Tuple[bool, List[Dict]]:
    """
    Analisa simbolicamente um único estado de entrada para determinar a emissão
    de headers pelo deparser.

    Retorna:
        Uma tupla: (is_satisfiable, emission_status_list)
        onde emission_status_list é como [{"header": "...", "status": "..."}, ...]
    """

    emission_status_list = []
    state_index = state_dict.get('input_state_index', -1) # Para logs

    # --- INÍCIO DA LÓGICA EXTRAÍDA DE run_deparser.py ---

    state_constraints_smt2 = state_dict.get("z3_constraints_smt2", [])
    state_field_updates = state_dict.get("field_updates", {})

    # Monta o script SMT base (declarações + restrições do estado)
    declarations_smt2 = [f"(declare-const {var.sexpr()} (_ BitVec {var.sort().size()}))"
                         for var in fields_z3.values() if hasattr(var, 'sexpr')] # Checa se é Z3 var
    parser_constraints_smt2_asserts = [f"(assert {s})" for s in state_constraints_smt2]
    full_script = "\n".join(declarations_smt2) + "\n" + "\n".join(parser_constraints_smt2_asserts)

    solver = Solver()
    is_satisfiable = False
    try:
        # Nota: A supressão de C stdout/stderr não é necessária aqui,
        # pois não estamos rodando o executável Z3 diretamente.
        solver.from_string(full_script)
        check_result = solver.check()
        is_satisfiable = check_result == sat
        if check_result == unknown:
             # log.warning(f"Solver retornou 'unknown' para restrições base do estado {state_index}. Assumindo satisfatível.")
             is_satisfiable = True # Trata unknown como potencialmente satisfatório
    except Z3Exception as e:
        log.error(f"Falha SMT (from_string) ao analisar estado {state_index}: {e}")
        return False, [{"header": "SMT_ERROR_BASE", "status": str(e)}]
    except Exception as e: # Captura outros erros de parsing SMT-LIB
        log.error(f"Erro não-Z3 (from_string) ao analisar estado {state_index}: {e}")
        return False, [{"header": "PARSE_ERROR_BASE", "status": str(e)}]

    if not is_satisfiable:
        # O estado base já é contraditório, não há o que analisar
        return False, []

    # Aplicar field_updates ao solver ANTES de checar a emissão
    # Isso garante que as condições de emissão vejam os valores atualizados
    if state_field_updates:
         # Cria um mapa SMT-LIB name -> Z3 var object para parse_smt2_string
         # Usa var.sexpr() que é o nome SMT-LIB esperado
         decls_map = {var.sexpr(): var for key, var in fields_z3.items() if hasattr(var, 'sexpr')}
         solver.push() # Cria um escopo para os updates
         try:
             for field_str, expr_str in state_field_updates.items():
                 # Tenta mapear field_str para a chave correta em fields_z3
                 parts = field_str.split('.')
                 # Suposição: field_str é "hdr.<nome>.campo" ou "<nome>.campo" ou "standard_metadata.campo" etc.
                 # Precisamos do ('nome_header', 'nome_campo')
                 field_key: Optional[Tuple[str, str]] = None
                 if len(parts) == 2: # Ex: "ethernet.srcAddr" ou "scalars.stage0"
                     field_key = tuple(parts)
                 elif len(parts) == 3 and parts[0] == 'hdr': # Ex: "hdr.ethernet.srcAddr" -> ('ethernet', 'srcAddr')
                     field_key = (parts[1], parts[2])

                 if field_key and field_key in fields_z3:
                     target_var = fields_z3[field_key]
                     try:
                         # Tenta parsear a expressão SMT-LIB do valor
                         value_expr = parse_smt2_string(expr_str, decls=decls_map)
                         # Cria a restrição de atualização
                         update_constraint = (target_var == value_expr)
                         solver.add(update_constraint)
                     except Z3Exception as e_parse:
                         log.warning(f"Erro Z3 ao parsear/aplicar field_update '{field_str} = {expr_str}' no estado {state_index}: {e_parse}")
                     except Exception as e_non_z3: # Erro genérico no parsing SMT
                         log.warning(f"Erro não-Z3 ao parsear/aplicar field_update '{field_str} = {expr_str}' no estado {state_index}: {e_non_z3}")
                 else:
                      log.debug(f"Campo de field_update não encontrado nos Z3 vars: '{field_str}' (key={field_key})")

             # Verifica se o estado AINDA é satisfatório APÓS os updates
             if solver.check() == unsat:
                  is_satisfiable = False
                  # log.debug(f"Estado {state_index} tornou-se insatisfatório após field_updates.")
         except Exception as e_outer:
             # Erro inesperado durante o loop de updates
             log.error(f"Erro inesperado durante aplicação de field_updates no estado {state_index}: {e_outer}")
             is_satisfiable = False # Assume insatisfatório por segurança
         finally:
             if not is_satisfiable:
                 solver.pop() # Descarta o escopo dos updates se ficou insat
                 return False, [] # Estado tornou-se insatisfatório

    # Se chegou aqui, o estado (com updates) é satisfatório. Checa emissão.
    try:
        for header_name in deparser_order:
            valid_field = fields_z3.get((header_name, '$valid$'))
            if valid_field is None:
                emission_status_list.append({"header": header_name, "status": "Erro: $valid$ não definido"})
                continue

            emission_status = "Desconhecido"
            try:
                # Check if it CAN be emitted (valid == 1 is possible?)
                solver.push()
                solver.add(valid_field == 1)
                check_can_emit = solver.check()
                solver.pop()

                if check_can_emit == sat:
                    # Check if it MUST be emitted (valid == 0 is impossible?)
                    solver.push()
                    solver.add(valid_field == 0)
                    check_must_emit = solver.check() # Se unsat, então valid==0 é impossível
                    solver.pop()

                    if check_must_emit == unsat:
                        emission_status = "Sempre"
                    elif check_must_emit == sat:
                        emission_status = "Condicional"
                    else: # unknown
                        emission_status = "Desconhecido (Z3 check_must_emit unknown)"

                elif check_can_emit == unsat:
                    emission_status = "Nunca"
                else: # unknown
                     emission_status = "Desconhecido (Z3 check_can_emit unknown)"

            except Z3Exception as e_z3:
                 log.warning(f"Erro Z3 ao verificar {header_name}.$valid$ no estado {state_index}: {e_z3}")
                 emission_status = f"Erro Z3: {e_z3}"
                 # Garante que pop seja chamado mesmo em erro interno do Z3
                 try: solver.pop()
                 except Z3Exception: pass
            except Exception as e_non_z3:
                 log.error(f"Erro Não-Z3 ao verificar {header_name}.$valid$ no estado {state_index}: {e_non_z3}")
                 emission_status = f"Erro Geral: {e_non_z3}"
                 try: solver.pop()
                 except Z3Exception: pass


            emission_status_list.append({"header": header_name, "status": emission_status})
    finally:
        # Garante que o pop() correspondente ao push() antes do loop de updates seja chamado
        if state_field_updates and is_satisfiable:
             try: solver.pop()
             except Z3Exception: pass # Ignora erro se já foi feito pop ou se houve erro antes

    # --- FIM DA LÓGICA EXTRAÍDA ---

    return is_satisfiable, emission_status_list

# --- Funções de Geração de Chave de Cache ---

# Cache para os campos relevantes (calculado uma vez por FSM)
RELEVANT_FIELDS_CACHE = {}

def get_relevant_deparser_fields(fsm_data: dict) -> List[Tuple[str, str]]:
    """
    Analisa o FSM para determinar quais campos (header, field) afetam o deparser.
    ATENÇÃO: Implementação SIMPLIFICADA baseada na ordem de emissão.
             Idealmente, usaria análise de dependência mais profunda ou simbólica.
    """
    fsm_id_tuple = tuple(sorted(fsm_data.get('__meta__', {}).items())) # Cria ID imutável
    if fsm_id_tuple in RELEVANT_FIELDS_CACHE:
        return RELEVANT_FIELDS_CACHE[fsm_id_tuple]

    relevant_fields = set()
    deparser_def = fsm_data.get('deparsers', [{}])[0]
    deparser_order = deparser_def.get('order', [])
    header_types = {ht['name']: ht for ht in fsm_data.get('header_types', [])}
    headers_map = {h['name']: h for h in fsm_data.get('headers', [])}

    for hdr_name in deparser_order:
        # A validade sempre importa para emissão
        relevant_fields.add((hdr_name, '$valid$'))

        # SIMPLIFICAÇÃO: Assume que *todos* os campos do header podem importar se ele for emitido.
        # Uma análise real veria quais campos são *lidos* por ações ou condicionais
        # que afetam o '$valid$' ou outros campos relevantes.
        if hdr_name in headers_map:
            ht_name = headers_map[hdr_name].get('header_type')
            if ht_name in header_types:
                 for f_info in header_types[ht_name].get('fields', []):
                      if len(f_info) >= 1 and isinstance(f_info[0], str):
                           # Lida com nomes como "metadata.field" ou só "field"
                           field_name_parts = f_info[0].split('.')
                           actual_field_name = field_name_parts[-1]
                           relevant_fields.add((hdr_name, actual_field_name))

    # TODO (Avançado): Analisar 'field_updates' e restrições para encontrar dependências indiretas.
    # Exemplo: Se state A atualiza X baseado em Y, e o deparser depende de X, então Y também é relevante.

    # Ordena para garantir consistência da chave
    sorted_relevant_fields = sorted(list(relevant_fields))
    RELEVANT_FIELDS_CACHE[fsm_id_tuple] = sorted_relevant_fields
    log.info(f"Campos relevantes para deparser cacheados (FSM ID {hash(fsm_id_tuple)}): {len(sorted_relevant_fields)} campos.")
    return sorted_relevant_fields

def get_deparser_cache_key(state_dict: dict, relevant_fields: List[Tuple[str, str]]) -> tuple:
    """
    Gera uma chave de cache (tupla) baseada nos valores dos campos relevantes em um estado.
    """
    key_parts = []
    for hdr_name, field_name in relevant_fields:
        # Constrói o nome completo esperado no dicionário de estado
        # Ex: 'ethernet.$valid$', 'ethernet.srcAddr', 'scalars.stage0'
        # Assume que o nome no dicionário NÃO tem 'hdr.' prefixando headers normais,
        # mas pode ter prefixos como 'standard_metadata.' ou 'scalars.'.
        # A lógica exata depende de como os estados são gerados pelo run_table.py
        # Vamos tentar algumas variações comuns:
        possible_keys = [
            f"{hdr_name}.{field_name}",            # Ex: ethernet.srcAddr
            f"hdr.{hdr_name}.{field_name}",        # Ex: hdr.ethernet.srcAddr (menos provável no dict)
        ]
        
        found_value = None
        key_found = False
        for key_attempt in possible_keys:
             if key_attempt in state_dict:
                  found_value = state_dict[key_attempt]
                  key_found = True
                  break
        
        if not key_found:
             # Se não achou, usa um valor padrão. Importante para consistência.
             default_val = False if field_name == '$valid$' else 0
             found_value = default_val
             # log.debug(f"Campo relevante '{hdr_name}.{field_name}' não encontrado no estado {state_dict.get('input_state_index', -1)}. Usando default: {default_val}")

        key_parts.append(found_value)

    return tuple(key_parts)