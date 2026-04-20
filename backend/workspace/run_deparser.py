# run_deparser.py (Corrected Z3 boolean check + Optimizer metadata preservation)
import json
import sys
import z3
from z3 import *
import os
from contextlib import contextmanager
from pathlib import Path

# --- Funções Auxiliares ---

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
    """Carrega um arquivo JSON e trata erros comuns."""
    filepath = Path(filename)
    if not filepath.is_file():
        print(f"Erro: Arquivo '{filename}' não foi encontrado ou não é um arquivo.")
        print(f"  -> Caminho absoluto tentado: {filepath.resolve()}")
        print(f"  -> Diretório atual: {Path.cwd()}")
        exit(1)
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"Erro: Arquivo '{filename}' não é um JSON válido: {e}")
        exit(1)
    except Exception as e:
        print(f"Erro inesperado ao carregar '{filename}': {e}")
        exit(1)

def parse_field_update_expr(expr_str, decls, target_var):
    """
    Parses a field-update term by wrapping it into an equality with target_var.
    This avoids AstVector-empty results when expr_str is only a term.
    """
    wrapped = f"(assert (= {target_var.sexpr()} {expr_str}))"
    parsed = parse_smt2_string(wrapped, decls=decls)
    if isinstance(parsed, z3.AstVector):
        if len(parsed) != 1:
            raise ValueError(f"SMT field update produced {len(parsed)} assertions (expected 1)")
        parsed = parsed[0]
    if not isinstance(parsed, z3.BoolRef) or not z3.is_eq(parsed):
        raise ValueError(f"Wrapped SMT update is not an equality: {type(parsed).__name__}")

    left = parsed.arg(0)
    right = parsed.arg(1)
    if z3.eq(left, target_var):
        candidate = right
    elif z3.eq(right, target_var):
        candidate = left
    elif left.sort() == target_var.sort():
        candidate = left
    elif right.sort() == target_var.sort():
        candidate = right
    else:
        raise ValueError("Could not isolate field-update expression with matching sort")
    return candidate


