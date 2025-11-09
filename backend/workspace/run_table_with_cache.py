#!/usr/bin/env python3
"""
Wrapper com Cache para run_table.py

Intercepta execuções de tabelas, usa cache para evitar processamento redundante.
"""

import json
import sys
import subprocess
from pathlib import Path
from table_execution_cache import TableExecutionCache, optimize_table_input, expand_table_results


def run_table_with_cache(
    fsm_file: Path,
    topology_file: Path,
    runtime_file: Path,
    input_states_file: Path,
    switch_id: str,
    table_name: str,
    output_states_file: Path,
    cache_file: Path,
    run_table_script: Path
):
    """
    Executa run_table.py com cache inteligente.
    """
    print(f"\n{'='*70}")
    print(f"RUN_TABLE COM CACHE: {table_name}")
    print(f"{'='*70}")
    
    # Carrega dados
    with open(fsm_file) as f:
        fsm_data = json.load(f)
    
    with open(input_states_file) as f:
        original_states = json.load(f)
    
    if not original_states:
        print("[Cache] Nenhum estado de entrada, pulando.")
        with open(output_states_file, 'w') as f:
            json.dump([], f)
        return
    
    # Encontra definição da tabela
    pipeline_name = 'ingress' if 'ingress' in table_name.lower() else 'egress'
    pipeline = next((p for p in fsm_data.get('pipelines', []) if p['name'] == pipeline_name), None)
    
    if not pipeline:
        print(f"[Cache] Pipeline '{pipeline_name}' não encontrado, executando sem cache")
        _run_original_table(run_table_script, fsm_file, topology_file, runtime_file,
                           input_states_file, switch_id, table_name, output_states_file)
        return
    
    table_def = next((t for t in pipeline.get('tables', []) if t['name'] == table_name), None)
    
    if not table_def:
        print(f"[Cache] Tabela '{table_name}' não encontrada, executando sem cache")
        _run_original_table(run_table_script, fsm_file, topology_file, runtime_file,
                           input_states_file, switch_id, table_name, output_states_file)
        return
    
    # Inicializa cache
    cache = TableExecutionCache(cache_file)
    
    # Fase 1: Verificar cache completo
    print(f"\n[Fase 1] Verificando cache...")
    cached_results = []
    states_to_process = []
    cache_mapping = {}  # {original_idx: cache_result}
    
    for idx, state in enumerate(original_states):
        hit, cached_result = cache.lookup(state, table_name, table_def, fsm_data)
        
        if hit:
            cached_results.append((idx, cached_result))
        else:
            states_to_process.append((idx, state))
    
    print(f"[Cache] Hits: {len(cached_results)}/{len(original_states)}")
    print(f"[Cache] A processar: {len(states_to_process)}")
    
    # Se todos estão em cache, retorna direto
    if not states_to_process:
        print("[Cache] ✓ Todos os estados em cache!")
        final_results = _build_results_from_cache(original_states, cached_results)
        with open(output_states_file, 'w') as f:
            json.dump(final_results, f, indent=2)
        cache.save_cache()
        return
    
    # Fase 2: Otimizar estados que precisam ser processados
    print(f"\n[Fase 2] Otimizando estados para processamento...")
    states_only = [s for _, s in states_to_process]
    unique_states, index_mapping = optimize_table_input(
        states_only, table_name, table_def, fsm_data, cache
    )
    
    # Fase 3: Processar estados únicos
    print(f"\n[Fase 3] Processando {len(unique_states)} estados únicos...")
    
    # Salva estados únicos em arquivo temporário
    temp_input = input_states_file.parent / f".temp_input_{table_name}_{input_states_file.name}"
    with open(temp_input, 'w') as f:
        json.dump(unique_states, f, indent=2)
    
    # Executa run_table.py original
    temp_output = output_states_file.parent / f".temp_output_{table_name}_{output_states_file.name}"
    
    success = _run_original_table(
        run_table_script, fsm_file, topology_file, runtime_file,
        temp_input, switch_id, table_name, temp_output
    )
    
    if not success:
        print("[Cache] Erro na execução, limpando temporários")
        temp_input.unlink(missing_ok=True)
        temp_output.unlink(missing_ok=True)
        return
    
    # Carrega resultados processados
    with open(temp_output) as f:
        processed_results = json.load(f)
    
    # Fase 4: Atualizar cache com novos resultados
    print(f"\n[Fase 4] Atualizando cache...")
    hash_to_result = {}
    
    for idx, state in enumerate(unique_states):
        if idx < len(processed_results):
            result = processed_results[idx]
            state_hash = cache._compute_table_state_hash(
                state, table_name, cache.table_relevant_fields[table_name]
            )
            hash_to_result[state_hash] = result
            
            # Armazena no cache
            cache.store(state, result, table_name, table_def, fsm_data)
    
    print(f"[Cache] {len(hash_to_result)} novos resultados armazenados")
    
    # Fase 5: Expandir resultados
    print(f"\n[Fase 5] Expandindo resultados...")
    
    # Reconstrói mapeamento completo
    full_results = []
    processed_idx_map = {states_to_process[i][0]: i for i in range(len(states_to_process))}
    
    for orig_idx, state in enumerate(original_states):
        # Verifica se estava em cache
        cached = next((r for i, r in cached_results if i == orig_idx), None)
        
        if cached:
            # Usa resultado do cache
            result = _apply_cached_result(state, cached, table_name)
            result['was_cached'] = True
        else:
            # Usa resultado processado
            proc_idx = processed_idx_map.get(orig_idx)
            if proc_idx is not None:
                state_hash = index_mapping.get(proc_idx)
                result = hash_to_result.get(state_hash)
                
                if result:
                    result = result.copy()
                    result['description'] = state.get('description', 'Unknown')
                    result['history'] = result.get('history', state.get('history', []))
                    result['was_cached'] = False
                else:
                    result = state  # Fallback
            else:
                result = state  # Fallback
        
        full_results.append(result)
    
    # Salva resultado final
    with open(output_states_file, 'w') as f:
        json.dump(full_results, f, indent=2)
    
    # Limpa temporários
    temp_input.unlink(missing_ok=True)
    temp_output.unlink(missing_ok=True)
    
    # Salva cache
    cache.save_cache()
    
    # Estatísticas
    stats = cache.get_stats()
    print(f"\n{'='*70}")
    print(f"ESTATÍSTICAS DO CACHE:")
    print(f"  Hits: {stats['hits']}")
    print(f"  Misses: {stats['misses']}")
    print(f"  Hit Rate: {stats['hit_rate']*100:.1f}%")
    print(f"  Tamanho do Cache: {stats['cache_size']} entradas")
    print(f"{'='*70}\n")


