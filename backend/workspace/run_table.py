# run_table.py (Versão Limpa e Corrigida)
import json
import sys
import z3
from z3 import BoolVal, BitVecVal, BitVec, And, Or, Not, If, Solver, sat, unsat, is_false, Extract, ZeroExt, BitVecSort
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

def p4_runtime_value_to_int(value_str, bitwidth):
    """Converte valores de runtime P4 (IPs, MACs, hex) para inteiros."""
    if isinstance(value_str, int):
        return value_str
    
    value_str = str(value_str).strip()
    
    try:
        if ":" in value_str and bitwidth == 48: # Endereco MAC
            return int(value_str.replace(":", ""), 16)
        if "." in value_str and bitwidth == 32: # Endereco IPv4
            parts = value_str.split('.')
            return (int(parts[0]) << 24) | (int(parts[1]) << 16) | (int(parts[2]) << 8) | int(parts[3])
        
        return int(value_str, 0) # Base 0 handles int, hex, bin
    except Exception as e:
        # print(f"Warning: Could not convert P4 value '{value_str}' to int: {e}")
        return 0 # Return 0 on failure

# --- LÓGICA DE ANÁLISE DE FLUXO DE CONTROLE ---
def build_z3_expression_for_conditional(expr_node, fields):
    if not expr_node: return BoolVal(True)
    if expr_node.get('type') == 'expression':
        return build_z3_expression_for_conditional(expr_node['value'], fields)
    op = expr_node.get('op')
    if not op: return BoolVal(True)
    if op == 'd2b':
        field_val = expr_node['right']['value']
        key = tuple(field_val) if len(field_val) == 2 else (field_val[1], field_val[2])
        field_var = fields.get(key)
        return field_var == 1 if field_var is not None else BoolVal(False)
    elif op == 'not':
        return Not(build_z3_expression_for_conditional(expr_node['right'], fields))
    elif op == 'and':
        left = build_z3_expression_for_conditional(expr_node['left'], fields)
        right = build_z3_expression_for_conditional(expr_node['right'], fields)
        return And(left, right)
    return BoolVal(True)

_path_cache = {}
def find_paths_to_table(pipeline_data, start_node_name, target_table_name, visited_nodes, fields):
    path_key = (start_node_name, target_table_name)
    if path_key in _path_cache: return _path_cache[path_key]
    if start_node_name == target_table_name: return [[]]
    if start_node_name is None or start_node_name in visited_nodes: return []
    visited_nodes.add(start_node_name)

    all_paths = []
    
    table_node = next((t for t in pipeline_data.get('tables', []) if t['name'] == start_node_name), None)
    if table_node:
        next_node = table_node.get('base_default_next')
        if next_node:
            paths = find_paths_to_table(pipeline_data, next_node, target_table_name, visited_nodes.copy(), fields)
            all_paths.extend(paths)
            
        next_tables = table_node.get('next_tables', {})
        for act_name, next_node_act in next_tables.items():
            paths = find_paths_to_table(pipeline_data, next_node_act, target_table_name, visited_nodes.copy(), fields)
            all_paths.extend(paths)
            
    cond_node = next((c for c in pipeline_data.get('conditionals', []) if c['name'] == start_node_name), None)
    if cond_node:
        condition_expr = build_z3_expression_for_conditional(cond_node.get('expression'), fields)
        
        paths_from_false = find_paths_to_table(pipeline_data, cond_node.get('false_next'), target_table_name, visited_nodes.copy(), fields)
        for p in paths_from_false:
            all_paths.append([Not(condition_expr)] + p)
            
        paths_from_true = find_paths_to_table(pipeline_data, cond_node.get('true_next'), target_table_name, visited_nodes.copy(), fields)
        for p in paths_from_true:
            all_paths.append([condition_expr] + p)
            
    _path_cache[path_key] = all_paths
    return all_paths

