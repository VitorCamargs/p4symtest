# run_table_egress.py
import json
import sys
from z3 import *
import os
from contextlib import contextmanager
from pathlib import Path

# --- Funções Auxiliares (mantidas de run_table.py) ---
@contextmanager
def suppress_c_stdout_stderr():
    """Suprime a saída C/C++ do Z3."""
    null_fd = os.open(os.devnull, os.O_RDWR)
    save_fds = [os.dup(1), os.dup(2)]
    os.dup2(null_fd, 1); os.dup2(null_fd, 2)
    try: yield
    finally:
        os.dup2(save_fds[0], 1); os.dup2(save_fds[1], 2)
        os.close(null_fd); os.close(save_fds[0]); os.close(save_fds[1])

def load_json(filename):
    """Carrega um arquivo JSON e trata erros."""
    filepath = Path(filename)
    if not filepath.exists():
        print(f"Erro: Arquivo '{filepath.name}' não foi encontrado.")
        exit(1)
    try:
        with open(filepath, 'r') as f: return json.load(f)
    except json.JSONDecodeError as e:
        print(f"Erro: Arquivo '{filepath.name}' não é um JSON válido: {e}")
        exit(1)
    except Exception as e:
        print(f"Erro inesperado ao carregar '{filepath.name}': {e}")
        exit(1)

# --- LÓGICA DE ANÁLISE DE FLUXO DE CONTROLE (adaptada para Egress) ---

# Cache para a função find_path_to_table
_path_cache = {}

def build_z3_expression_for_conditional(expr_node, fields):
    """Constrói uma expressão booleana Z3 para um condicional do FSM."""
    if not expr_node: return BoolVal(True)

    node_type = expr_node.get('type')
    op = expr_node.get('op')

    if node_type == 'expression':
        # Desce na estrutura aninhada se houver 'value'
        return build_z3_expression_for_conditional(expr_node.get('value'), fields)

    if op == 'd2b': # Geralmente usado para verificar a validade do header (header.$valid$)
        # 'd2b' geralmente tem 'right' como o campo a ser verificado
        field_node = expr_node.get('right')
        if field_node and field_node.get('type') == 'field':
            field_key = tuple(field_node['value']) # Ex: ('ethernet', '$valid$')
            field_var = fields.get(field_key)
            if field_var is not None:
                # Retorna a condição Z3 field == 1
                return field_var == 1
            else:
                # print(f"Aviso: Campo $valid$ {field_key} não encontrado em build_z3_expression_for_conditional.")
                return BoolVal(False) # Se o campo não existe, não é válido
        else:
            print(f"Aviso: Operador 'd2b' sem campo válido à direita: {expr_node}")
            return BoolVal(False) # Condição inválida

    elif op == 'not':
        right_expr = build_z3_expression_for_conditional(expr_node.get('right'), fields)
        return Not(right_expr)

    elif op == 'and':
        left_expr = build_z3_expression_for_conditional(expr_node.get('left'), fields)
        right_expr = build_z3_expression_for_conditional(expr_node.get('right'), fields)
        return And(left_expr, right_expr)

    elif op == '==' or op == '!=' or op == '>' or op == '<' or op == '>=' or op == '<=':
        # Lógica para operadores de comparação (pode precisar de build_z3_expression normal)
        # Por enquanto, assume que não são usados em condicionais de pipeline Egress
        print(f"Aviso: Operador de comparação '{op}' não implementado diretamente em condicionais de pipeline.")
        return BoolVal(True) # Ou False, dependendo da semântica desejada

    # Fallback para outros tipos ou estruturas não reconhecidas
    print(f"Aviso: Tipo de expressão condicional não tratada: {expr_node}")
    return BoolVal(True) # Assume True para não bloquear caminhos inesperadamente


