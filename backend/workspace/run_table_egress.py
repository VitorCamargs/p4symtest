# run_table_egress.py (Corrected AstVector error and added comparisons)
import json
import sys
import z3
from z3 import *
import os
from contextlib import contextmanager
from pathlib import Path
import hashlib # Import hashlib if not already imported

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
    """Carrega um arquivo JSON e trata erros."""
    filepath = Path(filename)
    if not filepath.is_file():
        print(f"Erro: Arquivo '{filename}' não foi encontrado ou não é um arquivo.")
        print(f"  -> Caminho absoluto tentado: {filepath.resolve()}")
        print(f"  -> Diretório atual: {Path.cwd()}")
        exit(1)
    try:
        with open(filepath, 'r', encoding='utf-8') as f: return json.load(f)
    except json.JSONDecodeError as e: print(f"Erro: Arquivo '{filename}' JSON inválido: {e}"); exit(1)
    except Exception as e: print(f"Erro ao carregar '{filename}': {e}"); exit(1)

def p4_runtime_value_to_int(value_str, bitwidth):
    """Converte valores de runtime P4 (IPs, MACs, hex) para inteiros."""
    if isinstance(value_str, int): return value_str
    value_str = str(value_str).strip()
    try:
        if ":" in value_str and bitwidth == 48: return int(value_str.replace(":", ""), 16)
        if "." in value_str and bitwidth == 32:
            parts = value_str.split('.'); return (int(parts[0]) << 24) | (int(parts[1]) << 16) | (int(parts[2]) << 8) | int(parts[3])
        return int(value_str, 0) # Base 0 handles int, hex, bin
    except Exception: return 0 # Return 0 on failure

def sanitize_symbol_name(name):
    return ''.join(ch if ch.isalnum() else '_' for ch in str(name))

def is_symbolic_token(value):
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {'', 'symbolic', 'sym', '__symbolic__', '*', 'auto', 'default'}
    return False

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

# --- LÓGICA DE ANÁLISE DE FLUXO DE CONTROLE ---
_path_cache = {}
def _field_key_from_node_value(field_val):
    if not isinstance(field_val, (list, tuple)):
        return None
    if len(field_val) == 2:
        return tuple(field_val)
    if len(field_val) >= 3:
        return (field_val[-2], field_val[-1])
    return None

def _to_boolref(value):
    if isinstance(value, z3.BoolRef):
        return value
    if isinstance(value, bool):
        return BoolVal(value)
    if isinstance(value, int):
        return BoolVal(value != 0)
    if isinstance(value, z3.BitVecRef):
        if value.size() == 1:
            return value == BitVecVal(1, 1)
        return value != BitVecVal(0, value.size())
    return BoolVal(True)

def _coerce_for_comparison(left, right):
    if isinstance(left, bool):
        left = BoolVal(left)
    if isinstance(right, bool):
        right = BoolVal(right)

    if isinstance(left, z3.BoolRef) or isinstance(right, z3.BoolRef):
        return _to_boolref(left), _to_boolref(right), 'bool'

    if isinstance(left, z3.BitVecRef) and isinstance(right, int):
        right = BitVecVal(right, left.size())
    if isinstance(right, z3.BitVecRef) and isinstance(left, int):
        left = BitVecVal(left, right.size())

    if isinstance(left, int) and isinstance(right, int):
        return left, right, 'int'

    if isinstance(left, z3.BitVecRef) and isinstance(right, z3.BitVecRef):
        left_size = left.size()
        right_size = right.size()
        if left_size != right_size:
            if left_size > right_size:
                right = ZeroExt(left_size - right_size, right)
            else:
                left = ZeroExt(right_size - left_size, left)
        return left, right, 'bv'

    return left, right, 'unknown'