# --- LÓGICA DE EXECUÇÃO SIMBÓLICA ---
def build_z3_expression(expr_node, current_fields):
    """Builds Z3 expression, returns int for constants, Z3 expr otherwise."""
    if not expr_node: return None
    node_type = expr_node.get('type')

    if node_type == 'hexstr': 
        try: return int(expr_node['value'], 16)
        except ValueError: return None
    if node_type == 'field': 
        field_val = expr_node['value']
        key = tuple(field_val) if len(field_val) == 2 else (field_val[1], field_val[2])
        return current_fields.get(key)
    if node_type == 'expression': 
        return build_z3_expression(expr_node.get('value'), current_fields)
    
    op = expr_node.get('op')
    if op:
        left_val = build_z3_expression(expr_node.get('left'), current_fields)
        right_val = build_z3_expression(expr_node.get('right'), current_fields)

        # Ensure Z3 objects if possible
        if isinstance(left_val, int) and isinstance(right_val, z3.BitVecRef):
            left_val = BitVecVal(left_val, right_val.size())
        if isinstance(right_val, int) and isinstance(left_val, z3.BitVecRef):
            right_val = BitVecVal(right_val, left_val.size())

        is_left_z3 = isinstance(left_val, z3.ExprRef)
        is_right_z3 = isinstance(right_val, z3.ExprRef)
        
        try:
            if op == '+': 
                if is_left_z3 and is_right_z3: return left_val + right_val
            elif op == '&': 
                if is_left_z3 and is_right_z3: return left_val & right_val
            elif op == '-': 
                if is_left_z3 and is_right_z3: return left_val - right_val
        except z3.Z3Exception as e:
            print(f"Error in build_z3_expression op '{op}': {e}")
            return None
            
    return None

