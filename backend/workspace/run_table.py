# run_table.py
# --- VERSÃO CORRIGIDA - Alcançabilidade considerando field_updates ---
import json
import sys
from z3 import *
import os
from contextlib import contextmanager

# --- FUNÇÕES AUXILIARES ---
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
    """
    Constrói uma expressão Z3 para os nós 'conditionals' do pipeline.
    """
    if not expr_node: return BoolVal(True)
    
    if expr_node.get('type') == 'expression':
        return build_z3_expression_for_conditional(expr_node['value'], fields)

    op = expr_node.get('op')
    if not op:
        return BoolVal(True)

    if op == 'd2b':
        h, f = expr_node['right']['value']
        return fields.get((h, f)) == 1
    
    elif op == 'not':
        right_expr = build_z3_expression_for_conditional(expr_node['right'], fields)
        return Not(right_expr)
        
    elif op == 'and':
        left_expr = build_z3_expression_for_conditional(expr_node['left'], fields)
        right_expr = build_z3_expression_for_conditional(expr_node['right'], fields)
        return And(left_expr, right_expr)

    return BoolVal(True)

_path_cache = {}
def find_path_to_table(pipeline_data, start_node_name, target_table_name, visited_nodes, fields):
    """
    Encontra o caminho de condições do pipeline até a tabela alvo.
    """
    path_key = (start_node_name, target_table_name)
    if path_key in _path_cache: return _path_cache[path_key]
    if start_node_name == target_table_name: return []
    if start_node_name is None or start_node_name in visited_nodes: return None
    visited_nodes.add(start_node_name)
    
    table_node = next((t for t in pipeline_data['tables'] if t['name'] == start_node_name), None)
    if table_node:
        path = find_path_to_table(pipeline_data, table_node.get('base_default_next'), target_table_name, visited_nodes.copy(), fields)
        if path is not None: _path_cache[path_key] = path; return path
    
    cond_node = next((c for c in pipeline_data['conditionals'] if c['name'] == start_node_name), None)
    if cond_node:
        condition_expr = build_z3_expression_for_conditional(cond_node['expression'], fields)
        
        # Testa FALSE_NEXT primeiro (importante!)
        path_from_false = find_path_to_table(pipeline_data, cond_node['false_next'], target_table_name, visited_nodes.copy(), fields)
        if path_from_false is not None:
            result = [Not(condition_expr)] + path_from_false
            _path_cache[path_key] = result
            return result
        
        # Depois testa TRUE_NEXT
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
        left_z3, right_z3 = build_z3_expression(expr_node.get('left'), current_fields), build_z3_expression(expr_node.get('right'), current_fields)
        if op == '+': return left_z3 + right_z3
        if op == '&': return left_z3 & right_z3
        if op == '-': return left_z3 - right_z3
    return None

def apply_symbolic_action(action_name, action_params, current_fields, fsm_data):
    action_def = next((a for a in fsm_data['actions'] if a['name'] == action_name), None)
    if not action_def: return {}
    modified_fields = {}
    for prim in action_def.get('primitives', []):
        if prim['op'] == 'mark_to_drop': modified_fields[('standard_metadata', 'egress_spec')] = BitVecVal(511, 9)
        elif prim['op'] == 'assign':
            dest_h, dest_f = prim['parameters'][0]['value']
            source, source_val = prim['parameters'][1], None
            if source['type'] == 'runtime_data':
                param_name = action_def['runtime_data'][source['value']]['name']
                source_val = action_params.get(param_name)
            elif source['type'] == 'field': source_val = current_fields.get(tuple(source['value']))
            elif source['type'] == 'expression': source_val = build_z3_expression(source, current_fields)
            if source_val is not None: modified_fields[(dest_h, dest_f)] = source_val
    return modified_fields

def execute_symbolic_table(table_def, current_fields, runtime_entries, fsm_data):
    next_fields = current_fields.copy()
    entries = runtime_entries.get(table_def['name'], [])
    default_action_name = next(a['name'] for a in fsm_data['actions'] if a['id'] == table_def['default_entry']['action_id'])
    modifiable_fields = set()
    for action_name in set([e['action'] for e in entries] + [default_action_name]):
        action_def = next((a for a in fsm_data['actions'] if a['name'] == action_name), {})
        for prim in action_def.get('primitives', []):
            if prim['op'] == 'mark_to_drop': modifiable_fields.add(('standard_metadata', 'egress_spec'))
            elif prim['op'] == 'assign': modifiable_fields.add(tuple(prim['parameters'][0]['value']))
    for field_key in modifiable_fields:
        default_mods = apply_symbolic_action(default_action_name, {}, current_fields, fsm_data)
        final_expr = default_mods.get(field_key, current_fields.get(field_key))
        for entry in reversed(entries):
            match_cond = True
            for field_str, match_val in entry['match'].items():
                h, f = field_str.split('.')
                field_var = current_fields.get((h, f))
                if field_var is None: continue
                if isinstance(match_val, (list, tuple)):
                    val, prefix = match_val; bitwidth = field_var.size()
                    mask = ((1 << bitwidth) - 1) << (bitwidth - prefix)
                    match_cond = And(match_cond, (field_var & mask) == (val & mask))
                else: match_cond = And(match_cond, field_var == match_val)
            entry_mods = apply_symbolic_action(entry['action'], entry['action_params'], current_fields, fsm_data)
            value_if_match = entry_mods.get(field_key, current_fields.get(field_key))
            final_expr = If(match_cond, value_if_match, final_expr)
        next_fields[field_key] = final_expr
    return next_fields

