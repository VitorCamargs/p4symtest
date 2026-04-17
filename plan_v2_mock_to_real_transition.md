# Plano de Transição — Frontend V2 do Mock para Backend Real

## Objetivo

Conectar o `frontendV2` ao backend real como padrão, preservando fallback para mock apenas quando explicitamente necessário.

## Status Atual (branch `codex/v2-real-backend-transition`)

1. Fase 1 concluída:
- `table_schemas` no backend real (`/api/info/components`).
- endpoint de compatibilidade `/api/mock/source`.

2. Fase 2 concluída:
- V2 aponta para backend real por padrão (`VITE_API_URL`/`VITE_API_MODE`).
- `scenario` só é anexado quando modo mock.

3. Fase 3 concluída:
- Compose com `frontend` em modo real.
- `mock-backend` disponível por profile.

4. Fase 4 iniciada:
- V2 sincroniza `topology.json` e `runtime_config.json` antes de rodar tabela.
- parser no backend real corrigido para chamar `run_parser.py` com `fsm + output`.
- fallback simbólico por campo implementado em `run_table.py` e `run_table_egress.py`.

---

## Diferenças já identificadas (Mock x Real)

1. `GET /api/info/components`
- Mock já expõe `table_schemas`.
- Real não expunha `table_schemas` (bloqueava formulários dinâmicos no modal).

2. `GET /api/mock/source`
- Mock já expõe para auto-carga em dev.
- Real não expunha endpoint compatível.

3. Cliente API V2
- URL padrão ainda era `localhost:5001` (mock).
- Query `scenario` era enviada em todas as requisições, inclusive modo real.

4. Docker
- Sem separação explícita de modo (`real` vs `mock`) no frontend.
- Sem serviço mock opcional por profile.

---

## Estratégia

### Fase 1 — Paridade mínima de contrato no backend real

1. Adicionar `table_schemas` em `/api/info/components` no backend real.
2. Adicionar endpoint de compatibilidade `/api/mock/source` no backend real.
3. Validar que o compile da V2 recebe schema dinâmico sem depender do mock.

### Fase 2 — Conexão padrão da V2 no backend real

1. Mudar default da API para `http://localhost:5000/api`.
2. Introduzir `VITE_API_MODE` (`real`|`mock`).
3. Enviar `scenario` somente quando `API_MODE=mock`.
4. Mostrar controles de cenário mock apenas quando em modo mock.

### Fase 3 — Docker operacional para transição

1. Definir frontend com:
- `VITE_API_URL=http://backend:5000/api`
- `VITE_API_MODE=real`
2. Garantir `depends_on` do frontend com healthcheck do backend.
3. Incluir serviço `mock-backend` opcional via `profiles: ["mock"]`.

### Fase 4 — Migração funcional progressiva

1. Confirmar fluxo base no real:
- Compile
- Analyze parser
- Analyze table/egress/deparser
2. Em seguida migrar a configuração de rede/tabelas para payload real de verify.
3. Por último ativar modos de execução:
- `auto_concrete` (padrão)
- `full_symbolic`

---

## Comandos Operacionais

### Subir modo real (padrão)

```bash
docker compose up -d --build backend frontend
```

Se a porta `5000` já estiver ocupada no host:

```bash
BACKEND_HOST_PORT=5002 docker compose up -d --build backend frontend
```

### Subir mock opcional (quando necessário)

```bash
docker compose --profile mock up -d --build mock-backend
```

---

## Critérios de aceite da transição inicial

1. `frontendV2` sobe e chama backend real por padrão.
2. Modal de configuração carrega tabelas dinâmicas usando `table_schemas` do backend real.
3. Requisições no modo real não enviam `scenario`.
4. Mock permanece disponível apenas sob profile explícito.
