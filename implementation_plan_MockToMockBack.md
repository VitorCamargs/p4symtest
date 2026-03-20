# Mock Backend + Frontend API Integration

Create a Flask mock server that mirrors all real backend endpoints, returning existing
mock JSON files as responses. Then update the frontend to call this server via a
centralized API client instead of using static file imports.

---

## Proposed Changes

### Part 1 — Mock Backend

#### [NEW] [mock_server.py](file:///home/teste/Documents/symtest/p4symtest/mock_backend/mock_server.py)

Flask app at `http://localhost:5001` (port 5001 to avoid collision with real backend on 5000) that:

- Serves mock JSON from `../frontendV2/src/mocks/` relative directory
- Implements all 9 real endpoints with same request/response shape
- Route logic for `/api/analyze/table` and `/api/analyze/egress_table` selects the
  mock output using the same filename convention as the real backend:
  `{switch_id}_{table_name.replace('.','_')}_from_{stem(input_states)}_output.json`
- Routes:
  - `POST /api/upload/p4` → returns `{ message, fsm_data: programa.json }`
  - `POST /api/upload/json` → returns `{ message, type, filename }` (accepts, ignores)
  - `POST /api/analyze/parser` → returns `{ message, states: parser_states.json, parser_info, state_count, output_file: 'parser_states.json' }`
  - `POST /api/analyze/reachability` → returns mock reachability
  - `POST /api/generate/rules` → returns `{ message, rules: runtime_config.json }`
  - `POST /api/analyze/table` → looks up `{switch}_{table}_from_{input_stem}_output.json`
  - `POST /api/analyze/egress_table` → same lookup logic
  - `POST /api/analyze/deparser` → looks up `deparser_output_from_{input_stem}.json`
  - `GET /api/info/components` → derives components from [programa.json](file:///home/teste/Documents/symtest/p4symtest/frontendV2/src/mocks/programa.json)
  - `GET /api/info/snapshots` → returns list of `*_output.json` files in mocks dir

#### [NEW] [requirements.txt](file:///home/teste/Documents/symtest/p4symtest/mock_backend/requirements.txt)

```
Flask==3.0.0
flask-cors==4.0.0
```

---

### Part 2 — Frontend API Client

#### [NEW] src/lib/api.ts

Centralized fetch helpers, all using `BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:5001/api'`.

Functions:
- `uploadP4(file: File)` → `{ fsm_data }`
- `analyzeParser()` → `{ states, output_file }`
- `analyzeTable(table_name, switch_id, input_states)` → `{ output_states, output_file }`
- `analyzeEgressTable(table_name, switch_id, input_states)` → `{ output_states, output_file }`
- `analyzeDeparser(input_states)` → `{ analysis_results, output_file }`
- `getComponents()` → components object
- `getSnapshots()` → `{ snapshots }`
- `generateRules()` → `{ rules }`

---

### Part 3 — Frontend Component Updates

#### [MODIFY] [App.tsx](file:///home/teste/Documents/symtest/p4symtest/frontendV2/src/App.tsx)

Add `lastOutputFile: string | null` state. Pass it down to [CenterPanel](file:///home/teste/Documents/symtest/p4symtest/frontendV2/src/components/CenterPanel.tsx#6-160) and [RightPanel](file:///home/teste/Documents/symtest/p4symtest/frontendV2/src/components/RightPanel.tsx#252-345).
[CenterPanel](file:///home/teste/Documents/symtest/p4symtest/frontendV2/src/components/CenterPanel.tsx#6-160) sets it from API responses; [RightPanel](file:///home/teste/Documents/symtest/p4symtest/frontendV2/src/components/RightPanel.tsx#252-345) reads results passed as a prop.

#### [MODIFY] [CenterPanel.tsx](file:///home/teste/Documents/symtest/p4symtest/frontendV2/src/components/CenterPanel.tsx)

- [handleCompile](file:///home/teste/Documents/symtest/p4symtest/frontendV2/src/components/CenterPanel.tsx#14-18): read P4 content from editor as a `Blob/File`, call `uploadP4()`, use response as `compiledData`
- [handleVerifyNode](file:///home/teste/Documents/symtest/p4symtest/frontendV2/src/components/CenterPanel.tsx#19-30): distinguish pipeline name (`ingress` vs [egress](file:///home/teste/Documents/symtest/p4symtest/backend/app.py#408-463)) to call `analyzeTable` vs `analyzeEgressTable`; for parser call `analyzeParser()`; for deparser call `analyzeDeparser()`
- Accept `lastOutputFile` and `setLastOutputFile` props; pass `lastOutputFile` as `input_states`; call `setLastOutputFile(result.output_file)` after each analysis
- Pass `verificationResult` (the raw API response) up to parent or into a new prop consumed by [RightPanel](file:///home/teste/Documents/symtest/p4symtest/frontendV2/src/components/RightPanel.tsx#252-345)

#### [MODIFY] [RightPanel.tsx](file:///home/teste/Documents/symtest/p4symtest/frontendV2/src/components/RightPanel.tsx)

- Accept `verificationResult: any` prop instead of selecting mocks internally
- Remove all `mockData` imports and mock selection logic
- Use `verificationResult` to render paths (the shape is already identical to the mocks)
- Keep all existing [PathItem](file:///home/teste/Documents/symtest/p4symtest/frontendV2/src/components/RightPanel.tsx#6-147), [FieldUpdatesView](file:///home/teste/Documents/symtest/p4symtest/frontendV2/src/components/RightPanel.tsx#148-199), [Z3ConstraintsView](file:///home/teste/Documents/symtest/p4symtest/frontendV2/src/components/RightPanel.tsx#208-247) rendering untouched

---

## Verification Plan

### Automated Tests

None currently exist in the project. No tests will be invented.

### Manual Verification

1. **Start the mock server** (see run instructions in notify_user):
   ```bash
   cd mock_backend && python mock_server.py
   ```
2. **Start the frontend**:
   ```bash
   cd frontendV2 && npm run dev
   ```
3. Open `http://localhost:5173` in the browser.
4. Click **"Compile Program"** → the Compiled Structures panel should populate with parsers/pipelines/deparsers (same as before, but now from the API).
5. Click **"Verify"** on [parser](file:///home/teste/Documents/symtest/p4symtest/backend/app.py#160-188) → Right panel should show 4 parser state paths.
6. Click **"Verify"** on `MyIngress.ipv4_lpm` → Right panel should update with ipv4_lpm output paths.
7. Click **"Verify"** on `MyEgress.egress_port_smac` → Right panel should update with egress paths.
8. Click **"Verify"** on [deparser](file:///home/teste/Documents/symtest/p4symtest/backend/app.py#468-507) → Right panel should update with deparser paths.
9. Check browser DevTools **Network tab** — all requests should go to `http://localhost:5001/api/...` and return 200.