def _compare_terms(op, left, right):
    left, right, kind = _coerce_for_comparison(left, right)

    if kind == 'bool':
        if op == '==':
            return left == right
        if op == '!=':
            return left != right
        return BoolVal(False)

    if kind == 'int':
        if op == '==':
            return BoolVal(left == right)
        if op == '!=':
            return BoolVal(left != right)
        if op == '>':
            return BoolVal(left > right)
        if op == '<':
            return BoolVal(left < right)
        if op == '>=':
            return BoolVal(left >= right)
        if op == '<=':
            return BoolVal(left <= right)
        return BoolVal(False)

    if kind == 'bv':
        if op == '==':
            return left == right
        if op == '!=':
            return left != right
        if op == '>':
            return UGT(left, right)
        if op == '<':
            return ULT(left, right)
        if op == '>=':
            return UGE(left, right)
        if op == '<=':
            return ULE(left, right)
        return BoolVal(False)

    if op == '==':
        return left == right if isinstance(left, z3.ExprRef) and isinstance(right, z3.ExprRef) else BoolVal(False)
    if op == '!=':
        return left != right if isinstance(left, z3.ExprRef) and isinstance(right, z3.ExprRef) else BoolVal(False)
    return BoolVal(True)

def _build_conditional_term(expr_node, fields):
    if not expr_node:
        return BoolVal(True)

    node_type = expr_node.get('type')
    if node_type == 'expression':
        return _build_conditional_term(expr_node.get('value'), fields)
    if node_type == 'field':
        key = _field_key_from_node_value(expr_node.get('value'))
        return fields.get(key)
    if node_type == 'hexstr':
        try:
            return int(expr_node.get('value', '0'), 16)
        except Exception:
            return 0
    if node_type in ('bool', 'boolean'):
        value = expr_node.get('value')
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() == 'true'
        return bool(value)

    op = expr_node.get('op')
    if not op:
        return None

    if op == 'd2b':
        right_term = _build_conditional_term(expr_node.get('right'), fields)
        return _to_boolref(right_term)
    if op == 'not':
        right_term = _build_conditional_term(expr_node.get('right'), fields)
        return Not(_to_boolref(right_term))
    if op == 'and':
        left_term = _build_conditional_term(expr_node.get('left'), fields)
        right_term = _build_conditional_term(expr_node.get('right'), fields)
        return And(_to_boolref(left_term), _to_boolref(right_term))
    if op == 'or':
        left_term = _build_conditional_term(expr_node.get('left'), fields)
        right_term = _build_conditional_term(expr_node.get('right'), fields)
        return Or(_to_boolref(left_term), _to_boolref(right_term))
    if op in ('==', '!=', '>', '<', '>=', '<='):
        left_term = _build_conditional_term(expr_node.get('left'), fields)
        right_term = _build_conditional_term(expr_node.get('right'), fields)
        return _compare_terms(op, left_term, right_term)

    return BoolVal(True)

def build_z3_expression_for_conditional(expr_node, fields):
    """Constrói uma expressão booleana Z3 para um condicional do FSM."""
    return _to_boolref(_build_conditional_term(expr_node, fields))

def find_path_to_table(pipeline_data, start_node_name, target_table_name, visited_nodes, fields):
    """Encontra um caminho e suas condições Z3."""
    path_key = (start_node_name, target_table_name)
    if path_key in _path_cache: return _path_cache[path_key]
    if start_node_name == target_table_name: return []
    if start_node_name is None or start_node_name in visited_nodes: return None
    visited_nodes.add(start_node_name)
    table_node = next((t for t in pipeline_data.get('tables', []) if t.get('name') == start_node_name), None)
    if table_node:
        path = find_path_to_table(pipeline_data, table_node.get('base_default_next'), target_table_name, visited_nodes.copy(), fields)
        if path is not None: _path_cache[path_key] = path; return path
    cond_node = next((c for c in pipeline_data.get('conditionals', []) if c.get('name') == start_node_name), None)
    if cond_node:
        cond_expr = build_z3_expression_for_conditional(cond_node.get('expression'), fields)
        path_false = find_path_to_table(pipeline_data, cond_node.get('false_next'), target_table_name, visited_nodes.copy(), fields)
        if path_false is not None: result = [Not(cond_expr)] + path_false; _path_cache[path_key] = result; return result
        path_true = find_path_to_table(pipeline_data, cond_node.get('true_next'), target_table_name, visited_nodes.copy(), fields)
        if path_true is not None: result = [cond_expr] + path_true; _path_cache[path_key] = result; return result
    _path_cache[path_key] = None; return None

