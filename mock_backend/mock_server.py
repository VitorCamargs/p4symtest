# mock_server.py — Mock Backend for P4SymTest
# Mirrors all endpoints of the real backend/app.py
# but returns pre-collected mock JSON files instead of running real analysis.
#
# Mock files are read from: ../frontendV2/src/mocks/
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

def load_mock(filename: str):
    """Load a JSON mock file by name from MOCK_DIR."""
    path = MOCK_DIR / filename
    if not path.exists():
        return None
    with open(path, 'r') as f:
        return json.load(f)

def list_snapshots():
    """Return all _output.json files plus parser_states.json, sorted."""
    files = [
        f for f in os.listdir(MOCK_DIR)
        if f.endswith('_output.json') or f == 'parser_states.json'
    ]
    files.sort(key=lambda x: (x != 'parser_states.json', x))
    return files

def extract_parser_info(fsm_data):
    """Mirror of app.py's extract_parser_info helper."""
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

def derive_components(fsm_data):
    """Mirror of app.py's get_components logic."""
    components = {
        'parser': None,
        'ingress_tables': [],
        'egress_tables': [],
        'actions': [],
        'headers': [],
        'deparser': None
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
            components[key] = [{'name': t.get('name')} for t in pipeline.get('tables', [])]
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
    """
    Real backend: accepts .p4 file, compiles with p4c, returns FSM JSON.
    Mock: ignores the file, returns programa.json as fsm_data.
    """
    fsm_data = load_mock('programa.json')
    if fsm_data is None:
        return jsonify({'error': 'Mock file programa.json not found'}), 500
    return jsonify({
        'message': 'P4 compilado com sucesso (mock)',
        'fsm_data': fsm_data
    })


@app.route('/api/upload/json', methods=['POST'])
def upload_json():
    """
    Real backend: saves uploaded JSON to workspace.
    Mock: accepts and acknowledges, does nothing.
    """
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
    """
    Real backend: runs run_parser.py, returns parser states.
    Mock: returns parser_states.json.
    """
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
    """
    Real backend: runs path_analyzer.py.
    Mock: returns static reachability derived from programa.json structure.
    """
    reachability = {
        'MyIngress.ipv4_lpm': {
            'reachable': True,
            'conditions': ['hdr.ipv4.isValid() && !hdr.myTunnel.isValid()']
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
    """
    Real backend: runs run_table.py for an Ingress table.
    Mock: resolves the output filename using the same naming convention as the real
    backend, then returns that mock file.

    filename = {switch_id}_{table_name.replace('.','_')}_from_{stem(input_states)}_output.json
    """
    data = request.get_json() or {}
    table_name = data.get('table_name')
    switch_id  = data.get('switch_id', 's1')
    input_states_file = data.get('input_states')

    if not table_name:
        return jsonify({'error': 'table_name não fornecido'}), 400
    if not input_states_file:
        return jsonify({'error': 'input_states não fornecido'}), 400

    input_stem = Path(input_states_file).stem  # e.g. "parser_states"
    safe_table = table_name.replace('.', '_')  # e.g. "MyIngress_ipv4_lpm"
    output_filename = f'{switch_id}_{safe_table}_from_{input_stem}_output.json'

    output_states = load_mock(output_filename)
    if output_states is None:
        # Fallback: try without switch_id prefix if not found
        alt_filename = f'{safe_table}_from_{input_stem}_output.json'
        output_states = load_mock(alt_filename)

    if output_states is None:
        return jsonify({
            'error': f'Mock não encontrado para tabela "{table_name}" com input "{input_states_file}"',
            'tried': output_filename
        }), 404

    return jsonify({
        'message': f'Análise da tabela {table_name} concluída (mock)',
        'results_summary': [],
        'output_states': output_states,
        'output_file': output_filename
    })


@app.route('/api/analyze/egress_table', methods=['POST'])
def analyze_egress_table():
    """
    Real backend: runs run_table_egress.py for an Egress table.
    Mock: same filename resolution as analyze_table.
    """
    data = request.get_json() or {}
    table_name = data.get('table_name')
    switch_id  = data.get('switch_id', 's1')
    input_states_file = data.get('input_states')

    if not table_name:
        return jsonify({'error': 'table_name não fornecido'}), 400
    if not input_states_file:
        return jsonify({'error': 'input_states não fornecido'}), 400

    input_stem      = Path(input_states_file).stem
    safe_table      = table_name.replace('.', '_')
    output_filename = f'{switch_id}_{safe_table}_from_{input_stem}_output.json'

    output_states = load_mock(output_filename)
    if output_states is None:
        return jsonify({
            'error': f'Mock não encontrado para tabela Egress "{table_name}" com input "{input_states_file}"',
            'tried': output_filename
        }), 404

    return jsonify({
        'message': f'Análise da tabela Egress {table_name} concluída (mock)',
        'output_states': output_states,
        'output_file': output_filename
    })


@app.route('/api/analyze/deparser', methods=['POST'])
def analyze_deparser():
    """
    Real backend: runs run_deparser.py.
    Mock: resolves filename as deparser_output_from_{stem(input_states)}.json
    """
    data = request.get_json() or {}
    input_states_file = data.get('input_states')

    if not input_states_file:
        return jsonify({'error': 'input_states não fornecido'}), 400

    input_stem      = Path(input_states_file).stem
    output_filename = f'deparser_output_from_{input_stem}.json'

    results = load_mock(output_filename)
    if results is None:
        return jsonify({
            'error': f'Mock não encontrado para deparser com input "{input_states_file}"',
            'tried': output_filename
        }), 404

    fsm_data    = load_mock('programa.json') or {}
    deparsers   = fsm_data.get('deparsers', [{}])
    deparser_def = deparsers[0] if deparsers else {}
    static_info = {
        'name': deparser_def.get('name', 'deparser'),
        'order': deparser_def.get('order', [])
    }

    return jsonify({
        'message': f'Análise do Deparser concluída (mock, usando {input_states_file})',
        'static_info': static_info,
        'analysis_results': results,
        'output_file': output_filename
    })


# ══════════════════════════════════════════════════════════════════════════════
# GENERATE ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/generate/rules', methods=['POST'])
def generate_rules():
    """
    Real backend: runs generate_rules.py, returns runtime_config.json.
    Mock: returns the project's runtime_config.json if present, else a stub.
    """
    # Try project-level runtime_config.json first
    if RUNTIME_CONFIG.exists():
        with open(RUNTIME_CONFIG, 'r') as f:
            rules = json.load(f)
    else:
        rules = {'targets': {}}  # Minimal stub

    return jsonify({
        'message': 'Regras geradas com sucesso (mock)',
        'rules': rules
    })


# ══════════════════════════════════════════════════════════════════════════════
# INFO ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/info/components', methods=['GET'])
def get_components():
    """
    Real backend: reads programa.json from workspace.
    Mock: reads programa.json from mocks dir.
    """
    fsm_data = load_mock('programa.json')
    if fsm_data is None:
        return jsonify({'error': 'Mock programa.json not found'}), 404
    return jsonify(derive_components(fsm_data))


@app.route('/api/info/snapshots', methods=['GET'])
def get_snapshots():
    """
    Real backend: lists output/ directory.
    Mock: lists _output.json files from MOCK_DIR.
    """
    return jsonify({'snapshots': list_snapshots()})


# ══════════════════════════════════════════════════════════════════════════════
# ENTRYPOINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print('=' * 60)
    print('🟡 P4SymTest MOCK Backend iniciado')
    print(f'   Mock files: {MOCK_DIR.resolve()}')
    print('   Servidor: http://localhost:5001')
    print('   (porta 5001 — real backend usa 5000)')
    print('=' * 60)
    app.run(debug=True, host='0.0.0.0', port=5001)
