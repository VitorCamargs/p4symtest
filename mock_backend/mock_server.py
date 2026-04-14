# mock_server.py — Mock Backend for P4SymTest
# Mirrors all endpoints of the real backend/app.py
# but returns pre-collected mock JSON files instead of running real analysis.
#
# Mock files are read from: ../frontendV2/src/mocks/{scenario}/
# Runs on port 5001 (real backend uses 5000)

from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
from pathlib import Path

app = Flask(__name__)
CORS(app)

# ── Paths ──────────────────────────────────────────────────────────────────────
MOCK_DIR = Path(__file__).parent.parent / 'frontendV2' / 'src' / 'mocks'
RUNTIME_CONFIG = Path(__file__).parent.parent / 'runtime_config.json'

def get_mock_dir():
    scenario = request.args.get('scenario', 'default')
    scenario_dir = MOCK_DIR / scenario
    if not scenario_dir.exists():
        scenario_dir = MOCK_DIR / 'default'
    return scenario_dir

def load_mock(filename: str):
    """Load a JSON mock file by name from the active scenario directory."""
    path = get_mock_dir() / filename
    if not path.exists():
        return None
    with open(path, 'r') as f:
        return json.load(f)

def list_snapshots():
    """Return all _output.json files plus parser_states.json, sorted."""
    active_dir = get_mock_dir()
    if not active_dir.exists():
        return []
    files = [
        f for f in os.listdir(active_dir)
        if f.endswith('_output.json') or f == 'parser_states.json'
    ]
    files.sort(key=lambda x: (x != 'parser_states.json', x))
    return files

def extract_parser_info(fsm_data):
    if not fsm_data or not fsm_data.get('parsers'):
        return None
    parser = fsm_data['parsers'][0]
    return {
        'name': parser.get('name', 'Parser'),
        'init_state': parser.get('init_state'),
        'states': [
            {
                'name': s.get('name'),
                'operations': len(s.get('parser_ops', [])),
                'transitions': len(s.get('transitions', []))
            }
            for s in parser.get('parse_states', [])
        ]
    }

def _action_name_by_id(fsm_data, action_id):
    """Look up an action name by its integer id."""
    if action_id is None:
        return 'NoAction'
    for a in fsm_data.get('actions', []):
        if a.get('id') == action_id:
            return a.get('name', 'NoAction')
    return 'NoAction'


def _table_schema(table_def, fsm_data):
    """Extract a concise schema for a table: its match keys, available actions, and default action."""
    default_action_id = table_def.get('default_entry', {}).get('action_id')
    # Collect unique action runtime params for each action
    actions = []
    for a_name in table_def.get('actions', []):
        action_def = next((a for a in fsm_data.get('actions', []) if a['name'] == a_name), None)
        params = []
        if action_def:
            params = [
                {'name': p['name'], 'bitwidth': p['bitwidth']}
                for p in action_def.get('runtime_data', [])
            ]
        actions.append({'name': a_name, 'params': params})

    return {
        'name': table_def.get('name'),
        'keys': [
            {
                'field': k.get('name'),
                'target': k.get('target'),
                'match_type': k.get('match_type', 'exact'),
            }
            for k in table_def.get('key', [])
        ],
        'actions': actions,
        'default_action': _action_name_by_id(fsm_data, default_action_id),
    }


def derive_components(fsm_data):
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
        p = fsm_data['parsers'][0]
        components['parser'] = {
            'name': p.get('name', 'Parser'),
            'states': len(p.get('parse_states', []))
        }
    for pipeline in fsm_data.get('pipelines', []):
        key = None
        if pipeline.get('name') == 'ingress':
            key = 'ingress_tables'
        elif pipeline.get('name') == 'egress':
            key = 'egress_tables'
        if key:
            tables = pipeline.get('tables', [])
            components[key] = [{'name': t.get('name')} for t in tables]
            for t in tables:
                components['table_schemas'].append(_table_schema(t, fsm_data))
    components['actions'] = [{'name': a.get('name')} for a in fsm_data.get('actions', [])]
    components['headers'] = [
        {'name': h.get('name'), 'type': h.get('header_type')}
        for h in fsm_data.get('headers', [])
    ]
    if fsm_data.get('deparsers'):
        d = fsm_data['deparsers'][0]
        components['deparser'] = {
            'name': d.get('name', 'deparser'),
            'order': d.get('order', [])
        }
    return components


# ══════════════════════════════════════════════════════════════════════════════
# UPLOAD ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/upload/p4', methods=['POST'])
def upload_p4():
    fsm_data = load_mock('programa.json')
    if fsm_data is None:
        return jsonify({'error': 'Mock file programa.json not found in active scenario'}), 500
    return jsonify({
        'message': 'P4 compilado com sucesso (mock)',
        'fsm_data': fsm_data
    })


@app.route('/api/upload/json', methods=['POST'])
def upload_json():
    file_type = request.form.get('type', 'unknown')
    filename = request.files.get('file').filename if 'file' in request.files else 'unknown.json'
    return jsonify({
        'message': f"Arquivo '{filename}' ({file_type}) salvo com sucesso. (mock)",
        'type': file_type,
        'filename': filename
    })


# ══════════════════════════════════════════════════════════════════════════════
# ANALYSIS ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/analyze/parser', methods=['POST'])
def analyze_parser():
    states = load_mock('parser_states.json')
    if states is None:
        return jsonify({'error': 'Mock parser_states.json not found'}), 500

    fsm_data = load_mock('programa.json')
    parser_info = extract_parser_info(fsm_data)

    return jsonify({
        'message': 'Análise do parser concluída (mock)',
        'states': states,
        'parser_info': parser_info,
        'state_count': len(states),
        'output_file': 'parser_states.json'
    })