# --- LÓGICA DE EXECUÇÃO SIMBÓLICA ---
def build_z3_expression(expr_node, current_fields, default_bw=32):
    """Constrói expressão Z3, retorna int para constantes, Z3 expr outros."""
    if not expr_node: return None
    node_type = expr_node.get('type')

    if node_type == 'hexstr':
        try: return int(expr_node['value'], 16) # Return as int
        except ValueError: return None
    if node_type == 'field':
        field_val = expr_node['value'];
        # Lida com chave de 2 ou 3 partes
        key = tuple(field_val) if len(field_val)==2 else (field_val[1],field_val[2]) if len(field_val)==3 else None
        if key: return current_fields.get(key) # Return Z3 var or None
        else: return None
    if node_type == 'expression':
        return build_z3_expression(expr_node.get('value'), current_fields, default_bw) # Pass default_bw

    op = expr_node.get('op')
    if op:
        left_val = build_z3_expression(expr_node.get('left'), current_fields, default_bw)
        right_val = build_z3_expression(expr_node.get('right'), current_fields, default_bw)

        # --- Enhanced Type/Size Handling ---
        target_bw = default_bw
        left_bw = left_val.size() if isinstance(left_val, z3.BitVecRef) else None
        right_bw = right_val.size() if isinstance(right_val, z3.BitVecRef) else None

        if left_bw is not None: target_bw = left_bw
        elif right_bw is not None: target_bw = right_bw

        # Convert ints to Z3 BitVecVal if needed
        if op in ['+', '&', '-', '==', '!=', '>', '<', '>=', '<='] or (op in ['and', 'not', 'd2b'] and not isinstance(left_val, bool) and not isinstance(right_val, bool)):
            if isinstance(left_val, int):
                try: left_val = BitVecVal(left_val, target_bw)
                except Exception as e: print(f"Warn: Z3 Conv Error Left ({left_val}, bw={target_bw}): {e}"); return None
            if isinstance(right_val, int):
                try: right_val = BitVecVal(right_val, target_bw)
                except Exception as e: print(f"Warn: Z3 Conv Error Right ({right_val}, bw={target_bw}): {e}"); return None

        is_left_z3 = isinstance(left_val, z3.ExprRef)
        is_right_z3 = isinstance(right_val, z3.ExprRef)

        # --- Perform Operation ---
        try:
            # Bitwise/Arithmetic Ops (Require Z3 BitVecRef)
            if op in ['+', '&', '-']:
                 if not is_left_z3 or not is_right_z3 or not is_bv(left_val) or not is_bv(right_val): return None
                 l_sz, r_sz = left_val.size(), right_val.size()
                 if l_sz != r_sz:
                     if l_sz > r_sz: right_val = ZeroExt(l_sz - r_sz, right_val)
                     else: left_val = ZeroExt(r_sz - l_sz, left_val)
                 if op == '+': return left_val + right_val
                 if op == '&': return left_val & right_val
                 if op == '-': return left_val - right_val

            # Boolean Ops (Return BoolRef)
            elif op == 'd2b':
                if isinstance(right_val, z3.BitVecRef):
                    if right_val.size() == 1: return right_val == 1
                    else: return right_val != 0
                else: return BoolVal(False)
            elif op == 'not':
                 if isinstance(right_val, z3.BoolRef): return Not(right_val)
                 elif isinstance(right_val, z3.BitVecRef) and right_val.size() == 1: return right_val == 0
                 else: return BoolVal(True)
            elif op == 'and':
                 if isinstance(left_val, z3.BitVecRef) and left_val.size()==1: left_val = (left_val == 1)
                 if isinstance(right_val, z3.BitVecRef) and right_val.size()==1: right_val = (right_val == 1)
                 if isinstance(left_val, z3.BoolRef) and isinstance(right_val, z3.BoolRef): return And(left_val, right_val)
                 else: return BoolVal(False)

            # --- Comparison Ops ---
            elif op == '==':
                 if is_left_z3 and is_right_z3: return left_val == right_val
                 else: return BoolVal(False)
            elif op == '!=':
                 if is_left_z3 and is_right_z3: return left_val != right_val
                 else: return BoolVal(False)
            elif op == '>':
                 if is_left_z3 and is_right_z3 and is_bv(left_val) and is_bv(right_val): return UGT(left_val, right_val)
                 else: return BoolVal(False)
            elif op == '<':
                 if is_left_z3 and is_right_z3 and is_bv(left_val) and is_bv(right_val): return ULT(left_val, right_val)
                 else: return BoolVal(False)
            elif op == '>=':
                 if is_left_z3 and is_right_z3 and is_bv(left_val) and is_bv(right_val): return UGE(left_val, right_val)
                 else: return BoolVal(False)
            elif op == '<=':
                 if is_left_z3 and is_right_z3 and is_bv(left_val) and is_bv(right_val): return ULE(left_val, right_val)
                 else: return BoolVal(False)
            # --- End Comparison Ops ---

            else: return None

        except z3.Z3Exception as e: print(f"Error Z3 build_z3 op '{op}': {e}"); return None
        except AttributeError as e: print(f"Error Attr build_z3 op '{op}': {e}"); return None

    return None

