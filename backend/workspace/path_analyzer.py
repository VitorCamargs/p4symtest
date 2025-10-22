# z3_path_executor.py
# Versão com impressão de resultados limpa e focada.

import json
import sys
from z3 import *

# --- Funções Auxiliares ---

def load_json(filename):
    """Carrega um arquivo JSON e trata erros comuns."""
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Erro ao carregar '{filename}': {e}"); exit(1)

def get_vars_from_expr(expr):
    """Extrai todas as variáveis de uma expressão Z3."""
    variables = set()
    
    def find_vars(e):
        if is_const(e) and e.decl().kind() == Z3_OP_UNINTERPRETED:
            variables.add(e)
        else:
            for child in e.children():
                find_vars(child)

    if is_expr(expr):
        find_vars(expr)
    return list(variables)

# --- LÓGICA DE ANÁLISE DE FLUXO E TRADUÇÃO PARA Z3 (sem alterações) ---

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

# --- Ponto de Entrada Principal ---
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python3 z3_path_executor.py <fsm.json>")
        exit(1)
        
    fsm_file = sys.argv[1]
    fsm_data = load_json(fsm_file)

    fields = {}
    header_types = {ht['name']: ht for ht in fsm_data['header_types']}
    for h in fsm_data['headers']:
        ht_name = h['header_type']
        if ht_name in header_types:
            for f_name, f_width, _ in header_types[ht_name]['fields']:
                fields[(h['name'], f_name)] = BitVec(f"{h['name']}.{f_name}", f_width)
        fields[(h['name'], '$valid$')] = BitVec(f"{h['name']}.$valid$", 1)

    ingress_pipeline = next((p for p in fsm_data.get("pipelines", []) if p['name'] == 'ingress'), None)
    if not ingress_pipeline:
        print("Erro: Pipeline 'ingress' não encontrado."); exit(1)

    print("--- Análise Simbólica de Alcançabilidade do Pipeline de Ingress ---")
    
    all_tables = ingress_pipeline.get("tables", [])
    if not all_tables:
        print("Nenhuma tabela encontrada."); exit(0)

    start_node = ingress_pipeline.get("init_table")

    for table in all_tables:
        table_name = table["name"]
        print("\n" + "="*60)
        print(f"Tabela: '{table_name}'")
        
        _path_cache.clear()
        path_conditions = find_path_to_table(ingress_pipeline, start_node, table_name, set(), fields)
        
        if path_conditions is None:
            print("  - Status: INALCANÇÁVEL (Nenhum caminho estrutural no grafo)")
            continue

        # Junta todas as condições em uma única expressão para análise
        full_condition = And(path_conditions)
        
        # Usa a representação de string padrão do Z3, que é mais legível
        print(f"  - Condição de Caminho: {full_condition}")
        
        solver = Solver()
        solver.add(full_condition)
        
        if solver.check() == sat:
            print("  - Status: ALCANÇÁVEL")
            m = solver.model()
            if m:
                print("  - Exemplo de Pacote:")
                # Extrai apenas as variáveis que fazem parte da condição de caminho
                involved_vars = get_vars_from_expr(full_condition)
                # Ordena as variáveis para uma impressão consistente
                sorted_vars = sorted(involved_vars, key=lambda v: str(v))
                for var in sorted_vars:
                    # Imprime o valor da variável no modelo encontrado
                    print(f"    - {str(var):<25} = {m[var]}")
        else:
            print("  - Status: INALCANÇÁVEL (Contradição Lógica no Caminho)")