def _run_original_table(script, fsm, topo, runtime, input_f, sw, table, output_f):
    """Executa run_table.py original"""
    cmd = [
        "python3", str(script),
        str(fsm), str(topo), str(runtime),
        str(input_f), sw, table, str(output_f)
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        if result.returncode != 0:
            print(f"[Erro] run_table.py falhou:")
            print(result.stderr)
            return False
        
        return True
    except subprocess.TimeoutExpired:
        print("[Erro] Timeout na execução de run_table.py")
        return False
    except Exception as e:
        print(f"[Erro] Exceção ao executar run_table.py: {e}")
        return False


def _build_results_from_cache(original_states, cached_results):
    """Constrói resultados finais apenas do cache"""
    results = []
    cache_map = {idx: res for idx, res in cached_results}
    
    for idx, state in enumerate(original_states):
        cached = cache_map.get(idx)
        if cached:
            result = _apply_cached_result(state, cached, "table")
            result['was_cached'] = True
            results.append(result)
        else:
            results.append(state)
    
    return results


def _apply_cached_result(state, cached_result, table_name):
    """Aplica resultado do cache a um estado"""
    result = state.copy()
    
    # Atualiza com dados do cache
    result['field_updates'] = cached_result.get('field_updates', result.get('field_updates', {}))
    result['z3_constraints_smt2'] = cached_result.get('new_constraints', result.get('z3_constraints_smt2', []))
    
    # Atualiza history se não existir
    if 'history' not in result:
        result['history'] = []
    
    if table_name not in str(result.get('history', [])):
        result['history'] = result['history'] + [table_name]
    
    return result


if __name__ == "__main__":
    if len(sys.argv) != 9:
        print("Uso: python3 run_table_with_cache.py <fsm.json> <topology.json> <runtime.json> "
              "<input_states.json> <switch_id> <table_name> <output_states.json> <cache.json>")
        sys.exit(1)
    
    fsm_file = Path(sys.argv[1])
    topology_file = Path(sys.argv[2])
    runtime_file = Path(sys.argv[3])
    input_states_file = Path(sys.argv[4])
    switch_id = sys.argv[5]
    table_name = sys.argv[6]
    output_states_file = Path(sys.argv[7])
    cache_file = Path(sys.argv[8])
    
    # Assume que run_table.py está no mesmo diretório
    run_table_script = Path(__file__).parent / "run_table.py"
    
    if not run_table_script.exists():
        print(f"Erro: run_table.py não encontrado em {run_table_script}")
        sys.exit(1)
    
    run_table_with_cache(
        fsm_file, topology_file, runtime_file,
        input_states_file, switch_id, table_name,
        output_states_file, cache_file, run_table_script
    )