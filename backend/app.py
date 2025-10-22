# app.py - Backend Flask para P4SymTest (Versão Docker)
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import subprocess
import json
import os
import tempfile
from pathlib import Path

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
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd or WORKSPACE_DIR,
            capture_output=True,
            text=True,
            timeout=30
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
            'error': 'Comando excedeu o tempo limite de 30 segundos'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def load_json_file(filepath):
    """Carrega um arquivo JSON"""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception as e:
        return None

# ============================================
# ENDPOINTS - UPLOAD DE ARQUIVOS
# ============================================
@app.route('/api/upload/p4', methods=['POST'])
def upload_p4():
    """Recebe código P4 e compila para JSON"""
    if 'file' not in request.files:
        return jsonify({'error': 'Nenhum arquivo fornecido'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Nome de arquivo vazio'}), 400
    
    # Salva o arquivo P4
    p4_path = P4FILES_DIR / 'programa.p4'
    file.save(p4_path)
    
    # --- INÍCIO DA CORREÇÃO ---
    
    # 1. Define o *diretório* de saída que o p4c criará.
    # O p4c vai criar uma pasta chamada 'programa.json'
    json_output_dir = P4FILES_DIR / 'programa.json'
    
    # 2. Executa o comando de compilação
    # O -o aponta para o diretório de saída
    compile_cmd = f'p4c --target bmv2 --arch v1model -o {json_output_dir} {p4_path}'
    
    result = run_command(compile_cmd, cwd=P4FILES_DIR)
    
    if not result['success']:
        return jsonify({
            'error': 'Erro na compilação do P4',
            'details': result['stderr']
        }), 400
    
    # 3. O arquivo JSON *real* está DENTRO do diretório que o p4c criou.
    json_real_file_path = json_output_dir / 'programa.json'
    
    # 4. Carrega o FSM gerado a partir do caminho *correto* do arquivo
    fsm_data = load_json_file(json_real_file_path)

    if fsm_data is None:
        return jsonify({
            'error': 'Falha ao ler o JSON compilado pelo P4C',
            'details': f'O arquivo esperado não foi encontrado em: {json_real_file_path}'
        }), 500
    
    # 5. Copia o *arquivo* real (não o diretório) para o workspace principal
    import shutil
    shutil.copy(json_real_file_path, WORKSPACE_DIR / 'programa.json')
    
    # --- FIM DA CORREÇÃO ---
    
    return jsonify({
        'message': 'P4 compilado com sucesso',
        'fsm_data': fsm_data
    })
@app.route('/api/upload/json', methods=['POST'])
def upload_json():
    """Recebe arquivos JSON (FSM, topology, runtime_config)"""
    if 'file' not in request.files:
        return jsonify({'error': 'Nenhum arquivo fornecido'}), 400
    
    file = request.files['file']
    file_type = request.form.get('type', 'unknown')
    
    # Define o nome do arquivo baseado no tipo
    filename_map = {
        'fsm': 'programa.json',
        'topology': 'topology.json',
        'runtime_config': 'runtime_config.json',
        'parser_states': 'parser_states.json'
    }
    
    filename = filename_map.get(file_type, file.filename)
    filepath = WORKSPACE_DIR / filename
    
    file.save(filepath)
    
    # Carrega e retorna o conteúdo
    data = load_json_file(filepath)
    
    return jsonify({
        'message': f'Arquivo {filename} carregado com sucesso',
        'data': data,
        'type': file_type
    })

# ============================================
# ENDPOINTS - ANÁLISE DO PARSER
# ============================================

@app.route('/api/analyze/parser', methods=['POST'])
def analyze_parser():
    """Executa análise simbólica do parser"""
    
    # Verifica se o FSM existe
    fsm_path = WORKSPACE_DIR / 'programa.json'
    if not fsm_path.exists():
        return jsonify({'error': 'FSM não encontrado. Faça upload do P4 primeiro.'}), 400
    
    # Arquivo de saída
    output_path = OUTPUT_DIR / 'parser_states.json'
    
    # Executa run_parser.py
    cmd = f'python3 run_parser.py {output_path}'
    result = run_command(cmd)
    
    if not result['success']:
        return jsonify({
            'error': 'Erro ao executar análise do parser',
            'details': result['stderr']
        }), 500
    
    # Carrega os resultados
    parser_states = load_json_file(output_path)
    
    if not parser_states:
        return jsonify({'error': 'Erro ao carregar resultados do parser'}), 500
    
    # Extrai informações do FSM para o grafo
    fsm_data = load_json_file(fsm_path)
    parser_info = extract_parser_info(fsm_data)
    
    return jsonify({
        'message': 'Análise do parser concluída',
        'states': parser_states,
        'parser_info': parser_info,
        'state_count': len(parser_states)
    })

def extract_parser_info(fsm_data):
    """Extrai informações estruturais do parser"""
    if not fsm_data or 'parsers' not in fsm_data:
        return None
    
    parser = fsm_data['parsers'][0]
    
    return {
        'name': parser.get('name', 'Parser'),
        'init_state': parser.get('init_state'),
        'states': [
            {
                'name': s['name'],
                'operations': len(s.get('parser_ops', [])),
                'transitions': len(s.get('transitions', []))
            }
            for s in parser.get('parse_states', [])
        ]
    }

# ============================================
# ENDPOINTS - ANÁLISE DE ALCANÇABILIDADE
# ============================================

@app.route('/api/analyze/reachability', methods=['POST'])
def analyze_reachability():
    """Analisa condições de alcançabilidade das tabelas"""
    
    fsm_path = WORKSPACE_DIR / 'programa.json'
    if not fsm_path.exists():
        return jsonify({'error': 'FSM não encontrado'}), 400
    
    # Executa path_analyzer.py
    cmd = f'python3 path_analyzer.py {fsm_path}'
    result = run_command(cmd)
    
    if not result['success']:
        return jsonify({
            'error': 'Erro ao analisar alcançabilidade',
            'details': result['stderr']
        }), 500
    
    # Parse da saída para extrair condições
    reachability = parse_reachability_output(result['stdout'])
    
    return jsonify({
        'message': 'Análise de alcançabilidade concluída',
        'reachability': reachability
    })

def parse_reachability_output(output):
    """Parse da saída do path_analyzer.py"""
    reachability = {}
    current_table = None
    
    lines = output.split('\n')
    for line in lines:
        if 'Analisando caminho para a tabela:' in line:
            # Extrai nome da tabela
            current_table = line.split("'")[1]
            reachability[current_table] = {
                'conditions': [],
                'reachable': True
            }
        elif current_table and 'Condições para alcançar' in line:
            continue
        elif current_table and line.strip() and line.strip()[0].isdigit():
            # Extrai condição
            condition = line.split('. ', 1)[1] if '. ' in line else line.strip()
            reachability[current_table]['conditions'].append(condition)
        elif current_table and 'INALCANÇÁVEL' in line:
            reachability[current_table]['reachable'] = False
            reachability[current_table]['conditions'] = ['INALCANÇÁVEL']
        elif current_table and 'INCONDICIONALMENTE' in line:
            reachability[current_table]['conditions'] = ['Incondicional']
    
    return reachability

# ============================================
# ENDPOINTS - GERAÇÃO DE REGRAS
# ============================================

@app.route('/api/generate/rules', methods=['POST'])
def generate_rules():
    """Gera regras de runtime baseadas na topologia"""
    
    fsm_path = WORKSPACE_DIR / 'programa.json'
    topology_path = WORKSPACE_DIR / 'topology.json'
    output_path = WORKSPACE_DIR / 'runtime_config.json'
    
    if not fsm_path.exists() or not topology_path.exists():
        return jsonify({'error': 'FSM ou topologia não encontrados'}), 400
    
    # Executa generate_rules.py
    cmd = f'python3 generate_rules.py {topology_path} {fsm_path} {output_path}'
    result = run_command(cmd)
    
    if not result['success']:
        return jsonify({
            'error': 'Erro ao gerar regras',
            'details': result['stderr']
        }), 500
    
    # Carrega as regras geradas
    rules = load_json_file(output_path)
    
    return jsonify({
        'message': 'Regras geradas com sucesso',
        'rules': rules
    })

# ============================================
# ENDPOINTS - ANÁLISE DE TABELAS
# ============================================

@app.route('/api/analyze/table', methods=['POST'])
def analyze_table():
    """Executa análise simbólica de uma tabela específica"""
    
    data = request.get_json()
    table_name = data.get('table_name')
    switch_id = data.get('switch_id', 's1')
    input_states_file = data.get('input_states', 'parser_states.json')
    
    if not table_name:
        return jsonify({'error': 'Nome da tabela não fornecido'}), 400
    
    # Verifica arquivos necessários
    fsm_path = WORKSPACE_DIR / 'programa.json'
    topology_path = WORKSPACE_DIR / 'topology.json'
    runtime_path = WORKSPACE_DIR / 'runtime_config.json'
    input_states_path = OUTPUT_DIR / input_states_file
    
    missing_files = []
    if not fsm_path.exists(): missing_files.append('FSM')
    if not topology_path.exists(): missing_files.append('Topology')
    if not runtime_path.exists(): missing_files.append('Runtime Config')
    if not input_states_path.exists(): missing_files.append('Parser States')
    
    if missing_files:
        return jsonify({
            'error': f'Arquivos faltando: {", ".join(missing_files)}'
        }), 400
    
    # Nome do arquivo de saída
    output_filename = f'{switch_id}_{table_name.replace(".", "_")}_output.json'
    output_path = OUTPUT_DIR / output_filename
    
    # Executa run_table.py
    cmd = (f'python3 run_table.py {fsm_path} {topology_path} {runtime_path} '
           f'{input_states_path} {switch_id} {table_name} {output_path}')
    
    result = run_command(cmd)
    
    if not result['success']:
        return jsonify({
            'error': 'Erro ao executar análise da tabela',
            'details': result['stderr'],
            'stdout': result['stdout']
        }), 500
    
    # Parse da saída para extrair resultados
    analysis_results = parse_table_analysis(result['stdout'])
    
    # Carrega os estados resultantes
    output_states = load_json_file(output_path)
    
    return jsonify({
        'message': f'Análise da tabela {table_name} concluída',
        'results': analysis_results,
        'output_states': output_states,
        'output_file': output_filename
    })

def parse_table_analysis(output):
    """Parse da saída do run_table.py"""
    results = []
    current_state = None
    
    lines = output.split('\n')
    for line in lines:
        if 'Analisando para o Estado de Entrada' in line:
            current_state = {
                'state_id': line.split('#')[1].split()[0] if '#' in line else 'unknown',
                'description': line.split('(')[1].split(')')[0] if '(' in line else '',
                'reachability_check': None,
                'forwarding_results': [],
                'drops': []
            }
        elif current_state and 'NUNCA alcançará' in line:
            current_state['reachability_check'] = 'unreachable'
            results.append(current_state)
            current_state = None
        elif current_state and 'A tabela é alcançável' in line:
            current_state['reachability_check'] = 'reachable'
        elif current_state and 'ENCAMINHADO para a porta' in line:
            # Extrai informações de forwarding
            parts = line.split("'")
            target = parts[1] if len(parts) > 1 else 'unknown'
            port = line.split('porta ')[1].split()[0] if 'porta' in line else 'unknown'
            current_state['forwarding_results'].append({
                'target': target,
                'port': port,
                'status': 'success'
            })
        elif current_state and 'DESCARTADO (drop)' in line:
            target = line.split("'")[1] if "'" in line else 'unknown'
            current_state['drops'].append({
                'target': target,
                'status': 'drop'
            })
        elif current_state and '=' * 50 in line and current_state['reachability_check']:
            # Fim do estado atual
            results.append(current_state)
            current_state = None
    
    # Adiciona último estado se existir
    if current_state and current_state['reachability_check']:
        results.append(current_state)
    
    return results

# ============================================
# ENDPOINTS - ANÁLISE COMBINADA
# ============================================

@app.route('/api/analyze/combined', methods=['POST'])
def analyze_combined():
    """Executa análise combinada de alcançabilidade (Parser vs Pipeline)"""
    
    fsm_path = WORKSPACE_DIR / 'programa.json'
    parser_states_path = OUTPUT_DIR / 'parser_states.json'
    
    if not fsm_path.exists() or not parser_states_path.exists():
        return jsonify({'error': 'Arquivos necessários não encontrados'}), 400
    
    # Executa combined_analyzer.py
    cmd = f'python3 combined_analyzer.py {fsm_path} {parser_states_path}'
    result = run_command(cmd)
    
    if not result['success']:
        return jsonify({
            'error': 'Erro ao executar análise combinada',
            'details': result['stderr']
        }), 500
    
    # Parse dos resultados
    combined_results = parse_combined_analysis(result['stdout'])
    
    return jsonify({
        'message': 'Análise combinada concluída',
        'results': combined_results
    })

def parse_combined_analysis(output):
    """Parse da saída do combined_analyzer.py"""
    results = {}
    current_table = None
    current_parser_state = None
    
    lines = output.split('\n')
    for line in lines:
        if 'Analisando Alcançabilidade para a Tabela:' in line:
            current_table = line.split("'")[1]
            results[current_table] = {
                'reachable_from': [],
                'unreachable_from': [],
                'conditions': []
            }
        elif current_table and 'Testando' in line and "'" in line:
            current_parser_state = line.split("'")[1]
        elif current_table and current_parser_state:
            if 'Alcançável' in line:
                results[current_table]['reachable_from'].append(current_parser_state)
            elif 'Inalcançável' in line or 'CONTRADIÇÃO' in line:
                results[current_table]['unreachable_from'].append(current_parser_state)
            current_parser_state = None
    
    return results

# ============================================
# ENDPOINTS - INFORMAÇÕES
# ============================================

@app.route('/api/info/components', methods=['GET'])
def get_components():
    """Retorna informações sobre os componentes do programa P4"""
    
    fsm_path = WORKSPACE_DIR / 'programa.json'
    if not fsm_path.exists():
        return jsonify({'error': 'FSM não encontrado'}), 400
    
    fsm_data = load_json_file(fsm_path)
    
    # Extrai componentes
    components = {
        'parser': None,
        'tables': [],
        'actions': [],
        'headers': []
    }
    
    # Parser
    if 'parsers' in fsm_data and fsm_data['parsers']:
        parser = fsm_data['parsers'][0]
        components['parser'] = {
            'name': parser.get('name', 'Parser'),
            'states': len(parser.get('parse_states', []))
        }
    
    # Tables e conditionals
    if 'pipelines' in fsm_data:
        for pipeline in fsm_data['pipelines']:
            if pipeline['name'] == 'ingress':
                components['tables'] = [
                    {'name': t['name']} 
                    for t in pipeline.get('tables', [])
                ]
    
    # Actions
    if 'actions' in fsm_data:
        components['actions'] = [
            {'name': a['name']} 
            for a in fsm_data['actions']
        ]
    
    # Headers
    if 'headers' in fsm_data:
        components['headers'] = [
            {'name': h['name'], 'type': h['header_type']} 
            for h in fsm_data['headers']
        ]
    
    return jsonify(components)

# ============================================
# SERVIDOR
# ============================================

if __name__ == '__main__':
    print("🚀 P4SymTest Backend iniciado!")
    print(f"📁 Workspace: {WORKSPACE_DIR.absolute()}")
    print(f"🔧 Scripts Python devem estar em: {WORKSPACE_DIR.absolute()}")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=5000)