def apply_symbolic_action(action_name, action_params, current_fields, fsm_data, action_defs, fsm_field_widths, symbol_scope='global'):
    """Aplica os efeitos de uma ação P4 simbolicamente."""
    action_def = action_defs.get(action_name)
    if not action_def: return {}
    modified_fields = {}

    for prim in action_def.get('primitives', []):
        op = prim.get('op'); params = prim.get('parameters', [])
        if op == 'assign' and len(params) == 2:
            dest = params[0]; source = params[1]
            if dest['type'] != 'field': continue
            dest_val = dest['value']; dest_key = tuple(dest_val) if len(dest_val)==2 else (dest_val[1],dest_val[2])
            dest_bitwidth = fsm_field_widths.get(dest_key, 32) # Usa cache

            source_val = None; source_bitwidth = dest_bitwidth
            if source['type'] == 'runtime_data':
                idx = source['value']
                if idx < len(action_def.get('runtime_data',[])):
                    pdef=action_def['runtime_data'][idx]; pname=pdef['name']; pwidth=pdef['bitwidth']
                    cval = action_params.get(pname)
                    if is_symbolic_token(cval):
                        sym_name = sanitize_symbol_name(
                            f"sym__{pname}__{symbol_scope}__{action_name}__{dest_key[0]}_{dest_key[1]}"
                        )
                        source_val = BitVec(sym_name, pwidth)
                        source_bitwidth = pwidth
                    elif cval is not None:
                        try: int_v = p4_runtime_value_to_int(cval, pwidth); source_val = BitVecVal(int_v, pwidth); source_bitwidth = pwidth
                        except Exception as e: print(f"Error BitVecVal {pname}={cval}: {e}")
            elif source['type'] == 'field':
                fval=source['value']; key=tuple(fval) if len(fval)==2 else (fval[1],fval[2])
                source_val = current_fields.get(key)
                if source_val is not None and hasattr(source_val, 'size'): source_bitwidth = source_val.size()
            elif source['type'] == 'expression':
                source_val = build_z3_expression(source, current_fields, dest_bitwidth) # Passa dest_bw como default
                if isinstance(source_val, int): source_val = BitVecVal(source_val, dest_bitwidth)
                if source_val is not None and hasattr(source_val, 'size'): source_bitwidth = source_val.size()
            elif source['type'] == 'hexstr':
                try: int_v = int(source['value'], 16); source_val = BitVecVal(int_v, dest_bitwidth); source_bitwidth = dest_bitwidth
                except: pass
            if isinstance(source_val, int): source_val = BitVecVal(source_val, dest_bitwidth)
            if source_val is not None and isinstance(source_val, z3.BitVecRef):
                if dest_bitwidth != source_bitwidth:
                    if dest_bitwidth > source_bitwidth: source_val = ZeroExt(dest_bitwidth - source_bitwidth, source_val)
                    else: source_val = Extract(dest_bitwidth - 1, 0, source_val)
                modified_fields[dest_key] = source_val
        elif op == 'mark_to_drop':
             key = ('standard_metadata', 'egress_spec'); bw = fsm_field_widths.get(key, 9); bw = 9 if bw != 9 else 9
             modified_fields[key] = BitVecVal(511, bw)
    return modified_fields

