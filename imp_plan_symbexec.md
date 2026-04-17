# Plano de Implementação — Execução Híbrida (Frontend V2 + Backend Real)

## Objetivo

Alinhar a execução com o artigo: priorizar regras concretas injetadas por mini-topology, com fallback simbólico apenas onde não há valor concreto disponível.

## Modelo funcional acordado

1. Modo padrão: `auto_concrete`.
2. Fallback por campo: quando um valor não é definido concretamente, usar simbólico.
3. Modo alternativo: `full_symbolic` (força campos de match e parâmetros para simbólico).
4. Override manual: usuário pode trocar qualquer campo simbólico para concreto no modal de configuração.

## Estratégia técnica adotada

1. Frontend V2 mantém configuração de topologia e tabelas por switch.
2. Antes de verificar tabela (ingress/egress), V2 sincroniza automaticamente com backend real:
- `topology.json` via `POST /api/upload/json` (`type=topology`)
- `runtime_config.json` via `POST /api/upload/json` (`type=runtime_config`)
3. `runtime_config` usa marcador `__symbolic__` para campos não concretizados.
4. Scripts de execução no backend (`run_table.py`, `run_table_egress.py`) tratam `__symbolic__` (e vazio/symbolic) como variável Z3, sem fallback silencioso para `0`.

## Semântica por modo

### `auto_concrete`

1. Auto-população tenta preencher concretamente com base na topologia.
2. Campos vazios/indefinidos viram `__symbolic__` no payload sincronizado.
3. No backend, parâmetros de ação ausentes/simbólicos geram `BitVec` fresco.

### `full_symbolic`

1. Frontend converte os valores de match para `__symbolic__`.
2. Frontend remove parâmetros concretos de ação no upload.
3. Backend cria variáveis simbólicas para parâmetros runtime usados pelas ações.

## Status atual nesta branch

1. `NetworkConfigModal` agora expõe seletor de modo de execução (`auto_concrete` / `full_symbolic`).
2. `LeftPanel` propaga a configuração atual para o `App`.
3. `CenterPanel` sincroniza configuração no backend real antes de rodar análise de tabela.
4. `api.ts` converte `TopologyConfig` da V2 para formatos de `topology.json` e `runtime_config.json` aceitos pelo backend.
5. `run_table.py` e `run_table_egress.py` atualizados para fallback simbólico explícito (incluindo matchs/params simbólicos).

## Validação mínima esperada

1. Compilar P4.
2. Rodar parser.
3. Verificar tabela em `auto_concrete` com pelo menos um campo vazio (deve virar simbólico, não zero).
4. Alternar para `full_symbolic` e repetir verificação.
5. Ajustar manualmente um campo simbólico para concreto e confirmar alteração no comportamento.