def find_path_to_table(pipeline_data, start_node_name, target_table_name, visited_nodes, fields):
    """Encontra um caminho e suas condições Z3 de start_node_name até target_table_name no grafo do pipeline."""
    path_key = (start_node_name, target_table_name)
    if path_key in _path_cache: return _path_cache[path_key]

    # Caso base: Já estamos na tabela alvo
    if start_node_name == target_table_name: return []

    # Caso base: Nó inválido ou já visitado neste caminho (ciclo)
    if start_node_name is None or start_node_name in visited_nodes: return None

    # Marca o nó atual como visitado para este caminho
    visited_nodes.add(start_node_name)

    # Verifica se o nó atual é uma tabela
    table_node = next((t for t in pipeline_data.get('tables', []) if t['name'] == start_node_name), None)
    if table_node:
        next_node_name = table_node.get('base_default_next') # Pega o próximo nó padrão após esta tabela
        # Recursivamente busca o caminho a partir do próximo nó
        path_from_here = find_path_to_table(pipeline_data, next_node_name, target_table_name, visited_nodes.copy(), fields)
        if path_from_here is not None:
            # Encontrou um caminho, retorna as condições acumuladas (nenhuma adicionada por esta tabela)
            _path_cache[path_key] = path_from_here
            return path_from_here

    # Verifica se o nó atual é um condicional (if)
    cond_node = next((c for c in pipeline_data.get('conditionals', []) if c['name'] == start_node_name), None)
    if cond_node:
        # Constrói a expressão Z3 para a condição do 'if'
        condition_expr = build_z3_expression_for_conditional(cond_node.get('expression'), fields)

        # 1. Tenta o caminho 'true'
        true_next_node = cond_node.get('true_next')
        path_from_true = find_path_to_table(pipeline_data, true_next_node, target_table_name, visited_nodes.copy(), fields)
        if path_from_true is not None:
            # Encontrou caminho via 'true', retorna [condição] + condições_restantes
            result = [condition_expr] + path_from_true
            _path_cache[path_key] = result
            return result

        # 2. Tenta o caminho 'false'
        false_next_node = cond_node.get('false_next')
        path_from_false = find_path_to_table(pipeline_data, false_next_node, target_table_name, visited_nodes.copy(), fields)
        if path_from_false is not None:
            # Encontrou caminho via 'false', retorna [Not(condição)] + condições_restantes
            result = [Not(condition_expr)] + path_from_false
            _path_cache[path_key] = result
            return result

    # Se não for tabela nem condicional que leva ao alvo, este caminho não funciona
    _path_cache[path_key] = None
    return None

# --- LÓGICA DE EXECUÇÃO SIMBÓLICA ---

def build_z3_expression(expr_node, current_fields):
    """Constrói uma expressão Z3 a partir de um nó de expressão do FSM JSON."""
    if not expr_node: return None
    node_type = expr_node.get('type')

    if node_type == 'hexstr':
        try:
            val = int(expr_node['value'], 16)
            # Tenta inferir bitwidth - pode precisar de ajustes
            if val < 512: return BitVecVal(val, 9)
            elif val < 65536: return BitVecVal(val, 16)
            elif val < 2**32: return BitVecVal(val, 32)
            elif val < 2**48: return BitVecVal(val, 48)
            else: return val # Fallback
        except ValueError: return None
        except Exception: return None # Protege contra erros de BitVecVal
    elif node_type == 'field':
        return current_fields.get(tuple(expr_node['value']))
    elif node_type == 'expression':
        return build_z3_expression(expr_node.get('value'), current_fields)
    elif node_type == 'runtime_data':
         # print(f"Aviso: 'runtime_data' em build_z3_expression: {expr_node}")
         return None # Tratado em apply_symbolic_action

    op = expr_node.get('op')
    if op:
        left_z3 = build_z3_expression(expr_node.get('left'), current_fields)
        right_z3 = build_z3_expression(expr_node.get('right'), current_fields)
        # Garante que ambos os lados são expressões Z3 ou None antes de operar
        is_left_z3 = isinstance(left_z3, z3.ExprRef)
        is_right_z3 = isinstance(right_z3, z3.ExprRef)

        try:
            if op == '+':
                if is_left_z3 and is_right_z3: return left_z3 + right_z3
            elif op == '&':
                if is_left_z3 and is_right_z3: return left_z3 & right_z3
            elif op == '-':
                if is_left_z3 and is_right_z3: return left_z3 - right_z3
            elif op == 'd2b': # Precisa apenas do right
                 field_expr = build_z3_expression(expr_node.get('right'), current_fields)
                 return field_expr == 1 if isinstance(field_expr, z3.ExprRef) else BoolVal(False)
            elif op == 'not': # Precisa apenas do right
                 inner_expr = build_z3_expression(expr_node.get('right'), current_fields)
                 return Not(inner_expr) if isinstance(inner_expr, z3.ExprRef) else BoolVal(True)
            elif op == 'and':
                 if is_left_z3 and is_right_z3: return And(left_z3, right_z3)
            # Adicione outros operadores se necessário (ex: '==', '<', etc.)
            else:
                 print(f"Aviso: Operador Z3 não suportado '{op}' em build_z3_expression.")

        except z3.Z3Exception as e:
            print(f"Erro Z3 ao aplicar operador '{op}': {e}. Left: {left_z3}, Right: {right_z3}")
            return None
        # Se chegou aqui sem retornar, significa que os operandos não eram válidos para o op
        if op not in ['d2b', 'not']: # Esses ops só precisam de um lado
             # print(f"Aviso: Operador '{op}' com operandos não Z3 ou nulos. Left: {left_z3}, Right: {right_z3}")
             pass
        return None # Falha na operação
    # print(f"Aviso: Tipo de nó de expressão não tratado: {expr_node}")
    return None


