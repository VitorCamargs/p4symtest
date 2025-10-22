# combined_analyzer.py (versão com correção definitiva)
import json
import sys
from z3 import *

# --- Funções Auxiliares e de Análise (sem alterações, apenas garantindo que estejam completas) ---

def load_json(filename):
    try:
        with open(filename, 'r') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Erro ao carregar '{filename}': {e}"); exit(1)

def build_z3_expression_for_conditional(expr_node, fields):
    if not expr_node: return BoolVal(True)
    if expr_node.get('type') == 'expression':
        return build_z3_expression_for_conditional(expr_node['value'], fields)
    op = expr_node.get('op')
    if not op: return BoolVal(True)
    if op == 'd2b':
        h, f = expr_node['right']['value']
        return fields.get((h, f)) == 1
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
    table_node = next((t for t in pipeline_data['tables'] if t['name'] == start_node_name), None)
    if table_node:
        path = find_path_to_table(pipeline_data, table_node.get('base_default_next'), target_table_name, visited_nodes.copy(), fields)
        if path is not None: _path_cache[path_key] = path; return path
    cond_node = next((c for c in pipeline_data['conditionals'] if c['name'] == start_node_name), None)
    if cond_node:
        condition_expr = build_z3_expression_for_conditional(cond_node['expression'], fields)
        path_from_false = find_path_to_table(pipeline_data, cond_node['false_next'], target_table_name, visited_nodes.copy(), fields)
        if path_from_false is not None:
            result = [Not(condition_expr)] + path_from_false; _path_cache[path_key] = result; return result
        path_from_true = find_path_to_table(pipeline_data, cond_node['true_next'], target_table_name, visited_nodes.copy(), fields)
        if path_from_true is not None:
            result = [condition_expr] + path_from_true; _path_cache[path_key] = result; return result
    _path_cache[path_key] = None
    return None

# --- Ponto de Entrada Principal (Lógica Reestruturada) ---
if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python3 combined_analyzer.py <fsm.json> <parser_states.json>")
        exit(1)
    fsm_file, parser_states_file = sys.argv[1], sys.argv[2]

    fsm_data = load_json(fsm_file)
    parser_states = load_json(parser_states_file)

    # 1. Cria as variáveis simbólicas Z3 (APENAS para construir as expressões)
    fields = {}
    header_types = {ht['name']: ht for ht in fsm_data['header_types']}
    for h in fsm_data['headers']:
        ht_name = h['header_type']
        if ht_name in header_types:
            for f_name, f_width, _ in header_types[ht_name]['fields']:
                fields[(h['name'], f_name)] = BitVec(f"{h['name']}.{f_name}", f_width)
        fields[(h['name'], '$valid$')] = BitVec(f"{h['name']}.$valid$", 1)
    
    # 2. Gera as strings de declaração SMT-LIB para todas as variáveis
    declarations_smt2 = []
    for var in fields.values():
        declarations_smt2.append(f"(declare-const {var.sexpr()} (_ BitVec {var.sort().size()}))")

    ingress_pipeline = next((p for p in fsm_data.get("pipelines", []) if p['name'] == 'ingress'), None)
    if not ingress_pipeline:
        print("Erro: Pipeline 'ingress' não encontrado."); exit(1)

    print("--- Análise Combinada de Alcançabilidade (Parser vs. Pipeline) ---")
    
    all_tables = ingress_pipeline.get("tables", [])
    start_node = ingress_pipeline.get("init_table")

    # 3. Loop externo: para cada tabela no pipeline
    for table in all_tables:
        table_name = table["name"]
        print("\n" + "#"*70)
        print(f"##  Analisando Alcançabilidade para a Tabela: '{table_name}'")
        print("#"*70)
        
        _path_cache.clear()
        path_conditions_z3 = find_path_to_table(ingress_pipeline, start_node, table_name, set(), fields)
        
        if path_conditions_z3 is None:
            print(f"\n  AVISO: A tabela '{table_name}' é estruturalmente inalcançável no pipeline.")
            continue
        
        # Converte as condições de caminho para strings SMT-LIB
        path_conditions_smt2 = [f"(assert {cond.sexpr()})" for cond in path_conditions_z3]

        print("\n  Condições do Pipeline para alcançar esta tabela:")
        for cond in path_conditions_z3: print(f"    - {cond}")

        print("\n  Verificando compatibilidade com cada estado do parser:")
        for i, state in enumerate(parser_states):
            # Formata as restrições do parser para SMT-LIB
            parser_constraints_smt2 = [f"(assert {s})" for s in state['z3_constraints_smt2']]

            # Monta o script SMT-LIB completo
            full_script = "\n".join(declarations_smt2) + \
                          "\n".join(parser_constraints_smt2) + \
                          "\n".join(path_conditions_smt2)
            
            # Cria um solver novo e limpo para cada teste
            solver = Solver()
            solver.from_string(full_script)
            
            print("\n" + "="*50)
            print(f"Testando '{state['description']}'")
            
            if solver.check() == sat:
                print(f"    -> RESULTADO: Alcançável")
            else:
                print(f"    -> RESULTADO: Inalcançável (CONTRADIÇÃO ENCONTRADA)")