def execute_symbolic_table_egress(table_def, current_fields, runtime_entries, fsm_data, action_defs, fsm_field_widths):
    """Executa uma tabela Egress simbolicamente."""
    next_fields = current_fields.copy()
    entries = runtime_entries.get(table_def['name'], [])
    default_action_id = table_def.get('default_entry', {}).get('action_id')
    default_action_name="NoAction"; a_info=next((a for a in fsm_data.get('actions',[]) if a.get('id')==default_action_id), None);
    if a_info: default_action_name = a_info['name']

    modifiable_fields = set()
    possible_actions = set(e.get('action','NoAction') for e in entries) | {default_action_name}
    for aname in possible_actions:
        adef = action_defs.get(aname);
        if not adef: continue
        for prim in adef.get('primitives',[]):
            op=prim.get('op'); params=prim.get('parameters',[])
            if op=='assign' and len(params)>0 and params[0].get('type')=='field':
                dval=params[0]['value']; key=tuple(dval) if len(dval)==2 else (dval[1],dval[2])
                modifiable_fields.add(key)
            elif op=='mark_to_drop': modifiable_fields.add(('standard_metadata','egress_spec'))

    default_mods = apply_symbolic_action(default_action_name, {}, current_fields, fsm_data, action_defs, fsm_field_widths, symbol_scope='default')

    for field_key in modifiable_fields:
        final_expr = default_mods.get(field_key, current_fields.get(field_key))

        # Determina target_sort usando fsm_field_widths
        target_bw = fsm_field_widths.get(field_key, 32)
        target_sort = BitVecSort(target_bw)

        for entry_idx, entry in enumerate(reversed(entries)):
            match_cond = BoolVal(True)
            for fstr, mval_info in entry.get('match',{}).items():
                parts=fstr.split('.'); fkey=tuple(parts) if len(parts)==2 else (parts[1],parts[2]) if len(parts)==3 else None
                if fkey is None: match_cond = BoolVal(False); break
                fvar = current_fields.get(fkey)
                # Checa se fvar eh BitVecRef antes de size()
                if fvar is None or not isinstance(fvar, z3.BitVecRef):
                    match_cond = BoolVal(False); break
                mtype=next((k['match_type'] for k in table_def.get('key',[]) if k.get('name')==fstr or k.get('target')==list(fkey)),'exact')
                econd = None
                try:
                    if mtype == 'exact':
                        if is_symbolic_token(mval_info):
                            sym_name = sanitize_symbol_name(f"match_{table_def.get('name', 'table')}_{fstr}_{entry_idx}")
                            econd = (fvar == BitVec(sym_name, fvar.size()))
                        else:
                            cval=p4_runtime_value_to_int(mval_info,fvar.size()); econd=(fvar == BitVecVal(cval,fvar.size()))
                    elif mtype == 'lpm':
                        if (not isinstance(mval_info, (list, tuple)) or len(mval_info) != 2):
                            match_cond = BoolVal(False); break
                        val_str, prefix = mval_info
                        if is_symbolic_token(val_str) or is_symbolic_token(prefix):
                            econd = BoolVal(True)
                        else:
                            prefix_int = int(prefix)
                            bitwidth = fvar.size()
                            cval = p4_runtime_value_to_int(val_str, bitwidth)
                            if prefix_int <= 0:
                                econd = BoolVal(True)
                            elif prefix_int >= bitwidth:
                                econd = (fvar == BitVecVal(cval, bitwidth))
                            else:
                                shift = bitwidth - prefix_int
                                mask_int = ((1 << bitwidth) - 1) ^ ((1 << shift) - 1)
                                mask_bv = BitVecVal(mask_int, bitwidth)
                                econd = (fvar & mask_bv) == (BitVecVal(cval, bitwidth) & mask_bv)
                    elif mtype == 'ternary':
                        if (not isinstance(mval_info, (list, tuple)) or len(mval_info) != 2):
                            match_cond = BoolVal(False); break
                        val_str, mask_str = mval_info
                        if is_symbolic_token(val_str) or is_symbolic_token(mask_str):
                            econd = BoolVal(True)
                        else:
                            cval = p4_runtime_value_to_int(val_str, fvar.size())
                            mask = p4_runtime_value_to_int(mask_str, fvar.size())
                            mask_bv = BitVecVal(mask, fvar.size())
                            econd = (fvar & mask_bv) == (BitVecVal(cval, fvar.size()) & mask_bv)
                    else: match_cond = BoolVal(False); break
                except Exception as e: print(f"Error Z3 match {fstr}: {e}"); match_cond = BoolVal(False); break
                if econd is not None: match_cond = And(match_cond, econd)
                elif not is_false(match_cond): match_cond = BoolVal(False); break
            if is_false(match_cond): continue

            entry_scope = f"entry_{entry_idx}_{table_def.get('name', 'table')}"
            entry_mods = apply_symbolic_action(
                entry.get('action','NoAction'),
                entry.get('action_params',{}),
                current_fields,
                fsm_data,
                action_defs,
                fsm_field_widths,
                symbol_scope=entry_scope
            )
            val_if_match = entry_mods.get(field_key, current_fields.get(field_key))

            # Converte valores nao-Z3 para Z3 usando target_sort
            if not isinstance(val_if_match, z3.ExprRef):
                 int_v = p4_runtime_value_to_int(val_if_match, target_bw)
                 try: val_if_match = BitVecVal(int_v, target_sort)
                 except Exception as e: print(f"Error BitVecVal val_if_match {int_v} size {target_bw}: {e}"); continue

            if not isinstance(final_expr, z3.ExprRef):
                 int_v = p4_runtime_value_to_int(final_expr, target_bw)
                 try: final_expr = BitVecVal(int_v, target_sort)
                 except Exception as e: print(f"Error BitVecVal final_expr {int_v} size {target_bw}: {e}"); continue

            # Chama If apenas se os sorts forem compativeis
            if val_if_match.sort() == final_expr.sort():
                 final_expr = If(match_cond, val_if_match, final_expr)
            else:
                 print(f"FATAL Error: Sort mismatch in Egress If for {field_key}. Then:{val_if_match.sort()}, Else:{final_expr.sort()}")
                 pass

        if final_expr is not None:
             try: next_fields[field_key] = simplify(final_expr)
             except z3.Z3Exception: next_fields[field_key] = final_expr
    return next_fields