def apply_symbolic_action(action_name, action_params, current_fields, fsm_data):
    action_def = next((a for a in fsm_data['actions'] if a['name'] == action_name), None)
    if not action_def: return {}
    modified_fields = {}
    for prim in action_def.get('primitives', []):
        op = prim.get('op')
        params = prim.get('parameters', [])

        if op == 'mark_to_drop':
            # Ensure egress_spec exists and has correct size (9 bits)
            dest_key = ('standard_metadata', 'egress_spec')
            dest_var = current_fields.get(dest_key)
            dest_bitwidth = dest_var.size() if dest_var is not None else 9
            if dest_bitwidth != 9:
                print(f"Warning: egress_spec expected size 9, found {dest_bitwidth}. Adjusting.")
                dest_bitwidth = 9
            modified_fields[dest_key] = BitVecVal(511, dest_bitwidth)
            
        elif op == 'assign' and len(params) == 2:
            dest = params[0]
            source = params[1]
            if dest['type'] != 'field': continue

            dest_val = dest['value']
            dest_key = tuple(dest_val) if len(dest_val) == 2 else (dest_val[1], dest_val[2])
            dest_var = current_fields.get(dest_key)
            # --- CORRECAO: Get bitwidth reliably, default to 32 if unknown ---
            dest_bitwidth = dest_var.size() if dest_var is not None else 32 
            
            source_val = None
            source_bitwidth = dest_bitwidth # Assume same size unless specified otherwise
            
            if source['type'] == 'runtime_data':
                param_def = action_def['runtime_data'][source['value']]
                param_name = param_def['name']
                param_bitwidth = param_def['bitwidth']
                concrete_val = action_params.get(param_name)
                if concrete_val is not None:
                    try:
                        int_val = p4_runtime_value_to_int(concrete_val, param_bitwidth)
                        source_val = BitVecVal(int_val, param_bitwidth)
                        source_bitwidth = param_bitwidth
                    except Exception as e:
                        print(f"Error creating BitVecVal for runtime param {param_name}={concrete_val}: {e}")

            elif source['type'] == 'field':
                field_val = source['value']
                key = tuple(field_val) if len(field_val) == 2 else (field_val[1], field_val[2])
                source_val = current_fields.get(key)
                if source_val is not None: source_bitwidth = source_val.size()

            elif source['type'] == 'expression':
                source_val = build_z3_expression(source, current_fields)
                if isinstance(source_val, int): # If build_z3 returns int, convert it
                   source_val = BitVecVal(source_val, dest_bitwidth) 
                if source_val is not None: source_bitwidth = source_val.size()

            elif source['type'] == 'hexstr':
                try:
                    int_val = int(source['value'], 16)
                    source_val = BitVecVal(int_val, dest_bitwidth) # Use dest size
                    source_bitwidth = dest_bitwidth
                except: pass
            
            # Ensure source_val is a Z3 expression before proceeding
            if isinstance(source_val, int):
                source_val = BitVecVal(source_val, dest_bitwidth)
            
            # Apply assignment and adjust size if necessary
            if source_val is not None and isinstance(source_val, z3.BitVecRef):
                # --- CORRECAO: Compare source_bitwidth and dest_bitwidth ---
                if dest_bitwidth != source_bitwidth:
                    # print(f"Warning: Adjusting size in assign {dest_key} ({dest_bitwidth}) = ... ({source_bitwidth})")
                    if dest_bitwidth > source_bitwidth:
                        source_val = ZeroExt(dest_bitwidth - source_bitwidth, source_val)
                    else:
                        source_val = Extract(dest_bitwidth - 1, 0, source_val)
                modified_fields[dest_key] = source_val
            # else: print(f"Warning: Source value for assign to {dest_key} is None or not Z3 expr.")

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
    action_names = set([e.get('action', 'NoAction') for e in entries] + [default_action_name])
    for action_name in action_names:
        action_def = next((a for a in fsm_data['actions'] if a['name'] == action_name), {})
        for prim in action_def.get('primitives', []):
            op = prim.get('op')
            params = prim.get('parameters', [])
            if op == 'mark_to_drop':
                modifiable_fields.add(('standard_metadata', 'egress_spec'))
            elif op == 'assign' and len(params) > 0 and params[0]['type'] == 'field':
                dest_val = params[0]['value']
                key = tuple(dest_val) if len(dest_val) == 2 else (dest_val[1], dest_val[2])
                modifiable_fields.add(key)

    # Executa simbolicamente para cada campo modificável
    for field_key in modifiable_fields:
        default_mods = apply_symbolic_action(default_action_name, {}, current_fields, fsm_data)
        final_expr = default_mods.get(field_key, current_fields.get(field_key))
        
        for entry in reversed(entries):
            match_cond = BoolVal(True)
            for field_str, match_val_info in entry.get('match', {}).items():
                parts = field_str.split('.')
                if len(parts) == 2: field_key_match = tuple(parts)
                elif len(parts) == 3: field_key_match = (parts[1], parts[2])
                else: match_cond = BoolVal(False); break
                
                field_var = current_fields.get(field_key_match)
                if field_var is None: match_cond = BoolVal(False); break
                
                match_type = next((k['match_type'] for k in table_def.get('key',[]) if k.get('name') == field_str or k.get('target') == list(field_key_match)), 'exact')

                entry_cond = None
                try:
                    if match_type == 'exact':
                        val = p4_runtime_value_to_int(match_val_info, field_var.size())
                        entry_cond = (field_var == BitVecVal(val, field_var.size()))
                    elif match_type == 'lpm':
                         val_str, prefix = match_val_info
                         val = p4_runtime_value_to_int(val_str, field_var.size())
                         bitwidth = field_var.size()
                         mask = ((1 << bitwidth) - 1) << (bitwidth - prefix) # Create mask
                         entry_cond = (field_var & mask) == (val & mask)
                    elif match_type == 'ternary':
                         val_str, mask_str = match_val_info
                         val = p4_runtime_value_to_int(val_str, field_var.size())
                         mask = p4_runtime_value_to_int(mask_str, field_var.size())
                         entry_cond = (field_var & mask) == (val & mask)
                    # Add range etc. if needed
                    else:
                        print(f"Warning: Unsupported match type '{match_type}' for field {field_str}")
                        match_cond = BoolVal(False); break
                except Exception as e:
                     print(f"Error creating Z3 match condition for {field_str} ({match_type}): {e}")
                     match_cond = BoolVal(False); break

                if entry_cond is not None:
                    match_cond = And(match_cond, entry_cond)
                elif not is_false(match_cond): # If no condition created, but wasn't False before
                     match_cond = BoolVal(False); break

            if is_false(match_cond): continue
            
            entry_mods = apply_symbolic_action(entry.get('action', 'NoAction'), entry.get('action_params', {}), current_fields, fsm_data)
            value_if_match = entry_mods.get(field_key, current_fields.get(field_key))

            # --- CORRECAO: Ensure both sides of If are Z3 expressions with same sort ---
            target_sort = current_fields.get(field_key).sort() if field_key in current_fields else None
            
            if not isinstance(value_if_match, z3.ExprRef):
                 int_val = p4_runtime_value_to_int(value_if_match, target_sort.size() if target_sort else 32)
                 value_if_match = BitVecVal(int_val, target_sort if target_sort else BitVecSort(32))

            if not isinstance(final_expr, z3.ExprRef):
                 int_val = p4_runtime_value_to_int(final_expr, target_sort.size() if target_sort else 32)
                 final_expr = BitVecVal(int_val, target_sort if target_sort else BitVecSort(32))

            # Check sorts before calling If
            if value_if_match.sort() == final_expr.sort():
                 final_expr = If(match_cond, value_if_match, final_expr)
            else:
                 print(f"Error: Sort mismatch in If for field {field_key}. Then: {value_if_match.sort()}, Else: {final_expr.sort()}")
                 # Handle error - maybe fall back to default? For now, keep previous final_expr
                 pass 
            # --- FIM DA CORRECAO ---

        if final_expr is not None:
             try:
                 next_fields[field_key] = simplify(final_expr)
             except z3.Z3Exception:
                 next_fields[field_key] = final_expr 
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

    fsm_data = load_json(fsm_file)
    topology_data = load_json(topology_file)
    runtime_entries_all = load_json(config_file)
    initial_states = load_json(input_states_file)
    runtime_entries = runtime_entries_all.get(switch_id, {})
    
    # Cria campos Z3
    fields = {}
    header_types = {ht['name']: ht for ht in fsm_data.get('header_types', [])}
    
    for h in fsm_data.get('headers', []):
        ht_name = h.get('header_type')
        h_name = h.get('name')
        if not h_name: continue

        if ht_name and ht_name in header_types:
            for f_info in header_types[ht_name].get('fields', []):
                if len(f_info) >= 2:
                     f_name, f_width = f_info[0], f_info[1]
                     if isinstance(f_name, str) and isinstance(f_width, int) and f_width > 0:
                         field_full_name = f"{h_name}.{f_name}"
                         fields[(h_name, f_name)] = BitVec(field_full_name, f_width)
        
        if h_name != 'scalars':
            valid_field_name = f"{h_name}.$valid$"
            fields[(h_name, '$valid$')] = BitVec(valid_field_name, 1)
    
    # Constrói mapa de topologia ... (codigo omitido para brevidade, sem alteracoes)
    ip_to_host_map = {h_info['ip']: h_id for h_id, h_info in topology_data.get('hosts', {}).items()}
    port_to_destination_map = {}
    current_switch_info = topology_data.get('switches', {}).get(switch_id, {})
    for h_id, h_info in topology_data.get('hosts', {}).items():
        if h_info.get('conectado_a', '').startswith(switch_id):
            port_name = h_info['conectado_a']; port_num = current_switch_info.get('portas', {}).get(port_name)
            if port_num: port_to_destination_map[port_num] = f"host {h_id} (direta)"
    for link in topology_data.get('links', []):
        if link.get('from', '').startswith(switch_id):
            port_name = link['from']; dest_switch = link.get('to', 'N/A').split('-')[0]
            port_num = current_switch_info.get('portas', {}).get(port_name)
            if port_num: port_to_destination_map[port_num] = f"switch {dest_switch}"
        elif link.get('to', '').startswith(switch_id):
            port_name = link['to']; dest_switch = link.get('from', 'N/A').split('-')[0]
            port_num = current_switch_info.get('portas', {}).get(port_name)
            if port_num: port_to_destination_map[port_num] = f"switch {dest_switch}"

    ingress_pipeline = next((p for p in fsm_data.get('pipelines',[]) if p.get('name') == 'ingress'), None)
    if not ingress_pipeline: print("Erro: Pipeline 'ingress' não encontrado."); exit(1)

    print(f"Calculando caminho do pipeline até a tabela '{table_name}'...")
    _path_cache.clear()
    all_path_conditions = find_paths_to_table(ingress_pipeline, ingress_pipeline.get('init_table'), table_name, set(), fields)
    if not all_path_conditions: print(f"AVISO: A tabela '{table_name}' parece ser estruturalmente inalcançável.")

    print(f"--- Carregados {len(initial_states)} estados de '{input_states_file}' ---")
    print(f"--- Executando análise modular da tabela '{table_name}' para o SWITCH '{switch_id}' ---")
    
    output_states = []
    for i, state in enumerate(initial_states):
        print("\n" + "="*50)
        print(f"Analisando para o Estado de Entrada #{i} ({state.get('description', 'Sem desc')})")

        parser_constraints_smt2 = state.get('z3_constraints_smt2', [])
        
        declarations_smt2 = [f"(declare-const {var.sexpr()} (_ BitVec {var.sort().size()}))" for var in fields.values()]
        
        # Determine logical reachability across all structural paths
        path_reachable = False
        valid_path_conditions = None
        
        if not all_path_conditions:
            print("  -> AVISO: Análise pulada. Pacote NUNCA alcançará a tabela (Sem Caminho Estrutural).")
            output_states.append(state); continue

        for p_conds in all_path_conditions:
            parser_assertions = [f"(assert {s})" for s in parser_constraints_smt2]
            path_assertions = [f"(assert {cond.sexpr()})" for cond in p_conds] if p_conds else []
            full_script = "\n".join(declarations_smt2 + parser_assertions + path_assertions)
            reachability_solver = Solver()
            try: reachability_solver.from_string(full_script)
            except Exception as e: print(f"  -> ERRO Z3: Falha ao carregar SMT: {e}"); continue
            
            if reachability_solver.check() == sat:
                path_reachable = True
                valid_path_conditions = p_conds
                break

        print("  --- Verificando Alcançabilidade (Reachability) ---")
        if not path_reachable:
            print(f"  -> AVISO: Análise pulada. Pacote NUNCA alcançará a tabela '{table_name}'.")
            output_states.append(state); continue
        else: print("  -> OK: A tabela é alcançável via um caminho válido.")
        
        analysis_solver = Solver()
        main_script = "\n".join(declarations_smt2 + parser_assertions)
        try: analysis_solver.from_string(main_script)
        except Exception as e: print(f"  -> ERRO Z3: Falha ao carregar SMT principal: {e}. Pulando."); continue
        
        current_symbolic_fields = fields.copy()
        if "field_updates" in state:
            decls = {var.sexpr(): var for key, var in fields.items()}
            for field_str, expr_str in state["field_updates"].items():
                parts = field_str.split('.'); field_key = tuple(parts) if len(parts)==2 else (parts[1],parts[2]) if len(parts)==3 else None
                if field_key and field_key in current_symbolic_fields:
                    try: 
                        with suppress_c_stdout_stderr(): current_symbolic_fields[field_key] = parse_smt2_string(expr_str, decls=decls)
                    except Exception as e: print(f"Erro ao parsear SMT para {field_str}: {e}")
        
        target_table_def = next((t for t in ingress_pipeline.get('tables', []) if t['name'] == table_name), None)
        if not target_table_def: print(f"Erro: Definição da tabela '{table_name}' não encontrada."); continue

        final_symbolic_fields = execute_symbolic_table(target_table_def, current_symbolic_fields, runtime_entries, fsm_data)
        
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
                            try: target_ip_str = int_to_ip(dst_addr_val.as_long())
                            except: pass 
                    
                    target_host = ip_to_host_map.get(target_ip_str, f"IP desconhecido ({target_ip_str})")
                    if port_num == 511: print(f"  -> Resultado: SIM, pacote para '{target_host}' é DESCARTADO (drop).")
                    else:
                        destination_info = port_to_destination_map.get(port_num, "desconhecido")
                        print(f"  -> Resultado: SIM, pacote para '{target_host}' é ENCAMINHADO para a porta {port_num} (-> {destination_info}).")
                analysis_solver.pop()

        new_constraints = list(state.get('z3_constraints_smt2', []))
        if egress_spec is not None:
            no_drop_constraint = (egress_spec != 511)
            analysis_solver.push(); analysis_solver.add(no_drop_constraint)
            if analysis_solver.check() == sat:
                new_constraints.append(no_drop_constraint.sexpr())
                print("\n  --- Propagação para Próximo Estágio ---"); print("  -> Otimização: Adicionada restrição de não descarte.")
            else:
                print("\n  --- Propagação para Próximo Estágio ---"); print("  -> AVISO: Todos os pacotes deste estado são descartados."); continue 
            analysis_solver.pop()
        
        field_updates = state.get("field_updates", {}).copy()
        for field_key, val_expr in final_symbolic_fields.items():
            original_val = current_symbolic_fields.get(field_key)
            if val_expr is not None and original_val is not None:
                 try:
                     final_smt = simplify(val_expr).sexpr(); original_smt = simplify(original_val).sexpr()
                     if final_smt != original_smt: field_updates[f"{field_key[0]}.{field_key[1]}"] = final_smt
                 except z3.Z3Exception: 
                     if val_expr.sexpr() != original_val.sexpr(): field_updates[f"{field_key[0]}.{field_key[1]}"] = val_expr.sexpr()
            elif val_expr is not None: field_updates[f"{field_key[0]}.{field_key[1]}"] = val_expr.sexpr()

        new_state = { 
            "description": state.get("description", "???") + f" -> {table_name}", 
            "z3_constraints_smt2": new_constraints, 
            "present_headers": state.get("present_headers", []), 
            "history": state.get("history", []) + [table_name], 
            "field_updates": field_updates 
        }
        output_states.append(new_state)

    with open(output_states_file, 'w') as f: json.dump(output_states, f, indent=2)
    print(f"\nAnálise concluída. {len(output_states)} estados salvos em '{output_states_file}'.")