def apply_symbolic_action(action_name, action_params, current_fields, fsm_data, action_defs):
    """Aplica os efeitos de uma ação P4 simbolicamente."""
    action_def = action_defs.get(action_name)
    if not action_def: return {}

    modified_fields = {}
    for prim in action_def.get('primitives', []):
        op = prim.get('op')
        params = prim.get('parameters', [])
        if op == 'assign' and len(params) == 2:
            dest = params[0]
            source = params[1]
            if dest['type'] == 'field':
                dest_key = tuple(dest['value'])
                dest_var = current_fields.get(dest_key) # Pega a variável Z3 de destino para obter bitwidth
                source_val = None

                if source['type'] == 'runtime_data':
                    param_index = source['value']
                    if param_index < len(action_def.get('runtime_data',[])):
                        param_def = action_def['runtime_data'][param_index]
                        param_name = param_def['name']
                        param_bitwidth = param_def['bitwidth']
                        concrete_val = action_params.get(param_name)
                        if concrete_val is not None:
                            try:
                                source_val = BitVecVal(concrete_val, param_bitwidth)
                            except Exception as e:
                                print(f"Erro ao criar BitVecVal para {param_name}={concrete_val} (width {param_bitwidth}): {e}")
                        else:
                            print(f"Aviso: Valor para parâmetro '{param_name}' não encontrado em action_params para ação '{action_name}'.")
                    else:
                        print(f"Erro: Índice runtime_data inválido {param_index} na ação '{action_name}'.")

                elif source['type'] == 'field':
                    source_key = tuple(source['value'])
                    source_val = current_fields.get(source_key)
                    # if source_val is None: print(f"Aviso: Campo fonte '{source_key}' não encontrado.")

                elif source['type'] == 'expression':
                    source_val = build_z3_expression(source, current_fields)
                    # if source_val is None: print(f"Aviso: Falha ao construir expressão Z3 para atribuição em '{dest_key}'.")

                elif source['type'] == 'hexstr':
                     try:
                         val = int(source['value'], 16)
                         if dest_var is not None: # Usa bitwidth do destino se disponível
                             source_val = BitVecVal(val, dest_var.size())
                         else: # Tenta inferir se não tem destino (menos preciso)
                             if val < 2**16: source_val = BitVecVal(val, 16)
                             elif val < 2**32: source_val = BitVecVal(val, 32)
                             elif val < 2**48: source_val = BitVecVal(val, 48)
                             else: source_val = val # Fallback
                             # print(f"Aviso: Bitwidth para hexstr '{source['value']}' inferido/fallback para atribuição em '{dest_key}'.")
                     except ValueError: pass # print(f"Aviso: Falha ao converter hexstr '{source['value']}' em atribuição.")
                     except Exception as e: pass # print(f"Erro ao criar BitVecVal para hexstr {source['value']}: {e}")

                # Aplica e ajusta tamanho se necessário
                if source_val is not None:
                    if dest_var is not None and isinstance(source_val, z3.BitVecRef) and dest_var.size() != source_val.size():
                        # print(f"Aviso: Ajustando tamanho Z3 em '{action_name}': {dest_key} ({dest_var.size()}) = {source_val} ({source_val.size()}).")
                        if dest_var.size() > source_val.size():
                            source_val = ZeroExt(dest_var.size() - source_val.size(), source_val)
                        else:
                            source_val = Extract(dest_var.size() - 1, 0, source_val)
                    elif dest_var is not None and isinstance(source_val, int):
                         source_val = BitVecVal(source_val, dest_var.size()) # Converte int para BitVecVal

                    modified_fields[dest_key] = source_val

        # Adicione outras primitivas se necessário (ex: mark_to_drop)
        elif op == 'mark_to_drop':
             pass # Efeito não modelado nas variáveis aqui

    return modified_fields