def get_target_identifier(table_def, fields, model, ip_to_host_map):
    """
    Identifica o alvo do pacote baseado na tabela sendo analisada.
    """
    if 'ipv4_lpm' in table_def['name']:
        dst_addr_field = fields.get(('ipv4', 'dstAddr'))
        if dst_addr_field is not None:
            try:
                dst_addr_val = model.eval(dst_addr_field, model_completion=True)
                if hasattr(dst_addr_val, 'as_long'):
                    ip_int = dst_addr_val.as_long()
                    ip_str = int_to_ip(ip_int)
                    target_host = ip_to_host_map.get(ip_str, f"IP {ip_str}")
                    return (target_host, ip_str)
            except Exception as e:
                pass
    
    elif 'myTunnel' in table_def['name']:
        dst_id_field = fields.get(('myTunnel', 'dst_id'))
        if dst_id_field is not None:
            try:
                dst_id_val = model.eval(dst_id_field, model_completion=True)
                if hasattr(dst_id_val, 'as_long'):
                    tunnel_id = dst_id_val.as_long()
                    return (f"Tunnel ID {tunnel_id}", str(tunnel_id))
            except Exception as e:
                pass
    
    return ("destino desconhecido", "N/A")

# --- Ponto de Entrada Principal ---
if __name__ == "__main__":
    if len(sys.argv) != 8:
        print("Uso: python3 run_table.py <fsm.json> <topology.json> <runtime_config.json> <estados_entrada.json> <switch_id> <nome_da_tabela> <estados_saida.json>")
        exit(1)
    fsm_file, topology_file, config_file, input_states_file, switch_id, table_name, output_states_file = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6], sys.argv[7]

    fsm_data = load_json(fsm_file)
    topology_data = load_json(topology_file)
    runtime_entries_all = load_json(config_file)
    initial_states = load_json(input_states_file)
    runtime_entries = runtime_entries_all.get(switch_id)
    if runtime_entries is None: print(f"Erro: Não foram encontradas regras para o switch '{switch_id}'."); exit(1)
    
    fields = {}
    header_types = {ht['name']: ht for ht in fsm_data['header_types']}
    for h in fsm_data['headers']:
        ht_name = h['header_type']
        if ht_name in header_types:
            for f_name, f_width, _ in header_types[ht_name]['fields']: fields[(h['name'], f_name)] = BitVec(f"{h['name']}.{f_name}", f_width)
        fields[(h['name'], '$valid$')] = BitVec(f"{h['name']}.$valid$", 1)
    
    ip_to_host_map = {h_info['ip']: h_id for h_id, h_info in topology_data.get('hosts', {}).items()}
    port_to_destination_map = {}
    current_switch_info = topology_data.get('switches', {}).get(switch_id, {})
    for h_id, h_info in topology_data.get('hosts', {}).items():
        if h_info['conectado_a'].startswith(switch_id):
            port_name, port_num = h_info['conectado_a'], current_switch_info.get('portas', {}).get(h_info['conectado_a'])
            if port_num: port_to_destination_map[port_num] = f"host {h_id} (conexão direta)"
    for link in topology_data.get('links', []):
        if link['from'].startswith(switch_id):
            port_name, dest_switch, port_num = link['from'], link['to'].split('-')[0], current_switch_info.get('portas', {}).get(link['from'])
            if port_num: port_to_destination_map[port_num] = f"switch {dest_switch}"
        elif link['to'].startswith(switch_id):
            port_name, dest_switch, port_num = link['to'], link['from'].split('-')[0], current_switch_info.get('portas', {}).get(link['to'])
            if port_num: port_to_destination_map[port_num] = f"switch {dest_switch}"

    ingress_pipeline = next((p for p in fsm_data['pipelines'] if p['name'] == 'ingress'), None)
    if not ingress_pipeline: print("Erro: Pipeline 'ingress' não encontrado."); exit(1)

    table_def = next((t for t in ingress_pipeline['tables'] if t['name'] == table_name), None)
    if not table_def: print(f"Erro: Tabela '{table_name}' não encontrada."); exit(1)

    print(f"Calculando caminho do pipeline até a tabela '{table_name}'...")
    _path_cache.clear()
    path_conditions = find_path_to_table(ingress_pipeline, ingress_pipeline['init_table'], table_name, set(), fields)
    
    if path_conditions is None: 
        print(f"AVISO: A tabela '{table_name}' parece ser inalcançável a partir do início do pipeline.")
    else:
        print(f"Condições de caminho encontradas: {len(path_conditions)} restrições")
        for i, cond in enumerate(path_conditions, 1):
            print(f"  {i}. {cond}")

    print(f"--- Carregados {len(initial_states)} estados de '{input_states_file}' ---")
    print(f"--- Executando análise modular da tabela '{table_name}' para o SWITCH '{switch_id}' ---")
    
    output_states = []
    for i, state in enumerate(initial_states):
        print("\n" + "="*50)
        print(f"Analisando para o Estado de Entrada #{i} ({state['description']})")

        # 1. Carrega as restrições do parser
        parser_constraints = []
        decls = {var.sexpr(): var for key, var in fields.items()}
        with suppress_c_stdout_stderr():
            for constraint_str in state['z3_constraints_smt2']:
                parser_constraints.append(parse_smt2_string(constraint_str, decls=decls))
        
        # 2. CRÍTICO: Aplica field_updates ANTES de verificar alcançabilidade
        current_symbolic_fields = fields.copy()
        with suppress_c_stdout_stderr():
            if "field_updates" in state:
                for field_str, expr_str in state["field_updates"].items():
                    h, f = field_str.split('.')
                    if (h, f) in current_symbolic_fields: 
                        updated_expr = parse_smt2_string(expr_str, decls=decls)
                        current_symbolic_fields[(h, f)] = updated_expr
                        print(f"  -> Field update aplicado: {field_str}")
        
        # 3. Constrói as condições do pipeline usando os campos ATUALIZADOS
        path_conditions_with_updates = []
        if path_conditions is not None:
            for cond in path_conditions:
                # Substitui as referências aos campos originais pelos campos atualizados
                cond_str = cond.sexpr()
                # Re-parseia a condição com os campos atualizados
                decls_updated = {var.sexpr(): var for key, var in current_symbolic_fields.items()}
                with suppress_c_stdout_stderr():
                    updated_cond = parse_smt2_string(cond_str, decls=decls_updated)
                path_conditions_with_updates.append(updated_cond)
        
        # 4. Verifica alcançabilidade com as condições atualizadas
        if path_conditions_with_updates:
            reachability_solver = Solver()
            reachability_solver.add(parser_constraints)
            reachability_solver.add(path_conditions_with_updates)
            
            print("  --- Verificando Alcançabilidade (Reachability) ---")
            check_result = reachability_solver.check()
            if check_result == unsat:
                print(f"  -> AVISO: Análise pulada. O pacote deste estado NUNCA alcançará a tabela '{table_name}'.")
                print(f"  -> Razão: As restrições do parser são incompatíveis com as condições do pipeline.")
                output_states.append(state)
                continue
            else:
                print("  -> OK: A tabela é alcançável para este tipo de pacote.")
        
        # 5. Executa a tabela
        final_symbolic_fields = execute_symbolic_table(table_def, current_symbolic_fields, runtime_entries, fsm_data)
        
        # 6. Analisa os resultados
        analysis_solver = Solver()
        analysis_solver.add(parser_constraints)
        if path_conditions_with_updates:
            analysis_solver.add(path_conditions_with_updates)
        
        print("  --- Análise de Resultados (Visão Completa) ---")
        egress_spec = final_symbolic_fields.get(('standard_metadata', 'egress_spec'))
        if egress_spec is not None:
            for port_num in [1, 2, 3, 511]:
                analysis_solver.push()
                analysis_solver.add(egress_spec == port_num)
                if analysis_solver.check() == sat:
                    m = analysis_solver.model()
                    
                    target_host, target_value = get_target_identifier(table_def, current_symbolic_fields, m, ip_to_host_map)
                    
                    if port_num == 511:
                        print(f"  -> Resultado: SIM, pacote para '{target_host}' é DESCARTADO (drop).")
                    else:
                        destination_info = port_to_destination_map.get(port_num, "destino desconhecido")
                        print(f"  -> Resultado: SIM, pacote para '{target_host}' é ENCAMINHADO para a porta {port_num} (em direção a: {destination_info}).")
                analysis_solver.pop()

        new_constraints = list(state['z3_constraints_smt2'])
        if egress_spec is not None:
            no_drop_constraint = (egress_spec != 511)
            new_constraints.append(no_drop_constraint.sexpr())
            print("\n  --- Propagação para Próximo Estágio ---")
            print("  -> Otimização: Adicionada restrição de que o pacote não foi descartado.")
        
        field_updates = state.get("field_updates", {}).copy()
        for (h,f), val_expr in final_symbolic_fields.items():
            if val_expr is not current_symbolic_fields.get((h,f)):
                field_updates[f"{h}.{f}"] = val_expr.sexpr()
        
        new_state = { 
            "description": state["description"] + f" -> {table_name}", 
            "z3_constraints_smt2": new_constraints, 
            "present_headers": state["present_headers"], 
            "history": state["history"] + [table_name], 
            "field_updates": field_updates 
        }
        output_states.append(new_state)

    with open(output_states_file, 'w') as f: json.dump(output_states, f, indent=2)
    print(f"\nAnálise concluída. Estados salvos em '{output_states_file}'.")