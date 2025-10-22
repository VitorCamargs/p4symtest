# run_parser.py (Versão Corrigida - sem scalars.$valid$)
import json
import sys
from z3 import *

def load_json(filename):
    try:
        with open(filename, 'r') as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Erro ao carregar '{filename}': {e}"); exit(1)

def create_symbolic_field(name, bitwidth):
    return BitVec(name, bitwidth)

def explore_parser(state_name, path_desc_list, path_conditions, extracted_headers):
    """
    Função recursiva que explora os caminhos do parser.
    Esta versão não acumula restrições de validade, apenas as de caminho.
    """
    global parser_results, fields, fsm_data
    parser_def = fsm_data['parsers'][0]
    state = next((s for s in parser_def['parse_states'] if s['name'] == state_name), None)
    if not state: return

    current_step_desc = state_name
    new_extracted_headers = extracted_headers.copy()
    
    for op in state.get('parser_ops', []):
        if op['op'] == 'extract':
            hdr_name = op['parameters'][0]['value']
            current_step_desc += f" [extract {hdr_name}]"
            new_extracted_headers.add(hdr_name)

    new_path_desc = path_desc_list + [current_step_desc]
    
    default_transition = None
    conditional_transitions = []
    transition_key_def = state.get('transition_key', [])
    
    for t in state['transitions']:
        if t['type'] == 'default':
            default_transition = t
            continue
        if transition_key_def:
            h_name, f_name = transition_key_def[0]['value']
            symb_field = fields[(h_name, f_name)]
            val = int(t['value'], 16)
            z3_cond = (symb_field == val)
            conditional_transitions.append({'transition': t, 'z3': z3_cond})

    for current in conditional_transitions:
        next_state = current['transition']['next_state']
        if next_state:
            explore_parser(
                next_state,
                new_path_desc,
                path_conditions + [current['z3']],
                new_extracted_headers
            )

    if default_transition:
        negated_z3 = [Not(ct['z3']) for ct in conditional_transitions]
        final_path_conditions = path_conditions + negated_z3
        next_state = default_transition['next_state']
        
        if next_state is None:
            # --- LÓGICA DE GERAÇÃO DE ESTADO CORRIGIDA ---
            final_constraints = []
            # 1. Adiciona as condições de transição do caminho
            final_constraints.extend(final_path_conditions)
            
            # 2. Adiciona as condições de validade FINAIS (EXCETO para 'scalars')
            for h in fsm_data['headers']:
                h_name = h['name']
                # *** CORREÇÃO: Pula o header 'scalars' ***
                if h_name == 'scalars':
                    continue
                    
                is_valid_constraint = (fields[(h_name, '$valid$')] == 1) if h_name in new_extracted_headers else (fields[(h_name, '$valid$')] == 0)
                final_constraints.append(is_valid_constraint)

            constraints_as_smt2 = [c.sexpr() for c in final_constraints]
            
            parser_results.append({
                "description": " -> ".join(new_path_desc),
                "z3_constraints_smt2": constraints_as_smt2,
                "present_headers": sorted(list(new_extracted_headers)),
                "history": ["Parser"],
            })
        else:
            explore_parser(next_state, new_path_desc, final_path_conditions, new_extracted_headers)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python3 run_parser.py <arquivo_de_saida.json>"); exit(1)
    output_file = sys.argv[1]

    fsm_data = load_json("programa.json") # Assume o nome do arquivo fsm
    parser_results = []
    
    fields = {}
    header_types = {ht['name']: ht for ht in fsm_data['header_types']}
    for h in fsm_data['headers']:
        ht_name = h['header_type']
        if ht_name in header_types:
            for f_name, f_width, _ in header_types[ht_name]['fields']:
                fields[(h['name'], f_name)] = BitVec(f"{h['name']}.{f_name}", f_width)
        # *** CORREÇÃO: Não cria $valid$ para 'scalars' ***
        if h['name'] != 'scalars':
            fields[(h['name'], '$valid$')] = BitVec(f"{h['name']}.$valid$", 1)
    
    print("--- Iniciando análise simbólica do Parser ---")
    parser_initial_state = fsm_data['parsers'][0]['init_state']
    explore_parser(parser_initial_state, [], [], set())
    
    print(f"{len(parser_results)} caminhos viáveis do parser foram encontrados.")
    with open(output_file, 'w') as f:
        json.dump(parser_results, f, indent=2)
    print(f"Resultados do parser salvos com sucesso em '{output_file}'.")