def execute_symbolic_table_egress(table_def, current_fields, runtime_entries, fsm_data, action_defs):
    """Executa uma tabela Egress simbolicamente."""
    next_fields = current_fields.copy()
    entries = runtime_entries.get(table_def['name'], []) # Pega entradas para esta tabela específica

    # Obtém a ação padrão
    default_action_id = table_def.get('default_entry', {}).get('action_id')
    default_action_name = "NoAction"
    if default_action_id is not None:
        action_info = next((a for a in fsm_data.get('actions', []) if a['id'] == default_action_id), None)
        if action_info: default_action_name = action_info['name']

    # Identifica campos modificáveis
    modifiable_fields = set()
    possible_action_names = set(entry['action'] for entry in entries) | {default_action_name}
    for action_name in possible_action_names:
        action_def = action_defs.get(action_name)
        if not action_def: continue
        for prim in action_def.get('primitives', []):
            if prim.get('op') == 'assign' and prim['parameters'][0]['type'] == 'field':
                modifiable_fields.add(tuple(prim['parameters'][0]['value']))

    # Aplica ação padrão para valor base
    default_action_mods = apply_symbolic_action(default_action_name, {}, current_fields, fsm_data, action_defs)

    # Itera sobre campos modificáveis
    for field_key in modifiable_fields:
        final_expr_for_field = default_action_mods.get(field_key, current_fields.get(field_key))

        # Itera sobre entradas em ordem REVERSA
        for entry in reversed(entries):
            match_cond = BoolVal(True)

            # Constrói condição de match
            for field_str, match_val_info in entry.get('match', {}).items():
                field_key_match = tuple(field_str.split('.'))
                field_var = current_fields.get(field_key_match)
                if field_var is None:
                    # print(f"Aviso: Campo chave '{field_str}' não encontrado. Ignorando entrada.")
                    match_cond = BoolVal(False); break

                match_type = next((k['match_type'] for k in table_def['key'] if k.get('name') == field_str or k.get('target') == list(field_key_match)), 'exact')

                entry_cond = None
                if match_type == 'exact':
                    concrete_val = match_val_info
                    try:
                        entry_cond = (field_var == BitVecVal(concrete_val, field_var.size()))
                    except Exception as e:
                        print(f"Erro Z3 ao criar condição 'exact' para {field_str} == {concrete_val}: {e}")
                        match_cond = BoolVal(False); break
                # Adicione outros tipos de match se necessário
                else:
                    print(f"Aviso: Tipo de match '{match_type}' não suportado na tabela Egress '{table_def['name']}'.")
                    match_cond = BoolVal(False); break

                if entry_cond is not None:
                    match_cond = And(match_cond, entry_cond)
                elif not is_false(match_cond):
                    match_cond = BoolVal(False); break

            # Se a condição de match ainda pode ser verdadeira
            if not is_false(match_cond):
                entry_action_mods = apply_symbolic_action(entry['action'], entry.get('action_params', {}), current_fields, fsm_data, action_defs)
                value_if_this_entry_matches = entry_action_mods.get(field_key, current_fields.get(field_key))

                # Constrói If-Then-Else
                final_expr_for_field = If(match_cond, value_if_this_entry_matches, final_expr_for_field)

        # Atualiza o campo simbólico com a expressão final
        if final_expr_for_field is not None:
             try:
                 simplified_expr = simplify(final_expr_for_field)
                 next_fields[field_key] = simplified_expr
             except z3.Z3Exception as e:
                  print(f"Erro Z3 ao simplificar expressão para {field_key}: {e}")
                  next_fields[field_key] = final_expr_for_field # Mantém não simplificado

    return next_fields


