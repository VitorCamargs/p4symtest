# run_table.py (Versão Limpa e Corrigida)
import json
import sys
from z3 import *
import os
from contextlib import contextmanager

# --- Funções Auxiliares ---
@contextmanager
def suppress_c_stdout_stderr():
    null_fd = os.open(os.devnull, os.O_RDWR)
    save_fds = [os.dup(1), os.dup(2)]
    os.dup2(null_fd, 1); os.dup2(null_fd, 2)
    try: yield
    finally:
        os.dup2(save_fds[0], 1); os.dup2(save_fds[1], 2)
        os.close(null_fd); os.close(save_fds[0]); os.close(save_fds[1])

def load_json(filename):
    try:
        with open(filename, 'r') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Erro ao carregar '{filename}': {e}"); exit(1)

def int_to_ip(ip_int):
    if not isinstance(ip_int, int): return "N/A"
    return f"{(ip_int >> 24) & 0xFF}.{(ip_int >> 16) & 0xFF}.{(ip_int >> 8) & 0xFF}.{ip_int & 0xFF}"

# --- LÓGICA DE ANÁLISE DE FLUXO DE CONTROLE ---
def build_z3_expression_for_conditional(expr_node, fields):
    if not expr_node: return BoolVal(True)
    if expr_node.get('type') == 'expression':
        return build_z3_expression_for_conditional(expr_node['value'], fields)
    op = expr_node.get('op')
    if not op: return BoolVal(True)
    if op == 'd2b':
        h, f = expr_node['right']['value']
        return fields.get((h, f)) == 1 if (h, f) in fields else BoolVal(False)
    elif op == 'not':
        return Not(build_z3_expression_for_conditional(expr_node['right'], fields))
    elif op == 'and':
        left = build_z3_expression_for_conditional(expr_node['left'], fields)
        right = build_z3_expression_for_conditional(expr_node['right'], fields)
        return And(left, right)
    return BoolVal(True)

_path_cache = {}
def find_path_to_table(pipeline_data, start_node_name, target_table_name, visited_nodes, fields):
    path_key = (start_node_name, target_table_name)
    if path_key in _path_cache: return _path_cache[path_key]
    if start_node_name == target_table_name: return []
    if start_node_name is None or start_node_name in visited_nodes: return None
    visited_nodes.add(start_node_name)

    table_node = next((t for t in pipeline_data.get('tables', []) if t['name'] == start_node_name), None)
    if table_node:
        next_node = table_node.get('base_default_next')
        path = find_path_to_table(pipeline_data, next_node, target_table_name, visited_nodes.copy(), fields)
        if path is not None:
            _path_cache[path_key] = path
            return path
            
    cond_node = next((c for c in pipeline_data.get('conditionals', []) if c['name'] == start_node_name), None)
    if cond_node:
        condition_expr = build_z3_expression_for_conditional(cond_node['expression'], fields)
        
        # Tenta o caminho 'false' primeiro
        path_from_false = find_path_to_table(pipeline_data, cond_node['false_next'], target_table_name, visited_nodes.copy(), fields)
        if path_from_false is not None:
            result = [Not(condition_expr)] + path_from_false
            _path_cache[path_key] = result
            return result
            
        # Se não encontrar, tenta o caminho 'true'
        path_from_true = find_path_to_table(pipeline_data, cond_node['true_next'], target_table_name, visited_nodes.copy(), fields)
        if path_from_true is not None:
            result = [condition_expr] + path_from_true
            _path_cache[path_key] = result
            return result
            
    _path_cache[path_key] = None
    return None

# --- LÓGICA DE EXECUÇÃO SIMBÓLICA ---
def build_z3_expression(expr_node, current_fields):
    if not expr_node: return None
    if expr_node.get('type') == 'hexstr': return int(expr_node['value'], 16)
    if expr_node.get('type') == 'field': return current_fields.get(tuple(expr_node['value']))
    if expr_node.get('type') == 'expression': return build_z3_expression(expr_node['value'], current_fields)
    op = expr_node.get('op')
    if op:
        left_z3 = build_z3_expression(expr_node.get('left'), current_fields)
        right_z3 = build_z3_expression(expr_node.get('right'), current_fields)
        if op == '+': return left_z3 + right_z3
        if op == '&': return left_z3 & right_z3
        if op == '-': return left_z3 - right_z3
    return None

