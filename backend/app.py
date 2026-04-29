# app.py - Backend Flask para P4SymTest (Versão Docker)
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import subprocess
import json
import os
import tempfile
from pathlib import Path

from table_diagnostics import (
    build_table_analysis_facts,
    diagnostics_unavailable,
    request_table_diagnostics,
    table_diagnostics_enabled,
)

app = Flask(__name__)
CORS(app)  # Permite requisições do frontend

# Diretórios de trabalho
WORKSPACE_DIR = Path('/app/workspace')
P4FILES_DIR = WORKSPACE_DIR / 'p4files'
OUTPUT_DIR = WORKSPACE_DIR / 'output'

# Garante que os diretórios existem
WORKSPACE_DIR.mkdir(exist_ok=True)
P4FILES_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# ============================================
# UTILITÁRIOS
# ============================================

def run_command(cmd, cwd=None):
    """Executa um comando shell e retorna o resultado"""
    try:
        # Aumentado timeout para 60 segundos
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd or WORKSPACE_DIR,
            capture_output=True,
            text=True,
            timeout=60
        )
        return {
            'success': result.returncode == 0,
            'stdout': result.stdout,
            'stderr': result.stderr,
            'returncode': result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'error': 'Comando excedeu o tempo limite de 60 segundos'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def load_json_file(filepath):
    """Carrega um arquivo JSON de forma segura"""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Warn: Arquivo JSON não encontrado: {filepath}")
        return None
    except json.JSONDecodeError as e:
        print(f"Warn: Erro ao decodificar JSON {filepath}: {e}")
        return None
    except Exception as e:
        print(f"Warn: Erro inesperado ao carregar JSON {filepath}: {e}")
        return None

def maybe_table_diagnostics(
    *,
    pipeline,
    table_name,
    switch_id,
    input_states_file,
    output_filename,
    input_states,
    output_states,
    stdout,
    stderr,
):
    """Build facts and optionally call llm-analyzer without affecting base output."""
    if not table_diagnostics_enabled():
        return None

    fsm_data = load_json_file(WORKSPACE_DIR / 'programa.json') or {}
    runtime_config = load_json_file(WORKSPACE_DIR / 'runtime_config.json') or {}
    topology = load_json_file(WORKSPACE_DIR / 'topology.json') or {}
    p4_source_paths = [
        P4FILES_DIR / 'programa.p4',
        WORKSPACE_DIR / 'programa.p4',
        WORKSPACE_DIR / 'custom_test.p4',
    ]

    try:
        facts = build_table_analysis_facts(
            pipeline=pipeline,
            table_name=table_name,
            switch_id=switch_id,
            input_snapshot_filename=input_states_file,
            output_snapshot_filename=output_filename,
            input_states=input_states,
            output_states=output_states,
            runtime_config=runtime_config,
            topology=topology,
            fsm_data=fsm_data,
            p4_source_paths=p4_source_paths,
            stdout=stdout,
            stderr=stderr,
        )
    except Exception as exc:
        print(f"Warn: falha ao extrair facts de diagnostico: {exc}")
        return diagnostics_unavailable(table_name, "facts_extraction_error", exc)

    return request_table_diagnostics(facts)

# ============================================
# ENDPOINTS - UPLOAD DE ARQUIVOS
# ============================================
@app.route('/api/upload/p4', methods=['POST'])
def upload_p4():
    """Recebe código P4 e compila para JSON FSM"""
    if 'file' not in request.files:
        return jsonify({'error': 'Nenhum arquivo fornecido'}), 400
    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': 'Nome de arquivo inválido ou vazio'}), 400

    p4_path = P4FILES_DIR / 'programa.p4'
    try:
        file.save(p4_path)
    except Exception as e:
         return jsonify({'error': f"Erro ao salvar arquivo P4: {e}"}), 500

    # Define o diretório de saída para o p4c
    json_output_dir = P4FILES_DIR / 'programa.json'
    # Limpa diretório de saída antigo, se existir
    if json_output_dir.exists():
        import shutil
        shutil.rmtree(json_output_dir)

    compile_cmd = f'p4c --target bmv2 --arch v1model -o {json_output_dir} {p4_path}'
    result = run_command(compile_cmd, cwd=P4FILES_DIR)

    if not result['success']:
        return jsonify({'error': 'Erro na compilação do P4', 'details': result['stderr'] or result['stdout']}), 400

    json_real_file_path = json_output_dir / 'programa.json'
    fsm_data = load_json_file(json_real_file_path)

    if fsm_data is None:
        compile_output = result['stderr'] or result['stdout']
        return jsonify({'error': 'Falha ao ler o JSON compilado pelo P4C', 'details': f'Arquivo esperado não encontrado em: {json_real_file_path}. Saída do compilador: {compile_output}'}), 500

    try:
        import shutil
        # Copia o FSM JSON para o workspace principal para fácil acesso pelos scripts
        shutil.copy(json_real_file_path, WORKSPACE_DIR / 'programa.json')
    except Exception as e:
         return jsonify({'error': f'Erro ao copiar FSM para workspace: {e}'}), 500

    return jsonify({'message': 'P4 compilado com sucesso', 'fsm_data': fsm_data})

@app.route('/api/upload/json', methods=['POST'])
def upload_json():
    """Recebe arquivos JSON (FSM, topology, runtime_config, states)"""
    if 'file' not in request.files:
        return jsonify({'error': 'Nenhum arquivo fornecido'}), 400
    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': 'Nome de arquivo inválido ou vazio'}), 400

    file_type = request.form.get('type', 'unknown') # O frontend envia o tipo inferido

    filename_map = {'fsm': 'programa.json', 'topology': 'topology.json', 'runtime_config': 'runtime_config.json'}
    is_state_file = file_type == 'parser_states' or '_output.json' in file.filename

    if is_state_file:
         filename = file.filename # Mantem o nome original
         filepath = OUTPUT_DIR / filename # Salva em output/
    elif file_type in filename_map:
         filename = filename_map[file_type]
         filepath = WORKSPACE_DIR / filename # Salva no workspace/
    else:
         filename = file.filename # Tipo desconhecido, salva no workspace
         filepath = WORKSPACE_DIR / filename

    try:
        filepath.parent.mkdir(parents=True, exist_ok=True) # Garante que o diretório exista
        file.save(filepath)
    except Exception as e:
        return jsonify({'error': f"Erro ao salvar arquivo '{filename}': {e}"}), 500

    data = load_json_file(filepath) # Tenta carregar para validar JSON

    return jsonify({
        'message': f"Arquivo '{filename}' ({file_type}) salvo com sucesso." + (" (JSON inválido)" if data is None and file_type != 'unknown' else ""),
        'type': file_type,
        'filename': filename # Retorna o nome do arquivo salvo
    })

# ============================================
# ENDPOINTS - ANÁLISE DO PARSER
# ============================================

@app.route('/api/analyze/parser', methods=['POST'])
def analyze_parser():
    """Executa análise simbólica do parser e retorna estados"""
    fsm_path = WORKSPACE_DIR / 'programa.json'
    if not fsm_path.exists():
        return jsonify({'error': 'FSM não encontrado (programa.json). Faça upload primeiro.'}), 400

    output_path = OUTPUT_DIR / 'parser_states.json'
    cmd = f'python3 run_parser.py {fsm_path} {output_path}'
    result = run_command(cmd)

    if not result['success']:
        return jsonify({'error': 'Erro ao executar análise do parser', 'details': result['stderr'] or result['stdout']}), 500

    parser_states = load_json_file(output_path)
    if parser_states is None: # Checa se o load_json falhou
        return jsonify({'error': 'Erro ao carregar resultados do parser (arquivo JSON vazio, inválido ou não gerado)', 'details': result['stdout']}), 500

    fsm_data = load_json_file(fsm_path)
    parser_info = extract_parser_info(fsm_data)

    return jsonify({
        'message': 'Análise do parser concluída',
        'states': parser_states,
        'parser_info': parser_info,
        'state_count': len(parser_states),
        'output_file': 'parser_states.json' # Nome do arquivo gerado
    })

def extract_parser_info(fsm_data):
    """Extrai informações estruturais do parser (helper)"""
    if not fsm_data or not fsm_data.get('parsers'): return None
    parser = fsm_data['parsers'][0]
    return {
        'name': parser.get('name', 'Parser'),
        'init_state': parser.get('init_state'),
        'states': [{'name': s.get('name'), 'operations': len(s.get('parser_ops', [])), 'transitions': len(s.get('transitions', []))} for s in parser.get('parse_states', [])]
    }

def action_name_by_id(fsm_data, action_id):
    """Resolve o nome da ação a partir do id no FSM."""
    if action_id is None:
        return 'NoAction'
    for action in fsm_data.get('actions', []):
        if action.get('id') == action_id:
            return action.get('name', 'NoAction')
    return 'NoAction'

def table_schema_from_def(table_def, fsm_data):
    """Extrai o schema de uma tabela para a configuração dinâmica no frontend."""
    default_action_id = table_def.get('default_entry', {}).get('action_id')
    actions = []
    for action_name in table_def.get('actions', []):
        action_def = next((a for a in fsm_data.get('actions', []) if a.get('name') == action_name), None)
        params = []
        if action_def:
            params = [
                {'name': p.get('name'), 'bitwidth': p.get('bitwidth')}
                for p in action_def.get('runtime_data', [])
            ]
        actions.append({'name': action_name, 'params': params})

    return {
        'name': table_def.get('name'),
        'keys': [
            {
                'field': key.get('name'),
                'target': key.get('target'),
                'match_type': key.get('match_type', 'exact'),
            }
            for key in table_def.get('key', [])
        ],
        'actions': actions,
        'default_action': action_name_by_id(fsm_data, default_action_id),
    }

# ============================================
# ENDPOINTS - ANÁLISE DE ALCANÇABILIDADE (Pipeline)
# ============================================

@app.route('/api/analyze/reachability', methods=['POST'])
def analyze_reachability():
    """Analisa condições de alcançabilidade das tabelas no pipeline de ingress"""
    fsm_path = WORKSPACE_DIR / 'programa.json'
    if not fsm_path.exists(): return jsonify({'error': 'FSM não encontrado (programa.json)'}), 400

    cmd = f'python3 path_analyzer.py {fsm_path}'
    result = run_command(cmd)
    # path_analyzer geralmente não falha, apenas imprime
    reachability = parse_reachability_output(result['stdout'])

    return jsonify({'message': 'Análise de alcançabilidade concluída', 'reachability': reachability})

def parse_reachability_output(output):
    """Parse do stdout do path_analyzer.py (helper)"""
    reachability = {}
    lines = output.split('\n')
    current_table_name = None
    current_conditions = []

    for line in lines:
        if "Tabela: '" in line:
            if current_table_name: # Salva a tabela anterior
                 if not current_conditions and reachability[current_table_name]['reachable']:
                      current_conditions = ["Incondicional"]
                 reachability[current_table_name]['conditions'] = current_conditions

            try:
                current_table_name = line.split("'")[1]
                reachability[current_table_name] = {'conditions': [], 'reachable': False}
                current_conditions = []
            except IndexError: current_table_name = None
        elif current_table_name:
            if "Status: ALCANÇÁVEL" in line: reachability[current_table_name]['reachable'] = True
            elif "Status: INALCANÇÁVEL" in line:
                reachability[current_table_name]['reachable'] = False
                reason = "Estrutural"
                if "Contradição Lógica" in line: reason = "Contradição Lógica"
                current_conditions = [f"INALCANÇÁVEL ({reason})"]
                reachability[current_table_name]['conditions'] = current_conditions
                current_table_name = None # Finaliza
            elif line.strip().startswith("- "): # Linha de condição SMT-LIB
                condition = line.strip()[2:]
                if condition != "True": current_conditions.append(condition) # Ignora 'True' explícito

    # Salva a última tabela
    if current_table_name:
         if not current_conditions and reachability[current_table_name]['reachable']:
              current_conditions = ["Incondicional"]
         reachability[current_table_name]['conditions'] = current_conditions

    return reachability

# ============================================
# ENDPOINTS - GERAÇÃO DE REGRAS DE RUNTIME
# ============================================

@app.route('/api/generate/rules', methods=['POST'])
def generate_rules():
    """Gera regras de runtime baseadas na topologia e FSM"""
    fsm_path = WORKSPACE_DIR / 'programa.json'
    topology_path = WORKSPACE_DIR / 'topology.json'
    output_path = WORKSPACE_DIR / 'runtime_config.json'

    if not fsm_path.exists() or not topology_path.exists():
        return jsonify({'error': 'FSM ou topologia não encontrados.'}), 400

    cmd = f'python3 generate_rules.py {topology_path} {fsm_path} {output_path}'
    result = run_command(cmd)

    if not result['success']:
        return jsonify({'error': 'Erro ao gerar regras', 'details': result['stderr'] or result['stdout']}), 500

    rules = load_json_file(output_path)
    if rules is None:
        return jsonify({'error': 'Regras geradas, mas falha ao ler o arquivo de saída.', 'details': result['stdout']}), 500

    return jsonify({'message': 'Regras geradas com sucesso', 'rules': rules})

# ============================================
# ENDPOINTS - ANÁLISE DE TABELAS (MODULAR)
# ============================================

@app.route('/api/analyze/table', methods=['POST'])
def analyze_table():
    """Executa análise simbólica de uma tabela usando um snapshot de entrada"""
    data = request.get_json()
    if not data: return jsonify({'error': 'Requisição sem JSON'}), 400

    table_name = data.get('table_name')
    switch_id = data.get('switch_id', 's1') # Default para 's1'
    input_states_file = data.get('input_states')

    if not table_name: return jsonify({'error': 'Nome da tabela não fornecido'}), 400
    if not input_states_file: return jsonify({'error': 'Snapshot de entrada (input_states) não fornecido'}), 400

    fsm_path = WORKSPACE_DIR / 'programa.json'
    topology_path = WORKSPACE_DIR / 'topology.json'
    runtime_path = WORKSPACE_DIR / 'runtime_config.json'
    input_states_path = OUTPUT_DIR / input_states_file # Assume snapshots em output/

    missing = [p.name for p in [fsm_path, topology_path, runtime_path, input_states_path] if not p.exists()]
    if missing:
        return jsonify({'error': f'Arquivos necessários faltando: {", ".join(missing)}'}), 400

    output_filename = f'{switch_id}_{table_name.replace(".", "_")}_from_{Path(input_states_file).stem}_output.json'
    output_path = OUTPUT_DIR / output_filename

    cmd = (f'python3 run_table.py {fsm_path} {topology_path} {runtime_path} '
           f'{input_states_path} {switch_id} {table_name} {output_path}')
    result = run_command(cmd)

    if not result['success']:
        return jsonify({'error': f'Erro ao executar análise da tabela {table_name}', 'details': result['stderr'] or result['stdout'], 'stdout': result['stdout']}), 500

    output_states = load_json_file(output_path)
    analysis_summary = parse_table_analysis_stdout(result['stdout'])

    response_payload = {
        'message': f'Análise da tabela {table_name} concluída (usando {input_states_file})',
        'results_summary': analysis_summary,
        'output_states': output_states if output_states is not None else [],
        'output_file': output_filename
    }
    diagnostics = maybe_table_diagnostics(
        pipeline='ingress',
        table_name=table_name,
        switch_id=switch_id,
        input_states_file=input_states_file,
        output_filename=output_filename,
        input_states=load_json_file(input_states_path) or [],
        output_states=response_payload['output_states'],
        stdout=result.get('stdout', ''),
        stderr=result.get('stderr', ''),
    )
    if diagnostics is not None:
        response_payload['diagnostics'] = diagnostics

    return jsonify(response_payload)

def parse_table_analysis_stdout(output):
    """Parse do stdout do run_table.py para resumo legível (helper)"""
    # (Implementação anterior mantida, parece robusta)
    results = []
    current_state_summary = None
    lines = output.split('\n')
    for line in lines:
        if 'Analisando para o Estado de Entrada #' in line:
            if current_state_summary: results.append(current_state_summary)
            state_id = line.split('#')[1].split()[0] if '#' in line else '?'
            desc = line.split('(')[1].split(')')[0] if '(' in line else 'N/A'
            current_state_summary = {'state_id': state_id, 'description': desc, 'outcome': 'Processando...', 'details': []}
        elif current_state_summary:
            if 'AVISO: Análise pulada' in line or 'NUNCA alcançará' in line:
                current_state_summary['outcome'] = 'Inalcançável'
                results.append(current_state_summary); current_state_summary = None
            elif 'OK: A tabela é alcançável' in line:
                current_state_summary['outcome'] = 'Alcançável' # Pode ser sobrescrito
            elif '-> Resultado: SIM' in line:
                current_state_summary['outcome'] = 'Alcançável'
                current_state_summary['details'].append(line.split('-> Resultado: SIM, ')[1])
            elif 'AVISO: Todos os pacotes deste estado são descartados' in line:
                current_state_summary['outcome'] = 'Drop (Sempre)'
                current_state_summary['details'] = ["Pacote sempre descartado nesta etapa."]
                # Não finaliza aqui, espera o fim do bloco do estado
    if current_state_summary: results.append(current_state_summary)
    return results

# ============================================
# ENDPOINTS - ANÁLISE COMBINADA (Parser vs Pipeline Reachability)
# ============================================
@app.route('/api/analyze/combined', methods=['POST'])
def analyze_combined():
    """Executa análise combinada Parser vs Pipeline Reachability"""
    fsm_path = WORKSPACE_DIR / 'programa.json'
    parser_states_path = OUTPUT_DIR / 'parser_states.json'

    if not fsm_path.exists() or not parser_states_path.exists():
        return jsonify({'error': 'Arquivos FSM ou Parser States não encontrados.'}), 400

    cmd = f'python3 combined_analyzer.py {fsm_path} {parser_states_path}'
    result = run_command(cmd)

    combined_results = parse_combined_analysis_stdout(result['stdout'])

    return jsonify({
        'message': 'Análise combinada (Parser vs Pipeline) concluída',
        'results': combined_results,
        'details': result['stdout'] # Inclui stdout completo
    })

def parse_combined_analysis_stdout(output):
    """Parse do stdout do combined_analyzer.py (helper)"""
    # (Implementação anterior mantida)
    results_by_table = {}
    current_table = None
    lines = output.split('\n')
    for line in lines:
        if '##  Analisando Alcançabilidade para a Tabela:' in line:
            try:
                current_table = line.split("'")[1]
                results_by_table[current_table] = {'pipeline_conditions': [], 'state_comparisons': []}
            except IndexError: current_table = None
        elif current_table:
            if line.strip().startswith("- "): # Condição do pipeline
                 results_by_table[current_table]['pipeline_conditions'].append(line.strip()[2:])
            elif "Testando '" in line: # Comparação com estado do parser
                 state_desc = line.split("'")[1]
                 outcome_line = next((l for l in lines[lines.index(line)+1:] if '-> RESULTADO:' in l), None)
                 outcome = "Erro no parse"
                 if outcome_line:
                      if "Alcançável" in outcome_line: outcome = "Compatível"
                      elif "Inalcançável" in outcome_line: outcome = "Incompatível (Contradição)"
                 results_by_table[current_table]['state_comparisons'].append({'state': state_desc, 'outcome': outcome})
    return results_by_table

# ============================================
# ENDPOINTS - ANÁLISE DE TABELAS EGRESS (NOVO)
# ============================================

@app.route('/api/analyze/egress_table', methods=['POST'])
def analyze_egress_table():
    """Executa análise simbólica de uma tabela Egress específica"""
    data = request.get_json()
    if not data: return jsonify({'error': 'Requisição sem JSON'}), 400

    table_name = data.get('table_name') # Nome da tabela Egress
    switch_id = data.get('switch_id', 's1')
    input_states_file = data.get('input_states')

    if not table_name: return jsonify({'error': 'Nome da tabela Egress não fornecido'}), 400
    if not input_states_file: return jsonify({'error': 'Snapshot de entrada não fornecido'}), 400

    fsm_path = WORKSPACE_DIR / 'programa.json'
    runtime_path = WORKSPACE_DIR / 'runtime_config.json'
    input_states_path = OUTPUT_DIR / input_states_file

    missing = [p.name for p in [fsm_path, runtime_path, input_states_path] if not p.exists()]
    if missing:
        return jsonify({'error': f'Arquivos necessários faltando: {", ".join(missing)}'}), 400

    output_filename = f'{switch_id}_{table_name.replace(".", "_")}_from_{Path(input_states_file).stem}_output.json'
    output_path = OUTPUT_DIR / output_filename

    # Chama o novo script run_table_egress.py
    cmd = (f'python3 run_table_egress.py {fsm_path} {runtime_path} '
           f'{input_states_path} {switch_id} {table_name} {output_path}')

    print(f"Executando comando Egress Table: {cmd}") # Log para debug
    result = run_command(cmd)

    if not result['success']:
        return jsonify({
            'error': f'Erro ao executar análise da tabela Egress {table_name}',
            'details': result.get('stderr') or result.get('stdout', 'Sem detalhes.'),
            'stdout': result.get('stdout', '')
        }), 500

    output_states = load_json_file(output_path)
    if output_states is None:
         return jsonify({
             'error': 'Análise da tabela Egress executada, mas falha ao ler o JSON de resultado.',
             'details': result.get('stdout', ''),
             'output_file': output_filename
        }), 500

    # Pode adicionar parsing do stdout se run_table_egress.py gerar resumo
    # summary = parse_table_analysis_stdout(result['stdout'])

    response_payload = {
        'message': f'Análise da tabela Egress {table_name} concluída (usando {input_states_file})',
        # 'results_summary': summary,
        'output_states': output_states,
        'output_file': output_filename
    }
    diagnostics = maybe_table_diagnostics(
        pipeline='egress',
        table_name=table_name,
        switch_id=switch_id,
        input_states_file=input_states_file,
        output_filename=output_filename,
        input_states=load_json_file(input_states_path) or [],
        output_states=output_states,
        stdout=result.get('stdout', ''),
        stderr=result.get('stderr', ''),
    )
    if diagnostics is not None:
        response_payload['diagnostics'] = diagnostics

    return jsonify(response_payload)

# ============================================
# ENDPOINTS - ANÁLISE DO DEPARSER
# ============================================

@app.route('/api/analyze/deparser', methods=['POST'])
def analyze_deparser():
    """Executa análise simbólica do deparser usando um snapshot de entrada"""
    data = request.get_json()
    if not data: return jsonify({'error': 'Requisição sem JSON'}), 400

    input_states_file = data.get('input_states')
    if not input_states_file: return jsonify({'error': 'Snapshot de entrada (input_states) não fornecido'}), 400

    fsm_path = WORKSPACE_DIR / 'programa.json'
    input_states_path = OUTPUT_DIR / input_states_file

    missing = [p.name for p in [fsm_path, input_states_path] if not p.exists()]
    if missing:
        return jsonify({'error': f'Arquivos faltando: {", ".join(missing)}'}), 400

    output_filename = f'deparser_output_from_{Path(input_states_file).stem}.json'
    output_path = OUTPUT_DIR / output_filename

    cmd = f'python3 run_deparser.py {fsm_path} {input_states_path} {output_path}'
    result = run_command(cmd)

    if not result['success']:
        return jsonify({'error': 'Erro ao executar análise do deparser', 'details': result['stderr'] or result['stdout'], 'stdout': result['stdout']}), 500

    deparser_results = load_json_file(output_path)
    if deparser_results is None:
         return jsonify({'error': 'Análise do deparser executada, mas falha ao ler o arquivo de resultado JSON.', 'details': result['stdout']}), 500

    fsm_data = load_json_file(fsm_path)
    deparser_def = fsm_data.get('deparsers', [{}])[0] if fsm_data and fsm_data.get('deparsers') else {}
    static_info = {'name': deparser_def.get('name', 'deparser'), 'order': deparser_def.get('order', [])}

    return jsonify({
        'message': f'Análise do Deparser concluída (usando {input_states_file})',
        'static_info': static_info,
        'analysis_results': deparser_results, # Retorna a estrutura detalhada do JSON
        'output_file': output_filename
    })

# ============================================
# ENDPOINTS - INFORMAÇÕES GERAIS
# ============================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Healthcheck simples para Docker Compose."""
    return jsonify({'status': 'ok'}), 200

@app.route('/api/info/components', methods=['GET'])
def get_components():
    """Retorna informações sobre os componentes do programa P4 (do FSM)"""
    fsm_path = WORKSPACE_DIR / 'programa.json'
    fsm_data = load_json_file(fsm_path)
    if not fsm_data: return jsonify({'error': 'FSM não encontrado ou inválido (programa.json)'}), 404

    components = {
        'parser': None,
        'ingress_tables': [],
        'egress_tables': [],
        'actions': [],
        'headers': [],
        'deparser': None,
        'table_schemas': [],
    }
    if fsm_data.get('parsers'):
        p = fsm_data['parsers'][0]; components['parser'] = {'name': p.get('name', 'P'), 'states': len(p.get('parse_states', []))}
    for p in fsm_data.get('pipelines', []):
        key = 'ingress_tables' if p.get('name') == 'ingress' else 'egress_tables' if p.get('name') == 'egress' else None
        if key:
            tables = p.get('tables', [])
            components[key] = [{'name': t.get('name')} for t in tables]
            for table in tables:
                components['table_schemas'].append(table_schema_from_def(table, fsm_data))
    components['actions'] = [{'name': a.get('name')} for a in fsm_data.get('actions', [])]
    components['headers'] = [{'name': h.get('name'), 'type': h.get('header_type')} for h in fsm_data.get('headers', [])]
    if fsm_data.get('deparsers'):
        d = fsm_data['deparsers'][0]; components['deparser'] = {'name': d.get('name', 'D'), 'order': d.get('order', [])}
    return jsonify(components)

@app.route('/api/info/snapshots', methods=['GET'])
def get_snapshots():
    """Lista os arquivos JSON de snapshot disponíveis no diretório 'output'."""
    try:
        # Garante que o diretório de output exista antes de listar
        OUTPUT_DIR.mkdir(exist_ok=True)
        files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith('_output.json') or f == 'parser_states.json']
        files.sort(key=lambda x: (x != 'parser_states.json', x)) # parser_states.json primeiro
        return jsonify({'snapshots': files})
    except Exception as e:
        print(f"Erro ao listar snapshots: {e}")
        # Retorna apenas o default se houver erro ao listar o diretório
        return jsonify({'snapshots': ['parser_states.json']})

