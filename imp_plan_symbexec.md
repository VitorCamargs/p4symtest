# Dynamic Control‑Plane Configuration & Symbolic Hit/Miss Testing

## Goal
Two **independent** modes for feeding the verifier, selectable via a toggle in the existing **Network Configuration** modal:

1. **Routing Mode** – The user fills in routing entries for every table defined in the P4 program. The [NetworkConfigModal](file:///home/teste/Documents/symtest/p4symtest/frontendV2/src/components/NetworkConfigModal.tsx#224-302) generates the forms dynamically from the `table_schema` returned by the backend (instead of the current hard‑coded `ipv4_lpm` / `myTunnel_exact` / `egress_port_smac`). The result is written to [runtime_config.json](file:///home/teste/Documents/symtest/p4symtest/runtime_config.json) locally and passed to the verifier.

2. **Symbolic Mode** – The user *does not* fill in any routing entry. The verifier automatically branches each table into its possible outcomes: **Miss** (default action) and **Hit** (each available non‑default action, with symbolic parameters). No [runtime_config.json](file:///home/teste/Documents/symtest/p4symtest/runtime_config.json) is needed.

---
## Proposed Changes

### Backend ([mock_server.py](file:///home/teste/Documents/symtest/p4symtest/mock_backend/mock_server.py))

#### [MODIFY] `/api/compiledData`
Extend the response per table with a `table_schema` object:
```json
{
  "name": "ipv4_acl",
  "keys": [
    {"field": "hdr.ipv4.srcAddr", "match_type": "ternary"},
    {"field": "hdr.ipv4.dstAddr", "match_type": "ternary"}
  ],
  "actions": ["set_class", "NoAction"],
  "default_action": "NoAction"
}
```

#### [MODIFY] Verification endpoint
- Accept a flag `symbolic_mode: boolean` alongside the existing `runtime_config` payload.
- If `symbolic_mode = true`, ignore routing entries and produce one result set per table per action (hit branches) plus the miss branch.
- If `symbolic_mode = false`, apply routing entries as today.

---
### Frontend (React)

#### [MODIFY] [NetworkConfigModal.tsx](file:///home/teste/Documents/symtest/p4symtest/frontendV2/src/components/NetworkConfigModal.tsx) – Dynamic Form Generation
- Remove hard‑coded [Ipv4Table](file:///home/teste/Documents/symtest/p4symtest/frontendV2/src/components/NetworkConfigModal.tsx#51-81), [TunnelTable](file:///home/teste/Documents/symtest/p4symtest/frontendV2/src/components/NetworkConfigModal.tsx#82-109), [EgressTable](file:///home/teste/Documents/symtest/p4symtest/frontendV2/src/components/NetworkConfigModal.tsx#110-137) sub‑components.
- Read `compiledData.table_schema` (already fetched in [App.tsx](file:///home/teste/Documents/symtest/p4symtest/frontendV2/src/App.tsx)) and **dynamically render one collapsible section per table**.
- Each section shows one row per key (respecting `match_type`: exact → text input, ternary → value + mask, lpm → IP + prefix length).
- Action dropdown per row populated from `actions`.

#### [ADD] Toggle "Routing Mode / Symbolic Mode"
- A prominent toggle in the modal header.
- When **Symbolic Mode** is selected, the routing‑entry forms are greyed out / hidden and a banner explains that the verifier will explore all hit/miss branches automatically.

#### [MODIFY] [RightPanel.tsx](file:///home/teste/Documents/symtest/p4symtest/frontendV2/src/components/RightPanel.tsx) – Hit/Miss Visualisation (Symbolic Mode)
- When the response contains symbolically‑generated branches, display a **"Hit: `action_name`"** badge and a **"Miss: `default_action`"** badge on each path row.
- The existing matrix view continues to work for concrete (Routing Mode) updates.

---
### Shared Types ([src/lib/api.ts](file:///home/teste/Documents/symtest/p4symtest/frontendV2/src/lib/api.ts))
```ts
export interface TableSchema {
  name: string;
  keys: Array<{field: string; match_type: string}>;
  actions: string[];
  default_action: string;
}
// Extended CompiledData already includes pipelines; add table_schema per table entry
```

---
## Verification Plan

### Manual
1. Open **Network Configuration** modal with [custom_test.p4](file:///home/teste/Documents/symtest/p4symtest/backend/workspace/custom_test.p4) loaded.
2. Verify that forms for `ipv4_lpm`, `ipv4_acl`, `tcp_exact` and `egress_port_smac` appear automatically (no `myTunnel_exact`).
3. Fill in a concrete rule for `ipv4_acl` (Routing Mode) → click Verify → RightPanel shows field updates for that path.
4. Switch to **Symbolic Mode** → click Verify → RightPanel shows labelled **Hit** and **Miss** paths for every table, including `ipv4_acl` and `tcp_exact`.