def apply_symbolic_action(action_name, action_params, current_fields, fsm_data):
    action_def = next((a for a in fsm_data['actions'] if a['name'] == action_name), None)
    if not action_def: return {}
    modified_fields = {}
    for prim in action_def.get('primitives', []):
        if prim['op'] == 'mark_to_drop':
            modified_fields[('standard_metadata', 'egress_spec')] = BitVecVal(511, 9)
        elif prim['op'] == 'assign':
            dest_h, dest_f = prim['parameters'][0]['value']
            source = prim['parameters'][1]
            source_val = None
            if source['type'] == 'runtime_data':
                param_name = action_def['runtime_data'][source['value']]['name']
                source_val = action_params.get(param_name)
            elif source['type'] == 'field':
                source_val = current_fields.get(tuple(source['value']))
            elif source['type'] == 'expression':
                source_val = build_z3_expression(source, current_fields)
            if source_val is not None:
                modified_fields[(dest_h, dest_f)] = source_val
    return modified_fields

def execute_symbolic_table(table_def, current_fields, runtime_entries, fsm_data):
    next_fields = current_fields.copy()
    entries = runtime_entries.get(table_def['name'], [])
    default_action_id = table_def.get('default_entry', {}).get('action_id')
    default_action_name = "NoAction"
    if default_action_id is not None:
        default_action_name = next((a['name'] for a in fsm_data['actions'] if a['id'] == default_action_id), "NoAction")
    
    # Identifica campos modificáveis
    modifiable_fields = set()
    action_names = set([e['action'] for e in entries] + [default_action_name])
    for action_name in action_names:
        action_def = next((a for a in fsm_data['actions'] if a['name'] == action_name), {})
        for prim in action_def.get('primitives', []):
            if prim['op'] == 'mark_to_drop':
                modifiable_fields.add(('standard_metadata', 'egress_spec'))
            elif prim['op'] == 'assign':
                modifiable_fields.add(tuple(prim['parameters'][0]['value']))

    # Executa simbolicamente para cada campo modificável
    for field_key in modifiable_fields:
        default_mods = apply_symbolic_action(default_action_name, {}, current_fields, fsm_data)
        final_expr = default_mods.get(field_key, current_fields.get(field_key))
        
        for entry in reversed(entries):
            match_cond = BoolVal(True)
            for field_str, match_val in entry['match'].items():
                h, f = field_str.split('.')
                field_var = current_fields.get((h, f))
                if field_var is None:
                    match_cond = BoolVal(False)
                    break
                if isinstance(match_val, (list, tuple)):
                    val, prefix = match_val
                    bitwidth = field_var.size()
                    mask = ((1 << bitwidth) - 1) << (bitwidth - prefix)
                    match_cond = And(match_cond, (field_var & mask) == (val & mask))
                else:
                    match_cond = And(match_cond, field_var == match_val)
            if is_false(match_cond):
                continue
            
            entry_mods = apply_symbolic_action(entry['action'], entry['action_params'], current_fields, fsm_data)
            value_if_match = entry_mods.get(field_key, current_fields.get(field_key))
            final_expr = If(match_cond, value_if_match, final_expr)
        
        if final_expr is not None:
             next_fields[field_key] = simplify(final_expr)
    return next_fields