# --- Ponto de Entrada Principal ---
if __name__ == "__main__":
    if len(sys.argv) != 7:
        print("Uso: python3 run_table_egress.py <fsm.json> <runtime_cfg> <in_states> <sw_id> <tbl_name> <out_states>")
        exit(1)
    fsm_file, config_file, input_states_file, switch_id, table_name, output_states_file = sys.argv[1:7]

    fsm_data = load_json(fsm_file)
    runtime_entries_all = load_json(config_file)
    initial_states = load_json(input_states_file)
    runtime_entries = runtime_entries_all.get(switch_id, {})

    # Cache de bitwidths
    fsm_field_widths = {}
    header_types = {ht['name']: ht for ht in fsm_data.get('header_types', [])}
    for h in fsm_data.get('headers', []):
        h_name = h.get('name'); ht_name = h.get('header_type')
        if not h_name or not ht_name or ht_name not in header_types: continue
        for f_info in header_types[ht_name].get('fields', []):
            if len(f_info)>=2: f_name,f_width=f_info[0],f_info[1]
            if isinstance(f_name,str) and isinstance(f_width,int): fsm_field_widths[(h_name,f_name)]=f_width
    if ('standard_metadata','egress_spec') not in fsm_field_widths: fsm_field_widths[('standard_metadata','egress_spec')]=9


    # Cria campos Z3
    fields = {}; all_hdr_names = [h.get('name') for h in fsm_data.get('headers',[]) if h.get('name')]
    for h_name in all_hdr_names:
        if h_name == 'scalars': continue
        key_valid = (h_name, '$valid$'); fields[key_valid] = BitVec(f"{h_name}.$valid$", 1)
        for (h,f), w in fsm_field_widths.items():
             if h == h_name: fields[(h,f)] = BitVec(f"{h}.{f}", w)
    if ('standard_metadata','$valid$') not in fields:
        fields[('standard_metadata','$valid$')] = BitVec("standard_metadata.$valid$", 1)
        if ('standard_metadata','egress_spec') in fsm_field_widths:
             w = fsm_field_widths[('standard_metadata','egress_spec')]
             fields[('standard_metadata','egress_spec')] = BitVec("standard_metadata.egress_spec", w)


    action_defs = {a['name']: a for a in fsm_data.get('actions', [])}
    egress_pipeline = next((p for p in fsm_data.get('pipelines',[]) if p.get('name')=='egress'),None)
    if not egress_pipeline: print("Erro: Pipeline 'egress' não encontrado."); exit(1)
    target_table_def = next((t for t in egress_pipeline.get('tables',[]) if t.get('name')==table_name),None)
    if not target_table_def: print(f"Erro: Tabela '{table_name}' não encontrada."); exit(1)

    print(f"Calculando caminho Egress até '{table_name}'...")
    _path_cache.clear()
    path_conditions = find_path_to_table(egress_pipeline, egress_pipeline.get("init_table"), table_name, set(), fields)
    if path_conditions is None: print(f"AVISO: Tabela '{table_name}' inalcançável.")

    print(f"--- Carregados {len(initial_states)} estados de '{Path(input_states_file).name}' ---")
    print(f"--- Analisando Egress '{table_name}' para SWITCH '{switch_id}' ---")
    output_states = []; analysis_solver = Solver()

    for i, state in enumerate(initial_states):
        print("\n" + "="*50 + f"\nAnalisando Estado Entrada #{i} ({state.get('description','No desc')})")
        analysis_solver.reset()
        decls=[f"(declare-const {v.sexpr()} (_ BitVec {v.sort().size()}))" for v in fields.values() if isinstance(v, z3.BitVecRef)] # So declara BitVecs
        p_asserts=[f"(assert {s})" for s in state.get('z3_constraints_smt2',[])]
        path_asserts=[f"(assert {c.sexpr()})" for c in path_conditions] if path_conditions else []
        script="\n".join(decls+p_asserts+path_asserts)
        try:
            with suppress_c_stdout_stderr(): analysis_solver.from_string(script)
            if analysis_solver.check() == unsat: print("  -> AVISO: Estado + Cond Egress INALCANÇÁVEIS."); continue
        except Exception as e: print(f"  -> ERRO Z3: Falha SMT: {e}. Pulando."); continue

        current_sym_fields = fields.copy()
        if "field_updates" in state:
            z3_decls = {v.sexpr(): v for k,v in fields.items() if isinstance(v, z3.BitVecRef)} # So BitVecs
            for fstr, estr in state["field_updates"].items():
                parts=fstr.split('.'); fkey=tuple(parts) if len(parts)==2 else (parts[1],parts[2]) if len(parts)==3 else None
                if fkey and fkey in current_sym_fields:
                    try:
                        target_var = fields.get(fkey)
                        if target_var is None:
                            continue
                        with suppress_c_stdout_stderr():
                            current_sym_fields[fkey] = parse_field_update_expr(estr, decls=z3_decls, target_var=target_var)
                    except Exception as e: print(f"Erro parse SMT field_update '{fstr}': {e}")

        final_sym_fields = execute_symbolic_table_egress(
             target_table_def, current_sym_fields, runtime_entries, fsm_data, action_defs, fsm_field_widths
        )

        tbl_updates = {}
        for fkey, final_v in final_sym_fields.items():
            init_v = current_sym_fields.get(fkey); final_smt, init_smt = None, None
            try:
                if isinstance(final_v, z3.ExprRef): final_smt = simplify(final_v).sexpr()
                if isinstance(init_v, z3.ExprRef): init_smt = simplify(init_v).sexpr()
                if final_smt != init_smt:
                    fstr=f"{fkey[0]}.{fkey[1]}";
                    if final_smt is not None: tbl_updates[fstr] = final_smt
            except z3.Z3Exception:
                 if isinstance(final_v, z3.ExprRef) and isinstance(init_v, z3.ExprRef):
                     final_smt_nosimp = final_v.sexpr(); init_smt_nosimp = init_v.sexpr()
                     if final_smt_nosimp != init_smt_nosimp: fstr=f"{fkey[0]}.{fkey[1]}"; tbl_updates[fstr] = final_smt_nosimp
                 elif isinstance(final_v, z3.ExprRef): fstr=f"{fkey[0]}.{fkey[1]}"; tbl_updates[fstr] = final_v.sexpr()

        combined_updates = state.get("field_updates",{}).copy(); combined_updates.update(tbl_updates)
        new_state = {
            "description": state.get("description","???") + f" -> {table_name}",
            "z3_constraints_smt2": state.get('z3_constraints_smt2',[]),
            "present_headers": state.get("present_headers",[]),
            "history": state.get("history",[]) + [table_name],
            "field_updates": combined_updates
        }
        output_states.append(new_state)
        print(f"  -> Estado saida gerado com {len(tbl_updates)} atualizacoes.")

    out_path = Path(output_states_file)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as f: json.dump(output_states, f, indent=2)
        print(f"\nAnalise Egress concluida. {len(output_states)} estados salvos em '{out_path.name}'.")
    except Exception as e: print(f"\nErro ao salvar '{out_path.name}': {e}"); exit(1)