@app.route('/api/analyze/reachability', methods=['POST'])
def analyze_reachability():
    reachability = {
        'MyIngress.ipv4_lpm': {
            'reachable': True,
            'conditions': ['hdr.ipv4.isValid()']
        },
        'MyIngress.ipv4_acl': {
            'reachable': True,
            'conditions': ['hdr.ipv4.isValid()']
        },
        'MyIngress.tcp_exact': {
            'reachable': True,
            'conditions': ['hdr.tcp.isValid()']
        },
        'MyIngress.myTunnel_exact': {
            'reachable': True,
            'conditions': ['hdr.myTunnel.isValid()']
        },
        'MyEgress.egress_port_smac': {
            'reachable': True,
            'conditions': ['hdr.ethernet.isValid()']
        }
    }
    return jsonify({
        'message': 'Análise de alcançabilidade concluída (mock)',
        'reachability': reachability
    })


@app.route('/api/analyze/table', methods=['POST'])
def analyze_table():
    data = request.get_json() or {}
    table_name = data.get('table_name')
    switch_id  = data.get('switch_id', 's1')
    input_states_file = data.get('input_states')

    if not table_name:
        return jsonify({'error': 'table_name não fornecido'}), 400
    if not input_states_file:
        return jsonify({'error': 'input_states não fornecido'}), 400

    input_stem = Path(input_states_file).stem
    safe_table = table_name.replace('.', '_')
    output_filename = f'{switch_id}_{safe_table}_from_{input_stem}_output.json'

    output_states = load_mock(output_filename)
    if output_states is None:
        alt_filename = f'{safe_table}_from_{input_stem}_output.json'
        output_states = load_mock(alt_filename)

    if output_states is None:
        alt_filename2 = f'{switch_id}_{safe_table}_from_parser_states_output.json'
        output_states = load_mock(alt_filename2)

    if output_states is None:
        alt_filename3 = f'{safe_table}_from_parser_states_output.json'
        output_states = load_mock(alt_filename3)

    if output_states is None:
        return jsonify({
            'error': f'Mock não encontrado para tabela "{table_name}"',
            'tried': [output_filename, alt_filename2]
        }), 404

    return jsonify({
        'message': f'Análise da tabela {table_name} concluída (mock)',
        'results_summary': [],
        'output_states': output_states,
        'output_file': output_filename
    })


@app.route('/api/analyze/egress_table', methods=['POST'])
def analyze_egress_table():
    data = request.get_json() or {}
    table_name = data.get('table_name')
    switch_id  = data.get('switch_id', 's1')
    input_states_file = data.get('input_states')

    if not table_name or not input_states_file:
        return jsonify({'error': 'Faltam dados'}), 400

    input_stem      = Path(input_states_file).stem
    safe_table      = table_name.replace('.', '_')
    output_filename = f'{switch_id}_{safe_table}_from_{input_stem}_output.json'

    output_states = load_mock(output_filename)
    
    if output_states is None:
        alt_filename2 = f'{switch_id}_{safe_table}_from_parser_states_output.json'
        output_states = load_mock(alt_filename2)

    if output_states is None:
        return jsonify({'error': 'Mock não encontrado'}), 404

    return jsonify({
        'message': f'Análise da tabela Egress {table_name} concluída (mock)',
        'output_states': output_states,
        'output_file': output_filename
    })


@app.route('/api/analyze/deparser', methods=['POST'])
def analyze_deparser():
    data = request.get_json() or {}
    input_states_file = data.get('input_states')
    if not input_states_file:
        return jsonify({'error': 'input_states não fornecido'}), 400

    input_stem      = Path(input_states_file).stem
    output_filename = f'deparser_output_from_{input_stem}.json'

    results = load_mock(output_filename)
    if results is None:
        return jsonify({'error': 'Mock não encontrado'}), 404

    fsm_data    = load_mock('programa.json') or {}
    deparser_def = fsm_data.get('deparsers', [{}])[0] if fsm_data.get('deparsers') else {}
    static_info = {
        'name': deparser_def.get('name', 'deparser'),
        'order': deparser_def.get('order', [])
    }

    return jsonify({
        'message': 'Análise do Deparser concluída',
        'static_info': static_info,
        'analysis_results': results,
        'output_file': output_filename
    })


@app.route('/api/generate/rules', methods=['POST'])
def generate_rules():
    if RUNTIME_CONFIG.exists():
        with open(RUNTIME_CONFIG, 'r') as f:
            rules = json.load(f)
    else:
        rules = {'targets': {}}

    return jsonify({
        'message': 'Regras geradas com sucesso (mock)',
        'rules': rules
    })


@app.route('/api/info/components', methods=['GET'])
def get_components():
    fsm_data = load_mock('programa.json')
    if fsm_data is None:
        return jsonify({'error': 'Mock programa.json not found'}), 404
    return jsonify(derive_components(fsm_data))


@app.route('/api/info/snapshots', methods=['GET'])
def get_snapshots():
    return jsonify({'snapshots': list_snapshots()})


@app.route('/api/mock/source', methods=['GET'])
def get_mock_source():
    """Retrieve the raw .p4 file for the current scenario."""
    path = get_mock_dir() / 'programa.p4'
    if not path.exists():
        return jsonify({'error': 'Source file not found'}), 404
    with open(path, 'r') as f:
        return jsonify({'source': f.read()})


if __name__ == '__main__':
    print('=' * 60)
    print('🟡 P4SymTest MOCK Backend (Dynamic Scenario)')
    print(f'   Base Mocks: {MOCK_DIR.resolve()}')
    print('   Servidor: http://localhost:5001')
    print('=' * 60)
    app.run(debug=True, host='0.0.0.0', port=5001)
