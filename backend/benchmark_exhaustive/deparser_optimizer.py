#!/usr/bin/env python3
"""
Otimizador de Estados para Deparser

Une estados equivalentes (mesmas constraints Z3 e field_updates) antes do deparser,
depois expande os resultados para todos os caminhos originais.
"""

import json
import hashlib
from typing import List, Dict, Any, Tuple
from collections import defaultdict
from pathlib import Path


class DeparserStateOptimizer:
    """Une estados equivalentes do ponto de vista do deparser"""
    
    def __init__(self):
        self.state_groups: Dict[str, List[Dict]] = defaultdict(list)
        self.representative_states: List[Dict] = []
        self.hash_to_indices: Dict[str, List[int]] = defaultdict(list)
    
    def _compute_deparser_hash(self, state: Dict) -> str:
        """
        Hash baseado apenas em:
        - z3_constraints_smt2 (validade dos headers)
        - field_updates (valores dos campos)
        
        Ignora: history, description, metadados
        """
        relevant_data = {
            'z3_constraints_smt2': sorted(state.get('z3_constraints_smt2', [])),
            'field_updates': dict(sorted(state.get('field_updates', {}).items()))
        }
        canonical_json = json.dumps(relevant_data, sort_keys=True)
        return hashlib.sha256(canonical_json.encode()).hexdigest()
    
    def optimize_states(self, states: List[Dict]) -> Tuple[List[Dict], Dict[str, Any]]:
        """
        Agrupa estados por equivalência e retorna representantes únicos.
        
        Returns: (estados_representativos, mapa_de_otimização)
        """
        print(f"\n[Optimizer] Iniciando otimização de {len(states)} estados...")
        
        # Agrupa por hash
        for idx, state in enumerate(states):
            state_hash = self._compute_deparser_hash(state)
            self.hash_to_indices[state_hash].append(idx)
            self.state_groups[state_hash].append(state)
        
        # Cria representantes
        for state_hash, group in self.state_groups.items():
            representative = group[0].copy()
            representative['_optimizer_hash'] = state_hash
            representative['_original_indices'] = self.hash_to_indices[state_hash]
            representative['_group_size'] = len(group)
            
            if len(group) > 1:
                representative['description'] = f"[MERGED {len(group)} states]"
            
            self.representative_states.append(representative)
        
        optimization_map = {
            'original_count': len(states),
            'optimized_count': len(self.representative_states),
            'reduction_ratio': 1 - (len(self.representative_states) / len(states)),
            'hash_to_indices': dict(self.hash_to_indices),
            'original_states': states,
            'representative_states': self.representative_states
        }
        
        reduction_pct = optimization_map['reduction_ratio'] * 100
        saved_states = len(states) - len(self.representative_states)
        
        print(f"[Optimizer] ✓ Otimização concluída:")
        print(f"            {len(states)} → {len(self.representative_states)} estados")
        print(f"            Redução: {reduction_pct:.1f}%")
        print(f"            Economia: {saved_states} estados")
        
        return self.representative_states, optimization_map
    
    def expand_results(self, deparser_results: List[Dict], 
                      optimization_map: Dict[str, Any]) -> List[Dict]:
        """
        Expande resultados do deparser para todos os estados originais,
        restaurando history e metadados de cada caminho.
        """
        print(f"\n[Optimizer] Expandindo {len(deparser_results)} resultados...")
        
        original_states = optimization_map['original_states']
        hash_to_indices = optimization_map['hash_to_indices']
        representative_states = optimization_map.get('representative_states', [])
        expanded_results = []
        
        for result in deparser_results:
            optimizer_hash = result.get('_optimizer_hash')
            original_indices = result.get('_original_indices')
            
            # Fallback: tenta recuperar do input_state_index
            if not optimizer_hash:
                input_idx = result.get('input_state_index', -1)
                if 0 <= input_idx < len(representative_states):
                    rep_state = representative_states[input_idx]
                    optimizer_hash = rep_state.get('_optimizer_hash')
                    original_indices = rep_state.get('_original_indices')
            
            if not optimizer_hash or not original_indices:
                expanded_results.append(result)
                continue
            
            # Cria resultado para cada estado original
            for orig_idx in original_indices:
                if orig_idx >= len(original_states):
                    continue
                    
                original_state = original_states[orig_idx]
                expanded_result = result.copy()
                
                # Restaura metadados originais
                expanded_result['input_state'] = original_state.get('description', f'State {orig_idx}')
                expanded_result['input_state_index'] = orig_idx
                expanded_result['history'] = original_state.get('history', [])
                
                # Remove metadados de otimização
                for key in ['_optimizer_hash', '_original_indices', '_group_size']:
                    expanded_result.pop(key, None)
                
                expanded_result['was_optimized'] = True
                expanded_result['optimization_group_size'] = len(original_indices)
                
                expanded_results.append(expanded_result)
        
        print(f"[Optimizer] ✓ Expansão concluída:")
        print(f"            {len(deparser_results)} → {len(expanded_results)} resultados")
        print(f"            Todos os caminhos originais restaurados")
        
        return expanded_results


