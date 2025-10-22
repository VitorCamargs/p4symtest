# run_deparser.py
import json
import sys
from z3 import *
import os
from contextlib import contextmanager
from pathlib import Path # Adicionado para melhor manipulação de caminhos

# --- Funções Auxiliares ---

@contextmanager
def suppress_c_stdout_stderr():
    """Suprime a saída C/C++ do Z3 (que polui o stdout)."""
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
    if not filepath.exists():
        print(f"Erro: Arquivo '{filename}' não foi encontrado.")
        exit(1)
    try:
        with open(filepath, 'r') as f: return json.load(f)
    except json.JSONDecodeError as e:
        print(f"Erro: Arquivo '{filename}' não é um JSON válido: {e}")
        exit(1)
    except Exception as e:
        print(f"Erro inesperado ao carregar '{filename}': {e}")
        exit(1)

# --- Ponto de Entrada Principal ---
if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Uso: python3 run_deparser.py <fsm.json> <estados_entrada.json> <estados_saida.json>")
        exit(1)

    fsm_file = sys.argv[1]
    input_states_file = sys.argv[2]
    output_file = sys.argv[3]

    # Garante que os arquivos de entrada são caminhos absolutos ou relativos ao workspace
    # (importante se chamado de diretórios diferentes)
    workspace_dir = Path(__file__).parent
    fsm_path = workspace_dir / Path(fsm_file).name
    # Arquivos de estado são esperados no diretório 'output' relativo ao workspace
    input_states_path = workspace_dir / 'output' / Path(input_states_file).name
    output_path = workspace_dir / 'output' / Path(output_file).name

    # Carrega dados
    fsm_data = load_json(fsm_path)
    input_states = load_json(input_states_path)
    if not isinstance(input_states, list):
         print(f"Erro: Arquivo de estados de entrada '{input_states_path}' não contém uma lista JSON.")
         exit(1)

    # Encontra o deparser
    if not fsm_data or not fsm_data.get('deparsers'):
        print(f"Erro: Seção 'deparsers' não encontrada ou vazia no FSM '{fsm_path}'.")
        exit(1)
    deparser_def = fsm_data['deparsers'][0]

    deparser_order = deparser_def.get('order', [])

    # Cria campos Z3
    fields = {}
    header_types = {ht['name']: ht for ht in fsm_data.get('header_types', [])}

    for h in fsm_data.get('headers', []):
        ht_name = h.get('header_type')
        h_name = h.get('name')
        if not h_name: continue # Ignora headers sem nome

        if ht_name in header_types:
            for f_info in header_types[ht_name].get('fields', []):
                # f_info pode ser [name, width, signed] ou [name, width]
                if len(f_info) >= 2:
                    f_name, f_width = f_info[0], f_info[1]
                    if isinstance(f_name, str) and isinstance(f_width, int) and f_width > 0:
                         fields[(h_name, f_name)] = BitVec(f"{h_name}.{f_name}", f_width)

        # Declara $valid$ para todos, incluindo 'scalars', para compatibilidade com estados antigos/externos
        fields[(h_name, '$valid$')] = BitVec(f"{h_name}.$valid$", 1)

    # Gera as strings de declaração SMT-LIB para todas as variáveis
    declarations_smt2 = [f"(declare-const {var.sexpr()} (_ BitVec {var.sort().size()}))" for var in fields.values()]

    print(f"--- Analisando Deparser '{deparser_def.get('name', 'deparser')}' ---")
    print(f"Snapshot de Entrada: '{input_states_path.name}'")
    print(f"Ordem de emissão P4: {', '.join(deparser_order)}")

    analysis_results = []

    # Analisa cada estado de entrada
    for i, state in enumerate(input_states):
        print(f"\nAnalisando para o Estado de Entrada #{i} ({state.get('description', 'Sem descrição')})")

        # --- Extrai dados adicionais do estado de entrada ---
        state_history = state.get("history", ["Desconhecido"]) # Pega o histórico do estado de entrada
        state_constraints_smt2 = state.get("z3_constraints_smt2", []) # Pega todas as restrições
        state_field_updates = state.get("field_updates", {}) # Pega os updates

        parser_constraints_smt2_asserts = [f"(assert {s})" for s in state_constraints_smt2]

        # Monta o script SMT-LIB completo para verificação de satisfatibilidade
        full_script = "\n".join(declarations_smt2) + "\n" + "\n".join(parser_constraints_smt2_asserts)

        solver = Solver()
        is_satisfiable = False
        try:
            with suppress_c_stdout_stderr():
                solver.from_string(full_script)
            is_satisfiable = solver.check() == sat
        except Exception as e:
            print(f"  - ERRO: Falha ao processar SMT-LIB para o estado #{i}: {e}")
            # Cria um resultado indicando o erro
            state_result = {
                "input_state": state.get('description', 'Erro no parse SMT'),
                "input_state_index": i,
                "history": state_history,
                "full_constraints_smt2": state_constraints_smt2,
                "non_drop_condition_smt": None, # Não aplicável aqui
                "satisfiable": False, # Marca como insatisfatório devido ao erro
                "error": f"Falha ao processar SMT-LIB: {e}",
                "emission_status": []
            }
            analysis_results.append(state_result)
            continue # Pula para o próximo estado

        # --- Extrai a condição de não-descarte (se aplicável) ---
        non_drop_condition_smt = None
        # Procura pela restrição explícita adicionada por run_table.py
        non_drop_constraint_explicit = "(distinct standard_metadata.egress_spec #b111111111)"
        if any(non_drop_constraint_explicit in s for s in state_constraints_smt2):
             # Tenta pegar a expressão atualizada de egress_spec dos field_updates
             egress_spec_update_expr = state_field_updates.get("standard_metadata.egress_spec")
             if egress_spec_update_expr:
                 # Cria a condição de não-drop usando a expressão atualizada
                 non_drop_condition_smt = f"(distinct {egress_spec_update_expr} #b111111111)"
             else:
                 # Se não houver update, usa a restrição explícita como fallback
                 non_drop_condition_smt = non_drop_constraint_explicit

        # Cria o dicionário de resultado base
        state_result = {
            "input_state": state.get('description', 'Sem descrição'),
            "input_state_index": i,
            "history": state_history, # <-- Incluído
            "full_constraints_smt2": state_constraints_smt2, # <-- Incluído
            "non_drop_condition_smt": non_drop_condition_smt, # <-- Incluído
            "satisfiable": is_satisfiable,
            "emission_status": [] # Será preenchido abaixo se satisfatório
        }

        if not is_satisfiable:
            print("  - AVISO: Estado de entrada insatisfatório. Pulando análise de emissão.")
            analysis_results.append(state_result)
            continue # Pula para o próximo estado

        # Se satisfatório, verifica a validade de cada header na ordem do deparser
        print("  - Estado satisfatório. Verificando emissão de headers:")
        for header_name in deparser_order:
            valid_field = fields.get((header_name, '$valid$'))
            if valid_field is None:
                print(f"    - AVISO: Header '{header_name}' na ordem do deparser, mas não encontrado nos campos Z3.")
                state_result["emission_status"].append({"header": header_name, "status": "Erro: Campo não definido"})
                continue

            emission_status = "Desconhecido"
            # Verifica se o header PODE ser emitido (valid == 1)
            solver.push()
            try:
                 solver.add(valid_field == 1)
                 check_can_emit = solver.check()
            except Exception as e:
                 print(f"    - ERRO ao checar {header_name}.$valid$ == 1: {e}")
                 check_can_emit = unknown # Trata erro como desconhecido
            solver.pop()

            if check_can_emit == sat:
                # É *possível* emitir. Verifica se PODE NÃO ser emitido (valid == 0)
                solver.push()
                try:
                    solver.add(valid_field == 0)
                    check_can_not_emit = solver.check()
                except Exception as e:
                     print(f"    - ERRO ao checar {header_name}.$valid$ == 0: {e}")
                     check_can_not_emit = unknown
                solver.pop()

                if check_can_not_emit == sat:
                    emission_status = "Condicional" # Pode ser 1 e pode ser 0
                    print(f"    - {header_name}: EMITIDO (Condicionalmente)")
                elif check_can_not_emit == unsat:
                    emission_status = "Sempre" # Só pode ser 1
                    print(f"    - {header_name}: EMITIDO (Sempre)")
                else: # check_can_not_emit == unknown
                     emission_status = "Desconhecido (Erro Z3?)"
                     print(f"    - {header_name}: Status Desconhecido (Erro na verificação de não-emissão)")

            elif check_can_emit == unsat:
                emission_status = "Nunca" # Não pode ser 1, então é sempre 0
                print(f"    - {header_name}: NÃO EMITIDO (Inválido)")
            else: # check_can_emit == unknown
                 emission_status = "Desconhecido (Erro Z3?)"
                 print(f"    - {header_name}: Status Desconhecido (Erro na verificação de emissão)")

            state_result["emission_status"].append({"header": header_name, "status": emission_status})

        analysis_results.append(state_result)

    # Salva resultados
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True) # Garante que diretório output exista
        with open(output_path, 'w') as f:
            json.dump(analysis_results, f, indent=2)
        print(f"\nAnálise do Deparser concluída. {len(analysis_results)} estados analisados.")
        print(f"Resultados salvos em '{output_path}'.")
    except Exception as e:
        print(f"\nErro ao salvar resultados em '{output_path}': {e}")
        exit(1)