# --- Ponto de Entrada Principal ---
if __name__ == "__main__":
    if len(sys.argv) != 8:
        print("Uso: python3 run_table.py <fsm.json> <topology.json> <runtime_config.json> <estados_entrada.json> <switch_id> <nome_da_tabela> <estados_saida.json>")
        exit(1)
    
    fsm_file = sys.argv[1]
    topology_file = sys.argv[2]
    config_file = sys.argv[3]
    input_states_file = sys.argv[4]
    switch_id = sys.argv[5]
    table_name = sys.argv[6]
    output_states_file = sys.argv[7]

    # Carrega dados
    try:
        fsm_data = load_json(fsm_file)
    except:
        fsm_data = load_json("programa.json")

    topology_data = load_json(topology_file)
    runtime_entries_all = load_json(config_file)
    initial_states = load_json(input_states_file)
    runtime_entries = runtime_entries_all.get(switch_id, {})
    
    # Cria campos Z3
    fields = {}
    header_types = {ht['name']: ht for ht in fsm_data['header_types']}
    
    for h in fsm_data['headers']:
        ht_name = h['header_type']
        if ht_name in header_types:
            for f_name, f_width, _ in header_types[ht_name]['fields']:
                field_full_name = f"{h['name']}.{f_name}"
                fields[(h['name'], f_name)] = BitVec(field_full_name, f_width)
        
        # Adiciona $valid$ para todos os headers EXCETO scalars
        if h['name'] != 'scalars':
            valid_field_name = f"{h['name']}.$valid$"
            fields[(h['name'], '$valid$')] = BitVec(valid_field_name, 1)
    
    # Constrói mapa de topologia
    ip_to_host_map = {h_info['ip']: h_id for h_id, h_info in topology_data.get('hosts', {}).items()}
    port_to_destination_map = {}
    current_switch_info = topology_data.get('switches', {}).get(switch_id, {})
    
    for h_id, h_info in topology_data.get('hosts', {}).items():
        if h_info['conectado_a'].startswith(switch_id):
            port_name = h_info['conectado_a']
            port_num = current_switch_info.get('portas', {}).get(port_name)
            if port_num:
                port_to_destination_map[port_num] = f"host {h_id} (direta)"
    
    for link in topology_data.get('links', []):
        if link['from'].startswith(switch_id):
            port_name = link['from']
            dest_switch = link['to'].split('-')[0]
            port_num = current_switch_info.get('portas', {}).get(port_name)
            if port_num:
                port_to_destination_map[port_num] = f"switch {dest_switch}"
        elif link['to'].startswith(switch_id):
            port_name = link['to']
            dest_switch = link['from'].split('-')[0]
            port_num = current_switch_info.get('portas', {}).get(port_name)
            if port_num:
                port_to_destination_map[port_num] = f"switch {dest_switch}"

    # Encontra pipeline ingress
    ingress_pipeline = next((p for p in fsm_data['pipelines'] if p['name'] == 'ingress'), None)
    if not ingress_pipeline:
        print("Erro: Pipeline 'ingress' não encontrado.")
        exit(1)

    # Calcula caminho até a tabela
    print(f"Calculando caminho do pipeline até a tabela '{table_name}'...")
    _path_cache.clear()
    path_conditions = find_path_to_table(ingress_pipeline, ingress_pipeline['init_table'], table_name, set(), fields)
    if path_conditions is None:
        print(f"AVISO: A tabela '{table_name}' parece ser estruturalmente inalcançável.")

    print(f"--- Carregados {len(initial_states)} estados de '{input_states_file}' ---")
    print(f"--- Executando análise modular da tabela '{table_name}' para o SWITCH '{switch_id}' ---")
    
    output_states = []
    for i, state in enumerate(initial_states):
        print("\n" + "="*50)
        print(f"Analisando para o Estado de Entrada #{i} ({state['description']})")

        parser_constraints_smt2 = state['z3_constraints_smt2']
        
        # Prepara script SMT2
        declarations_smt2 = [f"(declare-const {var.sexpr()} (_ BitVec {var.sort().size()}))" for var in fields.values()]
        parser_assertions = [f"(assert {s})" for s in parser_constraints_smt2]
        path_assertions = [f"(assert {cond.sexpr()})" for cond in path_conditions] if path_conditions is not None else []
        
        full_script = "\n".join(declarations_smt2 + parser_assertions + path_assertions)
        
        # Verificação de alcançabilidade
        reachability_solver = Solver()
        reachability_solver.from_string(full_script)

        print("  --- Verificando Alcançabilidade (Reachability) ---")
        if reachability_solver.check() == unsat:
            print(f"  -> AVISO: Análise pulada. O pacote deste estado NUNCA alcançará a tabela '{table_name}'.")
            output_states.append(state)
            continue
        else:
            print("  -> OK: A tabela é alcançável para este tipo de pacote.")
        
        # Cria solver de análise
        analysis_solver = Solver()
        main_script = "\n".join(declarations_smt2 + parser_assertions)
        analysis_solver.from_string(main_script)
        
        # Aplica field_updates do estado anterior
        current_symbolic_fields = fields.copy()
        if "field_updates" in state:
            decls = {var.sexpr(): var for key, var in fields.items()}
            for field_str, expr_str in state["field_updates"].items():
                h, f = field_str.split('.')
                if (h, f) in current_symbolic_fields:
                    try:
                        with suppress_c_stdout_stderr():
                            current_symbolic_fields[(h, f)] = parse_smt2_string(expr_str, decls=decls)
                    except Exception as e:
                        print(f"Erro ao parsear SMT string para {field_str}: {e}")
        
        # Encontra definição da tabela
        target_table_def = next((t for t in ingress_pipeline.get('tables', []) if t['name'] == table_name), None)
        if not target_table_def:
            print(f"Erro: Definição da tabela '{table_name}' não encontrada.")
            continue

        # Executa tabela simbolicamente
        final_symbolic_fields = execute_symbolic_table(target_table_def, current_symbolic_fields, runtime_entries, fsm_data)
        
        # Análise de resultados
        print("  --- Análise de Resultados (Visão Completa) ---")
        egress_spec = final_symbolic_fields.get(('standard_metadata', 'egress_spec'))
        if egress_spec is not None:
            possible_ports = set(p for p in port_to_destination_map.keys()) | {511}
            for port_num in sorted(list(possible_ports)):
                analysis_solver.push()
                analysis_solver.add(egress_spec == port_num)
                if analysis_solver.check() == sat:
                    m = analysis_solver.model()
                    dst_addr_field = fields.get(('ipv4', 'dstAddr'))
                    target_ip_str = "N/A"
                    if dst_addr_field is not None:
                        dst_addr_val = m.eval(dst_addr_field, model_completion=True)
                        if dst_addr_val is not None:
                            target_ip_str = int_to_ip(dst_addr_val.as_long())
                    
                    target_host = ip_to_host_map.get(target_ip_str, f"IP desconhecido ({target_ip_str})")
                    if port_num == 511:
                        print(f"  -> Resultado: SIM, pacote para '{target_host}' é DESCARTADO (drop).")
                    else:
                        destination_info = port_to_destination_map.get(port_num, "desconhecido")
                        print(f"  -> Resultado: SIM, pacote para '{target_host}' é ENCAMINHADO para a porta {port_num} (em direção a: {destination_info}).")
                analysis_solver.pop()

        # Prepara estado de saída
        new_constraints = list(state['z3_constraints_smt2'])
        if egress_spec is not None:
            no_drop_constraint = (egress_spec != 511)
            analysis_solver.push()
            analysis_solver.add(no_drop_constraint)
            if analysis_solver.check() == sat:
                new_constraints.append(no_drop_constraint.sexpr())
                print("\n  --- Propagação para Próximo Estágio ---")
                print("  -> Otimização: Adicionada restrição de que o pacote não foi descartado.")
            else:
                print("\n  --- Propagação para Próximo Estágio ---")
                print("  -> AVISO: Todos os pacotes deste estado são descartados pela tabela.")
                continue
            analysis_solver.pop()
        
        # Captura field_updates
        field_updates = state.get("field_updates", {}).copy()
        for (h, f), val_expr in final_symbolic_fields.items():
            original_val = current_symbolic_fields.get((h, f))
            if val_expr is not None and original_val is not None and val_expr.sexpr() != original_val.sexpr():
                 field_updates[f"{h}.{f}"] = val_expr.sexpr()
        
        new_state = { 
            "description": state["description"] + f" -> {table_name}", 
            "z3_constraints_smt2": new_constraints, 
            "present_headers": state["present_headers"], 
            "history": state["history"] + [table_name], 
            "field_updates": field_updates 
        }
        output_states.append(new_state)

    # Salva resultados
    with open(output_states_file, 'w') as f:
        json.dump(output_states, f, indent=2)
    print(f"\nAnálise concluída. {len(output_states)} estados salvos em '{output_states_file}'.")