def _is_quiet() -> bool:
    raw = os.environ.get("P4SYMTEST_BENCH_QUIET", "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _vprint(*args, **kwargs):
    if not _is_quiet():
        print(*args, **kwargs)


def _state_field_key(field_str):
    parts = field_str.split('.')
    if len(parts) == 2:
        return tuple(parts)
    if len(parts) == 3:
        return (parts[1], parts[2])
    return None


def _parse_assertion_expr(expr_smt2, decls, parse_cache):
    if expr_smt2 in parse_cache:
        return parse_cache[expr_smt2]
    wrapped = f"(assert {expr_smt2})"
    with suppress_c_stdout_stderr():
        parsed = parse_smt2_string(wrapped, decls=decls)
    if isinstance(parsed, z3.AstVector):
        if len(parsed) != 1:
            raise ValueError(f"SMT assertion produced {len(parsed)} assertions (expected 1)")
        parsed = parsed[0]
    if not isinstance(parsed, z3.BoolRef):
        raise ValueError(f"SMT assertion is not BoolRef: {type(parsed).__name__}")
    parse_cache[expr_smt2] = parsed
    return parsed


def _parse_state_constraints(constraints_smt2, decls, parse_cache):
    parsed_constraints = []
    for expr_smt2 in constraints_smt2:
        parsed_constraints.append(_parse_assertion_expr(expr_smt2, decls, parse_cache))
    return parsed_constraints


def _load_state_field_update_constraints(state_field_updates, fields, decls, field_update_cache):
    constraints = []
    for field_str, expr_str in state_field_updates.items():
        field_key = _state_field_key(field_str)
        if not field_key or field_key not in fields:
            continue
        target_var = fields[field_key]
        cache_key = (field_key[0], field_key[1], expr_str)
        if cache_key in field_update_cache:
            parsed_expr = field_update_cache[cache_key]
        else:
            parsed_expr = parse_field_update_expr(expr_str, decls=decls, target_var=target_var)
            field_update_cache[cache_key] = parsed_expr
        constraints.append(target_var == parsed_expr)
    return constraints

# --- Ponto de Entrada Principal ---
if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Uso: python3 run_deparser.py <fsm.json> <estados_entrada.json> <estados_saida.json>")
        exit(1)

    fsm_file = sys.argv[1]
    input_states_file = sys.argv[2]
    output_file = sys.argv[3]

    _vprint(f"--- Deparser: Carregando FSM de: {fsm_file} ---")
    _vprint(f"--- Deparser: Carregando Estados de: {input_states_file} ---")
    _vprint(f"--- Deparser: Salvando Saída em: {output_file} ---")

    fsm_data = load_json(fsm_file)
    input_states = load_json(input_states_file)
    if not isinstance(input_states, list):
         print(f"Erro: Arquivo de estados de entrada '{input_states_file}' não contém uma lista JSON.")
         exit(1)

    if not fsm_data or not fsm_data.get('deparsers'):
        print(f"Erro: Seção 'deparsers' não encontrada ou vazia no FSM '{fsm_file}'.")
        with open(output_file, 'w', encoding='utf-8') as f: json.dump([], f); exit(0)

    deparser_def = fsm_data['deparsers'][0]
    deparser_order = deparser_def.get('order', [])

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
                         fields[(h_name, f_name)] = BitVec(f"{h_name}.{f_name}", f_width)

        fields[(h_name, '$valid$')] = BitVec(f"{h_name}.$valid$", 1)

    declarations_smt2 = [f"(declare-const {var.sexpr()} (_ BitVec {var.sort().size()}))" for var in fields.values()]

    _vprint(f"--- Analisando Deparser '{deparser_def.get('name', 'deparser')}' ---")
    _vprint(f"Ordem de emissão P4: {', '.join(deparser_order)}")

    analysis_results = []
    decls = {var.sexpr(): var for var in fields.values()}
    parser_constraint_cache = {}
    field_update_cache = {}

    for i, state in enumerate(input_states):
        _vprint(f"\nAnalisando para o Estado de Entrada #{i} ({state.get('description', 'Sem descrição')})")

        state_history = state.get("history", ["Desconhecido"])
        state_constraints_smt2 = state.get("z3_constraints_smt2", [])
        state_field_updates = state.get("field_updates", {})

        solver = Solver()
        is_satisfiable = False
        try:
            parser_constraints = _parse_state_constraints(state_constraints_smt2, decls, parser_constraint_cache)
            if parser_constraints:
                solver.add(*parser_constraints)
            check_result = solver.check()
            is_satisfiable = check_result == sat
            if check_result == unknown:
                 _vprint("  - AVISO: Solver retornou 'unknown'. Assumindo satisfatível.")
                 is_satisfiable = True

        except Exception as e:
            _vprint(f"  - ERRO: Falha SMT: {e}")
            state_result = {
                "input_state": state.get('description', f'Erro SMT no estado {i}'), 
                "input_state_index": i,
                "history": state_history, 
                "full_constraints_smt2": state_constraints_smt2,
                "non_drop_condition_smt": None, 
                "satisfiable": False,
                "error": f"Falha ao processar SMT-LIB: {e}", 
                "emission_status": []
            }
            # Preserva metadados de otimização
            if '_optimizer_hash' in state:
                state_result['_optimizer_hash'] = state['_optimizer_hash']
            if '_original_indices' in state:
                state_result['_original_indices'] = state['_original_indices']
            if '_group_size' in state:
                state_result['_group_size'] = state['_group_size']
            
            analysis_results.append(state_result)
            continue

        # --- Extrai a condição de não-descarte ---
        egress_spec_update_expr_smt = state_field_updates.get("standard_metadata.egress_spec")
        non_drop_condition_smt = None
        if egress_spec_update_expr_smt:
            egress_spec_var = fields.get(('standard_metadata','egress_spec'))
            drop_val_hex = "#xff"
            if egress_spec_var is not None and isinstance(egress_spec_var, z3.BitVecRef):
                 if egress_spec_var.size() == 9:
                      drop_val_hex = "#x1ff"
            non_drop_condition_smt = f"(distinct {egress_spec_update_expr_smt} {drop_val_hex})"
        else:
            non_drop_constraint_explicit_9bit = "(distinct standard_metadata.egress_spec #b111111111)"
            non_drop_constraint_explicit_8bit = "(distinct standard_metadata.egress_spec #xff)"
            for constr in state_constraints_smt2:
                 if non_drop_constraint_explicit_9bit in constr: 
                     non_drop_condition_smt = non_drop_constraint_explicit_9bit
                     break
                 if non_drop_constraint_explicit_8bit in constr: 
                     non_drop_condition_smt = non_drop_constraint_explicit_8bit
                     break

        state_result = {
            "input_state": state.get('description', 'Sem descrição'), 
            "input_state_index": i,
            "history": state_history, 
            "full_constraints_smt2": state_constraints_smt2,
            "non_drop_condition_smt": non_drop_condition_smt, 
            "satisfiable": is_satisfiable,
            "emission_status": []
        }
        
        # Preserva metadados de otimização se existirem
        if '_optimizer_hash' in state:
            state_result['_optimizer_hash'] = state['_optimizer_hash']
        if '_original_indices' in state:
            state_result['_original_indices'] = state['_original_indices']
        if '_group_size' in state:
            state_result['_group_size'] = state['_group_size']

        if not is_satisfiable:
            _vprint("  - AVISO: Estado insatisfatório. Pulando emissão.")
            analysis_results.append(state_result)
            continue

        _vprint("  - Estado satisfatório. Verificando emissão:")

        if state_field_updates:
             try:
                 update_constraints = _load_state_field_update_constraints(
                     state_field_updates,
                     fields,
                     decls,
                     field_update_cache,
                 )
                 if update_constraints:
                     solver.add(*update_constraints)
             except Exception as e:
                 _vprint(f"    - Erro field_update: {e}")

        bv1 = BitVecVal(1, 1)
        bv0 = BitVecVal(0, 1)
        for header_name in deparser_order:
            valid_field = fields.get((header_name, '$valid$'))
            if valid_field is None:
                _vprint(f"    - AVISO: {header_name}.$valid$ não definido.")
                state_result["emission_status"].append({
                    "header": header_name, 
                    "status": "Erro: $valid$ não definido"
                })
                continue

            emission_status = "Desconhecido"
            try: 
                check_can_emit = solver.check(valid_field == bv1)
            except Exception as e: 
                _vprint(f"    - ERRO Z3 {header_name}.$valid$ == 1: {e}")
                check_can_emit = unknown

            if check_can_emit == sat:
                try: 
                    check_can_not_emit = solver.check(valid_field == bv0)
                except Exception as e: 
                    _vprint(f"    - ERRO Z3 {header_name}.$valid$ == 0: {e}")
                    check_can_not_emit = unknown

                if check_can_not_emit == sat: 
                    emission_status = "Condicional"
                    _vprint(f"    - {header_name}: EMITIDO (Condicional)")
                elif check_can_not_emit == unsat: 
                    emission_status = "Sempre"
                    _vprint(f"    - {header_name}: EMITIDO (Sempre)")
                else: 
                    emission_status = "Desconhecido (Erro Z3)"
                    _vprint(f"    - {header_name}: Status Desconhecido (!=1)")

            elif check_can_emit == unsat: 
                emission_status = "Nunca"
                _vprint(f"    - {header_name}: NÃO EMITIDO (Inválido)")
            else: 
                emission_status = "Desconhecido (Erro Z3)"
                _vprint(f"    - {header_name}: Status Desconhecido (==1)")

            state_result["emission_status"].append({
                "header": header_name, 
                "status": emission_status
            })

        analysis_results.append(state_result)

    output_path = Path(output_file)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(analysis_results, f, indent=2)
        _vprint(f"\nAnálise do Deparser concluída. {len(analysis_results)} estados analisados.")
        _vprint(f"Resultados salvos em '{output_path}'.")
    except Exception as e:
        print(f"\nErro ao salvar resultados em '{output_path}': {e}")
        exit(1)