@app.route('/api/mock/source', methods=['GET'])
def get_mock_source():
    """Compatibilidade com o fluxo legado da V2 em modo mock/dev."""
    candidate_paths = [
        P4FILES_DIR / 'programa.p4',
        WORKSPACE_DIR / 'programa.p4',
        WORKSPACE_DIR / 'custom_test.p4',
    ]
    for source_path in candidate_paths:
        if source_path.exists():
            try:
                with open(source_path, 'r') as f:
                    return jsonify({'source': f.read(), 'filename': source_path.name})
            except Exception as e:
                return jsonify({'error': f'Falha ao ler arquivo fonte: {e}'}), 500
    return jsonify({'error': 'Source file not found'}), 404

# ============================================
# SERVIDOR
# ============================================

if __name__ == '__main__':
    print("*"*60)
    print("🚀 P4SymTest Backend Iniciado!")
    print(f"  - Workspace: {WORKSPACE_DIR.absolute()}")
    print(f"  - Output Dir: {OUTPUT_DIR.absolute()}")
    print(f"  - Servidor Flask rodando em http://0.0.0.0:5000")
    print("*"*60)
    # Habilita debug e reloader para desenvolvimento. Para produção, use um servidor WSGI.
    app.run(debug=True, host='0.0.0.0', port=5000)
