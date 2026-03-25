import json
import traceback
import sys
# Set up paths so we can import z3 and run_table
sys.path.append('/app/workspace')
import z3
import run_table

fsm_data = run_table.load_json('/app/workspace/custom_test_out/custom_test.json')
fields = {}
for h in fsm_data.get('headers', []):
    ht_name, h_name = h.get('header_type'), h.get('name')
    if h_name and h_name != 'scalars':
        valid_field_name = f"{h_name}.$valid$"
        fields[(h_name, '$valid$')] = z3.BitVec(valid_field_name, 1)

ingress = next((p for p in fsm_data.get('pipelines',[]) if p.get('name') == 'ingress'), None)
run_table._path_cache.clear()
path_conditions = run_table.find_path_to_table(ingress, ingress.get('init_table'), 'MyIngress.tcp_exact', set(), fields)

print("path_conditions is None:", path_conditions is None)
if path_conditions is not None:
    for c in path_conditions:
        print("Path Condition:", c.sexpr())

# Let's also parse the SMT strings from input state 0
with open('/app/workspace/output/custom_test_parser_states.json') as f:
    s = json.load(f)[0]

declarations_smt2 = [f"(declare-const {var.sexpr()} (_ BitVec {var.sort().size()}))" for var in fields.values()]
parser_assertions = [f"(assert {cond})" for cond in s['z3_constraints_smt2']]
path_assertions = [f"(assert {cond.sexpr()})" for cond in path_conditions] if path_conditions is not None else []
full_script = "\n".join(declarations_smt2 + parser_assertions + path_assertions)

print("\n--- SMT Script ---")
print(full_script)

s_z3 = z3.Solver()
s_z3.from_string(full_script)
print("\n--- Check Result ---")
print(s_z3.check())