# --- Ponto de Entrada Principal ---
if __name__ == "__main__":
    if len(sys.argv) != 7:
        print("Uso: python3 run_table_egress.py <fsm.json> <runtime_config.json> <estados_entrada.json> <switch_id> <nome_tabela_egress> <estados_saida.json>")
        exit(1)

    fsm_file = sys.argv[1]
    config_file = sys.argv[2]
    input_states_file = sys.argv[3]
    switch_id = sys.argv[4]
    table_name = sys.argv[5] # Nome da tabela Egress alvo
    output_states_file = sys.argv[6]

    # Carrega dados
    fsm_data = load_json(fsm_file)
    runtime_entries_all = load_json(config_file)
    initial_states = load_json(input_states_file)
    runtime_entries = runtime_entries_all.get(switch_id, {})

    # --- Cria campos Z3 (Abordagem Reforçada) ---
    fields = {}
    header_types = {ht['name']: ht for ht in fsm_data.get('header_types', [])}
    all_header_names_in_fsm = [h.get('name') for h in fsm_data.get('headers', []) if h.get('name')] # Nomes definidos no FSM

    # 1. Cria campos normais (não $valid$)
    for h_name in all_header_names_in_fsm:
        if h_name == 'scalars': continue # Ignora 'scalars'

        header_def = next((h for h in fsm_data['headers'] if h.get('name') == h_name), None)
        header_type_def_name = None
        if h_name == 'standard_metadata':
            std_meta_type_def = next((ht for ht in fsm_data.get('header_types', []) if ht['name'] == 'standard_metadata'), None)
            if std_meta_type_def: header_type_def_name = 'standard_metadata'
        elif header_def:
            header_type_def_name = header_def.get('header_type')

        if header_type_def_name and header_type_def_name in header_types:
            ht_def = header_types[header_type_def_name]
            for f_info in ht_def.get('fields', []):
                if len(f_info) >= 2:
                    f_name, f_width = f_info[0], f_info[1]
                    if isinstance(f_name, str) and isinstance(f_width, int) and f_width > 0:
                        field_key = (h_name, f_name)
                        z3_var_name = f"{h_name}.{f_name}"
                        fields[field_key] = BitVec(z3_var_name, f_width)

    # 2. Cria TODOS os campos $valid$ necessários (incluindo standard_metadata.$valid$)
    for h_name in all_header_names_in_fsm:
        if h_name != 'scalars':
            field_key = (h_name, '$valid$')
            z3_var_name = f"{h_name}.$valid$"
            fields[field_key] = BitVec(z3_var_name, 1)

    # --- Fim da Criação de Campos Z3 ---


    # Mapa de ações
    action_defs = {a['name']: a for a in fsm_data.get('actions', [])}

    # Encontra pipeline egress e a tabela alvo dentro dele
    egress_pipeline = next((p for p in fsm_data.get('pipelines', []) if p.get('name') == 'egress'), None)
    if not egress_pipeline:
        print("Erro: Pipeline 'egress' não encontrado no FSM.")
        exit(1)

    target_table_def = next((t for t in egress_pipeline.get('tables', []) if t['name'] == table_name), None)
    if not target_table_def:
        print(f"Erro: Tabela Egress '{table_name}' não encontrada no pipeline Egress.")
        with open(output_states_file, 'w') as f: json.dump([], f) # Salva JSON vazio
        exit(1)

    # Calcula caminho ATÉ a tabela DENTRO do pipeline Egress
    print(f"Calculando caminho do pipeline Egress até a tabela '{table_name}'...")
    _path_cache.clear()
    egress_start_node = egress_pipeline.get("init_table") # Pode ser None
    path_conditions = find_path_to_table(egress_pipeline, egress_start_node, table_name, set(), fields)

    if path_conditions is None:
        print(f"AVISO: A tabela '{table_name}' parece ser estruturalmente inalcançável dentro do pipeline Egress.")
        # Decide o que fazer: sair ou continuar

    print(f"--- Carregados {len(initial_states)} estados de '{Path(input_states_file).name}' ---")
    print(f"--- Executando análise modular da tabela Egress '{table_name}' para o SWITCH '{switch_id}' ---")

    output_states = []
    analysis_solver = Solver() # Cria fora do loop

    for i, state in enumerate(initial_states):
        print("\n" + "="*50)
        print(f"Analisando para o Estado de Entrada #{i} ({state.get('description', 'Sem descrição')})")

        # --- VERIFICAÇÃO DE ALCANÇABILIDADE/SATISFATIBILIDADE ---
        analysis_solver.reset()
        # Gera declarações SMT2 para TODAS as variáveis Z3 criadas
        declarations_smt2 = [f"(declare-const {var.sexpr()} (_ BitVec {var.sort().size()}))" for var in fields.values()]
        parser_constraints_smt2 = state.get('z3_constraints_smt2', [])
        parser_assertions = [f"(assert {s})" for s in parser_constraints_smt2]
        path_assertions = [f"(assert {cond.sexpr()})" for cond in path_conditions] if path_conditions is not None else []

        full_script = "\n".join(declarations_smt2 + parser_assertions + path_assertions)

        try:
            with suppress_c_stdout_stderr():
                analysis_solver.from_string(full_script)
            check_result = analysis_solver.check()

            if check_result == unsat:
                if path_conditions is not None:
                     print(f"  -> AVISO: Análise pulada. Estado + Condições do Egress INALCANÇÁVEIS.")
                else: # path_conditions is None -> estruturalmente inalcançável
                     print(f"  -> AVISO: Análise pulada. Tabela estruturalmente inalcançável OU estado de entrada insatisfatório.")
                continue # Pula para o próximo estado
            # else: print("  -> OK: Estado + Condições do caminho Egress são satisfatórios.")

        except z3.Z3Exception as e:
             print(f"  -> ERRO Z3: Falha ao carregar/verificar restrições Egress para estado #{i}: {e}. Script SMT:\n{full_script}\nPulando.")
             continue
        except Exception as e: # Captura outros erros de parsing SMT
             print(f"  -> ERRO Inesperado: Falha ao processar SMT para estado #{i}: {e}. Script SMT:\n{full_script}\nPulando.")
             continue


        # --- EXECUÇÃO SIMBÓLICA DA TABELA EGRESS ---
        current_symbolic_fields = fields.copy() # Começa com os campos base
        # Aplica field_updates do estado de entrada
        if "field_updates" in state:
            decls = {var.sexpr(): var for key, var in fields.items()} # Mapa nome SMT -> var Z3
            for field_str, expr_str in state["field_updates"].items():
                field_key = tuple(field_str.split('.'))
                if field_key in current_symbolic_fields:
                    try:
                        # Parseia a string SMT2 usando as declarações existentes
                        with suppress_c_stdout_stderr():
                            updated_expr = parse_smt2_string(expr_str, decls=decls)
                        current_symbolic_fields[field_key] = updated_expr
                    except z3.Z3Exception as e:
                        print(f"Erro Z3 ao parsear SMT para field_update '{field_str}' no estado #{i}: {e}")
                    except Exception as e:
                         print(f"Erro inesperado ao parsear SMT para '{field_str}': {e}")
                # else: print(f"Aviso: Campo '{field_str}' de field_updates não encontrado.")

        # Executa a tabela Egress
        final_symbolic_fields = execute_symbolic_table_egress(
             target_table_def,
             current_symbolic_fields,
             runtime_entries,
             fsm_data,
             action_defs
        )

        # --- GERAÇÃO DE ESTADO DE SAÍDA ---
        table_field_updates = {}
        for field_key, final_val_expr in final_symbolic_fields.items():
            initial_val_expr = current_symbolic_fields.get(field_key)
            final_smt, initial_smt = None, None
            try:
                if final_val_expr is not None: final_smt = simplify(final_val_expr).sexpr()
                if initial_val_expr is not None: initial_smt = simplify(initial_val_expr).sexpr()
            except z3.Z3Exception: # Se simplificação falhar, usa não simplificado
                 if final_val_expr is not None: final_smt = final_val_expr.sexpr()
                 if initial_val_expr is not None: initial_smt = initial_val_expr.sexpr()

            if final_smt != initial_smt: # Compara as strings SMT
                 field_str = f"{field_key[0]}.{field_key[1]}"
                 if final_smt is not None:
                     table_field_updates[field_str] = final_smt
                 # else: handle caso onde campo se torna nulo?

        combined_field_updates = state.get("field_updates", {}).copy()
        combined_field_updates.update(table_field_updates)

        new_state = {
            "description": state.get("description", "???") + f" -> {table_name}",
            "z3_constraints_smt2": parser_constraints_smt2, # Mantém restrições originais
            "present_headers": state.get("present_headers", []),
            "history": state.get("history", []) + [table_name],
            "field_updates": combined_field_updates
        }
        output_states.append(new_state)
        print(f"  -> Estado de saída gerado com {len(table_field_updates)} novas atualizações de campo.")

    # --- SALVAR RESULTADOS ---
    output_path = Path(output_states_file)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(output_states, f, indent=2)
        print(f"\nAnálise da tabela Egress concluída. {len(output_states)} estados salvos em '{output_path.name}'.")
    except Exception as e:
        print(f"\nErro ao salvar resultados em '{output_path.name}': {e}")
        exit(1)