def optimize_and_process_deparser(all_final_states: List[Dict], 
                                  work_dir: Path,
                                  run_num: int) -> Tuple[Path, Dict[str, Any]]:
    """
    Helper: otimiza estados e salva arquivo para o deparser.
    
    Returns: (caminho_arquivo_otimizado, mapa_de_otimização)
    """
    optimizer = DeparserStateOptimizer()
    optimized_states, opt_map = optimizer.optimize_states(all_final_states)
    
    # Salva estados otimizados
    optimized_file = work_dir / f"run{run_num}_final_states_optimized.json"
    with open(optimized_file, 'w') as f:
        json.dump(optimized_states, f, indent=2)
    
    # Salva mapa (sem estados originais para economizar espaço)
    opt_map_save = opt_map.copy()
    opt_map_save.pop('original_states', None)
    opt_map_save.pop('representative_states', None)
    
    opt_map_file = work_dir / f"run{run_num}_optimization_map.json"
    with open(opt_map_file, 'w') as f:
        json.dump(opt_map_save, f, indent=2)
    
    print(f"[Optimizer] Arquivos salvos:")
    print(f"            - Estados otimizados: {optimized_file}")
    print(f"            - Mapa de otimização: {opt_map_file}")
    
    return optimized_file, opt_map


def expand_deparser_results(deparser_output_file: Path,
                            optimization_map: Dict[str, Any],
                            work_dir: Path,
                            run_num: int) -> Path:
    """
    Helper: expande resultados do deparser para todos os caminhos.
    
    Returns: caminho_arquivo_expandido
    """
    with open(deparser_output_file, 'r') as f:
        deparser_results = json.load(f)
    
    optimizer = DeparserStateOptimizer()
    expanded_results = optimizer.expand_results(deparser_results, optimization_map)
    
    expanded_file = work_dir / f"run{run_num}_deparser_expanded.json"
    with open(expanded_file, 'w') as f:
        json.dump(expanded_results, f, indent=2)
    
    print(f"[Optimizer] Resultados expandidos salvos: {expanded_file}")
    
    return expanded_file


# --- Exemplo de uso standalone ---
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) != 4:
        print("Uso: python3 deparser_optimizer.py <input_states.json> <deparser_results.json> <output_expanded.json>")
        sys.exit(1)
    
    input_file = Path(sys.argv[1])
    deparser_file = Path(sys.argv[2])
    output_file = Path(sys.argv[3])
    
    # Carrega estados originais
    with open(input_file, 'r') as f:
        original_states = json.load(f)
    
    # Otimiza
    optimizer = DeparserStateOptimizer()
    optimized_states, opt_map = optimizer.optimize_states(original_states)
    
    print(f"\n[Info] Estados otimizados salvos temporariamente para processamento...")
    
    # Carrega resultados do deparser
    with open(deparser_file, 'r') as f:
        deparser_results = json.load(f)
    
    # Expande
    expanded_results = optimizer.expand_results(deparser_results, opt_map)
    
    # Salva
    with open(output_file, 'w') as f:
        json.dump(expanded_results, f, indent=2)
    
    print(f"\n[Success] Resultados expandidos salvos em: {output_file}")