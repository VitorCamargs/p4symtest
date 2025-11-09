#!/usr/bin/env python3
"""
Sistema de Cache para Execução de Tabelas

Otimiza execuções de tabelas identificando estados equivalentes que produzirão
o mesmo resultado simbólico, evitando processamento redundante.
"""

import json
import hashlib
from typing import List, Dict, Any, Tuple, Set
from collections import defaultdict
from pathlib import Path


class TableExecutionCache:
    """
    Cache inteligente para execução de tabelas P4.
    
    Identifica estados equivalentes do ponto de vista da tabela:
    - Mesmas constraints Z3 relevantes para a tabela
    - Mesmos field_updates relevantes para a tabela
    """
    
    def __init__(self, cache_file: Path = None):
        self.cache_file = cache_file
        self.cache: Dict[str, Dict] = {}
        self.hit_count = 0
        self.miss_count = 0
        self.table_relevant_fields: Dict[str, Set[Tuple[str, str]]] = {}
        
        if cache_file and cache_file.exists():
            self._load_cache()
    
    def _load_cache(self):
        """Carrega cache de execuções anteriores"""
        try:
            with open(self.cache_file, 'r') as f:
                data = json.load(f)
                self.cache = data.get('cache', {})
                self.table_relevant_fields = {
                    k: set(tuple(x) for x in v) 
                    for k, v in data.get('relevant_fields', {}).items()
                }
            print(f"[TableCache] Cache carregado: {len(self.cache)} entradas")
        except Exception as e:
            print(f"[TableCache] Erro ao carregar cache: {e}")
    
    def save_cache(self):
        """Salva cache em disco"""
        if not self.cache_file:
            return
        
        try:
            data = {
                'cache': self.cache,
                'relevant_fields': {
                    k: [list(x) for x in v] 
                    for k, v in self.table_relevant_fields.items()
                },
                'stats': {
                    'total_entries': len(self.cache),
                    'hit_count': self.hit_count,
                    'miss_count': self.miss_count,
                    'hit_rate': self.hit_count / max(1, self.hit_count + self.miss_count)
                }
            }
            
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            print(f"[TableCache] Cache salvo: {len(self.cache)} entradas")
        except Exception as e:
            print(f"[TableCache] Erro ao salvar cache: {e}")
    
    def _extract_relevant_fields(self, table_def: Dict, fsm_data: Dict) -> Set[Tuple[str, str]]:
        """
        Extrai campos relevantes para uma tabela:
        - Campos usados em match keys
        - Campos modificados por ações da tabela
        """
        relevant = set()
        
        # Campos de match
        for key in table_def.get('key', []):
            target = key.get('target')
            if target and len(target) >= 2:
                relevant.add(tuple(target[-2:]))  # (header, field)
        
        # Campos modificados por ações
        action_ids = set()
        for entry in table_def.get('entries', []):
            action_ids.add(entry.get('action_id'))
        action_ids.add(table_def.get('default_entry', {}).get('action_id'))
        
        for action in fsm_data.get('actions', []):
            if action.get('id') in action_ids:
                for prim in action.get('primitives', []):
                    op = prim.get('op')
                    params = prim.get('parameters', [])
                    
                    if op == 'assign' and len(params) >= 2:
                        dest = params[0]
                        if dest.get('type') == 'field':
                            dest_val = dest['value']
                            if len(dest_val) >= 2:
                                relevant.add(tuple(dest_val[-2:]))
                    
                    elif op == 'mark_to_drop':
                        relevant.add(('standard_metadata', 'egress_spec'))
        
        return relevant
    
    def _compute_table_state_hash(
        self, 
        state: Dict, 
        table_name: str,
        relevant_fields: Set[Tuple[str, str]]
    ) -> str:
        """
        Calcula hash baseado apenas nos campos relevantes para a tabela.
        """
        # Filtra constraints relevantes
        all_constraints = state.get('z3_constraints_smt2', [])
        relevant_constraints = []
        
        for constraint in all_constraints:
            # Verifica se a constraint menciona campos relevantes
            is_relevant = False
            for header, field in relevant_fields:
                if f"{header}.{field}" in constraint or f"{header}.$valid$" in constraint:
                    is_relevant = True
                    break
            
            if is_relevant:
                relevant_constraints.append(constraint)
        
        # Filtra field_updates relevantes
        field_updates = state.get('field_updates', {})
        relevant_updates = {}
        
        for field_str, expr in field_updates.items():
            parts = field_str.split('.')
            if len(parts) >= 2:
                field_key = tuple(parts[-2:])
                if field_key in relevant_fields:
                    relevant_updates[field_str] = expr
        
        # Cria estrutura determinística
        hash_data = {
            'table': table_name,
            'constraints': sorted(relevant_constraints),
            'updates': dict(sorted(relevant_updates.items()))
        }
        
        canonical = json.dumps(hash_data, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()
    
    def lookup(
        self, 
        state: Dict, 
        table_name: str,
        table_def: Dict,
        fsm_data: Dict
    ) -> Tuple[bool, Dict]:
        """
        Busca no cache se já existe resultado para este estado.
        
        Returns:
            (hit, cached_result)
        """
        # Extrai campos relevantes (com cache)
        if table_name not in self.table_relevant_fields:
            self.table_relevant_fields[table_name] = self._extract_relevant_fields(
                table_def, fsm_data
            )
        
        relevant_fields = self.table_relevant_fields[table_name]
        
        # Calcula hash
        state_hash = self._compute_table_state_hash(state, table_name, relevant_fields)
        
        # Busca no cache
        cache_key = f"{table_name}:{state_hash}"
        
        if cache_key in self.cache:
            self.hit_count += 1
            return True, self.cache[cache_key]
        else:
            self.miss_count += 1
            return False, {}
    
    def store(
        self,
        state: Dict,
        result: Dict,
        table_name: str,
        table_def: Dict,
        fsm_data: Dict
    ):
        """Armazena resultado no cache"""
        if table_name not in self.table_relevant_fields:
            self.table_relevant_fields[table_name] = self._extract_relevant_fields(
                table_def, fsm_data
            )
        
        relevant_fields = self.table_relevant_fields[table_name]
        state_hash = self._compute_table_state_hash(state, table_name, relevant_fields)
        cache_key = f"{table_name}:{state_hash}"
        
        # Armazena apenas o essencial
        cached_result = {
            'field_updates': result.get('field_updates', {}),
            'new_constraints': result.get('z3_constraints_smt2', [])
        }
        
        self.cache[cache_key] = cached_result
    
    def get_stats(self) -> Dict:
        """Retorna estatísticas do cache"""
        total = self.hit_count + self.miss_count
        return {
            'hits': self.hit_count,
            'misses': self.miss_count,
            'total_lookups': total,
            'hit_rate': self.hit_count / max(1, total),
            'cache_size': len(self.cache)
        }


def optimize_table_input(
    states: List[Dict],
    table_name: str,
    table_def: Dict,
    fsm_data: Dict,
    cache: TableExecutionCache
) -> Tuple[List[Dict], Dict[int, str]]:
    """
    Otimiza entrada de tabela removendo duplicatas.
    
    Returns:
        (unique_states, index_mapping)
        - unique_states: estados únicos para processar
        - index_mapping: {original_idx: hash} para reconstrução
    """
    print(f"\n[TableOptimizer] Otimizando entrada para '{table_name}'...")
    print(f"                 Estados originais: {len(states)}")
    
    # Extrai campos relevantes
    if table_name not in cache.table_relevant_fields:
        cache.table_relevant_fields[table_name] = cache._extract_relevant_fields(
            table_def, fsm_data
        )
    
    relevant_fields = cache.table_relevant_fields[table_name]
    
    # Agrupa por hash
    hash_to_states: Dict[str, List[int]] = defaultdict(list)
    hash_to_representative: Dict[str, int] = {}
    
    for idx, state in enumerate(states):
        state_hash = cache._compute_table_state_hash(state, table_name, relevant_fields)
        hash_to_states[state_hash].append(idx)
        
        if state_hash not in hash_to_representative:
            hash_to_representative[state_hash] = idx
    
    # Cria lista de estados únicos
    unique_states = []
    index_mapping = {}
    
    for state_hash, original_indices in hash_to_states.items():
        repr_idx = hash_to_representative[state_hash]
        unique_states.append(states[repr_idx])
        
        # Mapeia todos os índices originais para este hash
        for orig_idx in original_indices:
            index_mapping[orig_idx] = state_hash
    
    reduction = 1 - (len(unique_states) / len(states))
    print(f"[TableOptimizer] ✓ Otimização concluída:")
    print(f"                 {len(states)} → {len(unique_states)} estados")
    print(f"                 Redução: {reduction*100:.1f}%")
    print(f"                 Economia: {len(states) - len(unique_states)} execuções")
    
    return unique_states, index_mapping


def expand_table_results(
    results: List[Dict],
    original_states: List[Dict],
    index_mapping: Dict[int, str],
    hash_to_result_idx: Dict[str, int]
) -> List[Dict]:
    """
    Expande resultados da tabela para todos os estados originais.
    """
    print(f"\n[TableOptimizer] Expandindo {len(results)} resultados...")
    
    expanded = []
    
    for orig_idx, state in enumerate(original_states):
        state_hash = index_mapping.get(orig_idx)
        result_idx = hash_to_result_idx.get(state_hash)
        
        if result_idx is not None and result_idx < len(results):
            result = results[result_idx].copy()
            
            # Restaura metadados originais
            result['description'] = state.get('description', 'Unknown')
            result['history'] = state.get('history', [])
            
            # Adiciona info de otimização
            result['was_cached'] = False
            result['was_optimized'] = True
            
            expanded.append(result)
        else:
            # Fallback: mantém estado original
            expanded.append(state)
    
    print(f"[TableOptimizer] ✓ Expansão concluída: {len(expanded)} resultados")
    
    return expanded


# --- Exemplo de uso ---
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) != 5:
        print("Uso: python3 table_execution_cache.py <fsm.json> <table_name> <input_states.json> <cache.json>")
        sys.exit(1)
    
    fsm_file = Path(sys.argv[1])
    table_name = sys.argv[2]
    input_file = Path(sys.argv[3])
    cache_file = Path(sys.argv[4])
    
    # Carrega dados
    with open(fsm_file) as f:
        fsm_data = json.load(f)
    
    with open(input_file) as f:
        states = json.load(f)
    
    # Encontra definição da tabela
    ingress = next((p for p in fsm_data.get('pipelines', []) if p['name'] == 'ingress'), None)
    if not ingress:
        print("Pipeline ingress não encontrado")
        sys.exit(1)
    
    table_def = next((t for t in ingress.get('tables', []) if t['name'] == table_name), None)
    if not table_def:
        print(f"Tabela '{table_name}' não encontrada")
        sys.exit(1)
    
    # Inicializa cache
    cache = TableExecutionCache(cache_file)
    
    # Otimiza entrada
    unique_states, index_mapping = optimize_table_input(
        states, table_name, table_def, fsm_data, cache
    )
    
    print(f"\n[Info] Processar {len(unique_states)} estados únicos")
    print(f"[Info] Economizando {len(states) - len(unique_states)} execuções redundantes")
    
    # Salva cache
    cache.save_cache()
    
    print(f"\n[Stats] Cache: {cache.get_stats()}")