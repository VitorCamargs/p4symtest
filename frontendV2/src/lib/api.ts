// api.ts — Centralized API client for P4SymTest
// All requests go to VITE_API_URL (defaults to real backend at localhost:5000)

const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:5000/api';
const API_MODE = ((import.meta.env.VITE_API_MODE as string | undefined) ?? '').toLowerCase();

const MOCK_API =
  API_MODE === 'mock' ||
  (!API_MODE && (BASE_URL.includes('localhost:5001') || BASE_URL.includes('/5001')));

export const isMockApi = () => MOCK_API;
const SYMBOLIC_MARKER = '__symbolic__';
const SYMBOLIC_TOKENS = new Set(['', 'symbolic', 'sym', '__symbolic__', '*', 'auto', 'default']);

let currentScenario = localStorage.getItem('p4scenario') || 'default';
export const setApiScenario = (s: string) => {
  currentScenario = s;
  localStorage.setItem('p4scenario', s);
};
export const getApiScenario = () => currentScenario;

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const target = isMockApi()
    ? `${BASE_URL}${path}${path.includes('?') ? '&' : '?'}scenario=${currentScenario}`
    : `${BASE_URL}${path}`;
  const res = await fetch(target, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(body.error ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ── Shared Types ─────────────────────────────────────────────────────────────

export interface SourceInfo {
  filename: string;
  line: number;
  column: number;
  source_fragment: string;
}

export interface TableKey {
  field: string;
  target: [string, string];
  match_type: 'exact' | 'lpm' | 'ternary' | 'range';
}

export interface TableActionParam {
  name: string;
  bitwidth: number;
}

export interface TableAction {
  name: string;
  params: TableActionParam[];
}

export interface TableSchema {
  name: string;
  keys: TableKey[];
  actions: TableAction[];
  default_action: string;
}

export type TableWarningType =
  | 'unreachable_table'
  | 'unexpected_drop'
  | 'rule_shadowing'
  | 'missing_runtime_entry'
  | 'unexpected_field_update'
  | 'no_effect_action'
  | 'parser_table_mismatch'
  | 'deparser_invalid_header'
  | 'egress_spec_conflict';

export type TableWarningSeverity = 'info' | 'low' | 'medium' | 'high';
export type TableWarningSource = 'deterministic' | 'llm_hypothesis';
export type TableWarningEvidenceSource =
  | 'symbolic_fact'
  | 'p4_slice'
  | 'runtime'
  | 'topology'
  | 'snapshot_summary'
  | 'log_summary'
  | 'rag_chunk';

export interface TableWarningEvidence {
  id: string;
  source: TableWarningEvidenceSource;
  summary: string;
  location?: string;
}

export interface TableWarning {
  type: TableWarningType;
  severity: TableWarningSeverity;
  confidence: number;
  source: TableWarningSource;
  evidence_ids: string[];
  explanation: string;
  suggested_action: string;
}

export interface TableWarningModelInfo {
  provider: string;
  model: string;
  prompt_version: string;
}

export interface TableWarningDiagnostics {
  diagnostics_version: string;
  table_name: string;
  expected_behavior: string;
  observed_behavior: string;
  inconclusive: boolean;
  warnings: TableWarning[];
  evidence: TableWarningEvidence[];
  model_info: TableWarningModelInfo;
  rag_context_ids: string[];
}

export interface TableDiagnosticsUnavailable {
  diagnostics_unavailable: true;
  table_name?: string;
  reason?: string;
  message?: string;
}

export type TableDiagnostics = TableWarningDiagnostics | TableDiagnosticsUnavailable;
export type TableOutputStates = any[] & { diagnostics?: TableDiagnostics };

// ── Upload ────────────────────────────────────────────────────────────────────

export interface UploadP4Result {
  message: string;
  fsm_data: any; // full programa.json structure
}

/** Upload a P4 source file (or Blob of editor content) for compilation. */
export async function uploadP4(file: Blob, filename = 'programa.p4'): Promise<UploadP4Result> {
  const form = new FormData();
  form.append('file', file, filename);
  return apiFetch<UploadP4Result>('/upload/p4', { method: 'POST', body: form });
}

export async function fetchMockSource(): Promise<{ source: string }> {
  if (!isMockApi()) {
    throw new Error('fetchMockSource is available only in mock API mode');
  }
  return apiFetch<{ source: string }>('/mock/source', { method: 'GET' });
}

// ── Runtime Config Sync (Frontend V2 -> Real Backend) ────────────────────────

export type ExecutionMode = 'auto_concrete' | 'full_symbolic';

export interface FrontendTableEntry {
  match: Record<string, string>;
  matchMask?: Record<string, string>;
  matchPrefix?: Record<string, number>;
  action: string;
  action_params: Record<string, string>;
}

export interface FrontendSwitchRuntime {
  id: string;
  tables: Record<string, FrontendTableEntry[]>;
}

export interface FrontendNode {
  id: string;
  data?: Record<string, unknown>;
}

export interface FrontendEdge {
  id?: string;
  source?: string;
  target?: string;
}

export interface FrontendExecutionConfig {
  nodes: FrontendNode[];
  edges: FrontendEdge[];
  switches: FrontendSwitchRuntime[];
  executionMode?: ExecutionMode;
}

interface BackendTopology {
  hosts: Record<string, { ip: string; mac: string; conectado_a: string }>;
  switches: Record<string, { portas: Record<string, number> }>;
  links: Array<{ from: string; to: string }>;
}

type RuntimeMatchValue = string | [string | number, string | number];
interface RuntimeEntry {
  match: Record<string, RuntimeMatchValue>;
  action: string;
  action_params: Record<string, string>;
}
type RuntimeConfig = Record<string, Record<string, RuntimeEntry[]>>;

const asText = (value: unknown): string => {
  if (typeof value === 'string') return value.trim();
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return '';
};

const isIpv4Literal = (value: string): boolean => {
  const v = value.trim();
  if (!/^(\d{1,3})(\.\d{1,3}){3}$/.test(v)) return false;
  return v.split('.').every((part) => {
    const n = Number(part);
    return Number.isFinite(n) && n >= 0 && n <= 255;
  });
};

const prefixToIpv4Mask = (prefix: number): string => {
  const p = Math.max(0, Math.min(32, Math.trunc(prefix)));
  const parts: number[] = [];
  for (let i = 0; i < 4; i++) {
    const rem = Math.max(0, Math.min(8, p - i * 8));
    const octet = rem === 0 ? 0 : (0xff << (8 - rem)) & 0xff;
    parts.push(octet);
  }
  return parts.join('.');
};

const parseIpv4Cidr = (value: string): { ip: string; prefix: number } | null => {
  const m = value.trim().match(/^(\d{1,3}(?:\.\d{1,3}){3})\/(\d{1,2})$/);
  if (!m) return null;
  const ip = m[1];
  const prefix = Number(m[2]);
  if (!isIpv4Literal(ip) || !Number.isFinite(prefix) || prefix < 0 || prefix > 32) return null;
  return { ip, prefix };
};

const inferTernaryMaskFromFieldValue = (field: string, value: string, currentMask?: string): string => {
  const f = field.toLowerCase();
  const v = value.trim();
  const m = (currentMask ?? '').trim();

  // Respect explicit user-provided mask exactly (including 0.0.0.0 wildcard).
  if (m) return m;
  if (isSymbolicToken(v)) return m || '0.0.0.0';
  if (!isIpv4Literal(v)) return m || '0xffffffff';
  if (v === '0.0.0.0') return m || '0.0.0.0';
  if ((f.includes('dstaddr') || f.includes('dst_addr')) && v.endsWith('.0')) return '255.255.255.0';
  return '255.255.255.255';
};

const isSymbolicToken = (value: unknown): boolean => {
  if (value === null || value === undefined) return true;
  if (typeof value !== 'string') return false;
  return SYMBOLIC_TOKENS.has(value.trim().toLowerCase());
};

const edgeKey = (edge: FrontendEdge, index: number): string =>
  edge.id ?? `${edge.source ?? 'unknown'}::${edge.target ?? 'unknown'}::${index}`;

function buildTopologyPayload(config: FrontendExecutionConfig): BackendTopology {
  const switchNodes = config.nodes.filter((n) => n.id.startsWith('s'));
  const hostNodes = config.nodes.filter((n) => n.id.startsWith('h'));

  const switches: BackendTopology['switches'] = {};
  const edgePortBySwitch = new Map<string, string>();

  switchNodes.forEach((swNode) => {
    const connectedEdges = config.edges.filter((e) => e.source === swNode.id || e.target === swNode.id);
    const portas: Record<string, number> = {};

    connectedEdges.forEach((edge, idx) => {
      const portNo = idx + 1;
      const portName = `${swNode.id}-eth${portNo}`;
      portas[portName] = portNo;
      edgePortBySwitch.set(`${swNode.id}|${edgeKey(edge, idx)}`, portName);
    });

    switches[swNode.id] = { portas };
  });

  const hosts: BackendTopology['hosts'] = {};
  hostNodes.forEach((hostNode, hostIdx) => {
    const attachedEdgeIndex = config.edges.findIndex((edge) =>
      (edge.source === hostNode.id && edge.target?.startsWith('s')) ||
      (edge.target === hostNode.id && edge.source?.startsWith('s'))
    );
    const attachedEdge = attachedEdgeIndex >= 0 ? config.edges[attachedEdgeIndex] : undefined;
    const attachedSwitchId = attachedEdge
      ? (attachedEdge.source === hostNode.id ? attachedEdge.target : attachedEdge.source)
      : undefined;
    const connectedPort = (attachedSwitchId && attachedEdge)
      ? edgePortBySwitch.get(`${attachedSwitchId}|${edgeKey(attachedEdge, attachedEdgeIndex)}`)
      : undefined;

    const data = hostNode.data;
    const fallbackIdx = hostIdx + 1;
    const ip = typeof data?.ip === 'string' ? data.ip : `10.0.${fallbackIdx}.10`;
    const mac = typeof data?.mac === 'string' ? data.mac : `00:00:00:00:${String(fallbackIdx).padStart(2, '0')}:00`;
    const conectado_a = connectedPort ?? `${attachedSwitchId ?? 's1'}-eth1`;

    hosts[hostNode.id] = { ip, mac, conectado_a };
  });

  const links: BackendTopology['links'] = [];
  config.edges.forEach((edge, idx) => {
    if (!edge.source?.startsWith('s') || !edge.target?.startsWith('s')) return;
    const key = edgeKey(edge, idx);
    const fromPort = edgePortBySwitch.get(`${edge.source}|${key}`) ?? `${edge.source}-eth1`;
    const toPort = edgePortBySwitch.get(`${edge.target}|${key}`) ?? `${edge.target}-eth1`;
    links.push({ from: fromPort, to: toPort });
  });

  return { hosts, switches, links };
}

function normalizeRuntimeEntry(entry: FrontendTableEntry, mode: ExecutionMode): RuntimeEntry {
  const normalizedMatch: Record<string, RuntimeMatchValue> = {};

  for (const [field, rawValue] of Object.entries(entry.match ?? {})) {
    const concreteValue = mode === 'full_symbolic' ? SYMBOLIC_MARKER : asText(rawValue);
    const symbolicValue = isSymbolicToken(concreteValue) ? SYMBOLIC_MARKER : concreteValue;
    const prefix = entry.matchPrefix?.[field];
    const mask = entry.matchMask?.[field];
    const hasPrefix = typeof prefix === 'number' && Number.isFinite(prefix);
    const hasMask = mask !== undefined;

    if (mode !== 'full_symbolic') {
      const cidr = parseIpv4Cidr(concreteValue);
      if (cidr) {
        if (hasPrefix) {
          // LPM must be encoded as [value, prefix_len], never as dotted mask.
          normalizedMatch[field] = [cidr.ip, cidr.prefix];
        } else if (hasMask) {
          // Ternary may use CIDR shorthand in the UI; convert to explicit mask.
          normalizedMatch[field] = [cidr.ip, prefixToIpv4Mask(cidr.prefix)];
        } else {
          normalizedMatch[field] = cidr.ip;
        }
        continue;
      }
    }

    if (hasPrefix) {
      normalizedMatch[field] = [symbolicValue, mode === 'full_symbolic' ? SYMBOLIC_MARKER : prefix];
      continue;
    }

    if (hasMask) {
      const inferredMask = mode === 'full_symbolic'
        ? SYMBOLIC_MARKER
        : inferTernaryMaskFromFieldValue(field, concreteValue, asText(mask));
      const maskValue = inferredMask;
      normalizedMatch[field] = [symbolicValue, isSymbolicToken(maskValue) ? SYMBOLIC_MARKER : maskValue];
      continue;
    }

    normalizedMatch[field] = symbolicValue;
  }

  const normalizedActionParams: Record<string, string> = {};
  if (mode !== 'full_symbolic') {
    for (const [name, rawValue] of Object.entries(entry.action_params ?? {})) {
      const value = asText(rawValue);
      if (!isSymbolicToken(value)) {
        normalizedActionParams[name] = value;
      }
    }
  }

  return {
    match: normalizedMatch,
    action: entry.action || 'NoAction',
    action_params: normalizedActionParams,
  };
}

function buildRuntimeConfigPayload(config: FrontendExecutionConfig): RuntimeConfig {
  const mode: ExecutionMode = config.executionMode ?? 'auto_concrete';
  const runtimeConfig: RuntimeConfig = {};

  const switches: FrontendSwitchRuntime[] = config.switches.length
    ? config.switches
    : config.nodes.filter((n) => n.id.startsWith('s')).map((n) => ({ id: n.id, tables: {} }));

  switches.forEach((sw) => {
    const perTable: Record<string, RuntimeEntry[]> = {};
    for (const [tableName, entries] of Object.entries(sw.tables ?? {})) {
      const typedEntries = Array.isArray(entries) ? entries : [];
      perTable[tableName] = typedEntries.map((entry: FrontendTableEntry) => normalizeRuntimeEntry(entry, mode));
    }
    runtimeConfig[sw.id] = perTable;
  });

  return runtimeConfig;
}

async function uploadJsonConfig(
  type: 'topology' | 'runtime_config',
  payload: unknown,
  filename: string
): Promise<{ message: string; type: string; filename: string }> {
  const form = new FormData();
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  form.append('file', blob, filename);
  form.append('type', type);
  return apiFetch<{ message: string; type: string; filename: string }>('/upload/json', {
    method: 'POST',
    body: form,
  });
}

export async function syncExecutionConfig(config: FrontendExecutionConfig): Promise<{
  mode: ExecutionMode;
  topology: BackendTopology;
  runtime_config: RuntimeConfig;
}> {
  if (isMockApi()) {
    throw new Error('syncExecutionConfig is only available in real backend mode');
  }

  const mode: ExecutionMode = config.executionMode ?? 'auto_concrete';
  const topology = buildTopologyPayload(config);
  const runtime_config = buildRuntimeConfigPayload(config);

  await Promise.all([
    uploadJsonConfig('topology', topology, 'topology.json'),
    uploadJsonConfig('runtime_config', runtime_config, 'runtime_config.json'),
  ]);

  return { mode, topology, runtime_config };
}

// ── Analysis ─────────────────────────────────────────────────────────────────

export interface ParserResult {
  message: string;
  states: any[];
  parser_info: any;
  state_count: number;
  output_file: string; // 'parser_states.json'
}

export async function analyzeParser(): Promise<ParserResult> {
  return apiFetch<ParserResult>('/analyze/parser', { method: 'POST' });
}

export interface TableResult {
  message: string;
  results_summary: any[];
  output_states: TableOutputStates;
  output_file: string; // e.g. 's1_MyIngress_ipv4_lpm_from_parser_states_output.json'
  diagnostics?: TableDiagnostics;
}

function attachDiagnosticsToOutputStates<T extends { output_states: TableOutputStates; diagnostics?: TableDiagnostics }>(
  result: T
): T {
  if (result.diagnostics && Array.isArray(result.output_states)) {
    Object.defineProperty(result.output_states, 'diagnostics', {
      value: result.diagnostics,
      enumerable: false,
      configurable: true,
    });
  }
  return result;
}

export async function analyzeTable(
  table_name: string,
  switch_id: string,
  input_states: string
): Promise<TableResult> {
  const result = await apiFetch<TableResult>('/analyze/table', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ table_name, switch_id, input_states }),
  });
  return attachDiagnosticsToOutputStates(result);
}

export interface EgressTableResult {
  message: string;
  output_states: TableOutputStates;
  output_file: string;
  diagnostics?: TableDiagnostics;
}

export async function analyzeEgressTable(
  table_name: string,
  switch_id: string,
  input_states: string
): Promise<EgressTableResult> {
  const result = await apiFetch<EgressTableResult>('/analyze/egress_table', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ table_name, switch_id, input_states }),
  });
  return attachDiagnosticsToOutputStates(result);
}

export interface DeparserResult {
  message: string;
  static_info: { name: string; order: string[] };
  analysis_results: any[];
  output_file: string;
}

export async function analyzeDeparser(input_states: string): Promise<DeparserResult> {
  return apiFetch<DeparserResult>('/analyze/deparser', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ input_states }),
  });
}

// ── Info ─────────────────────────────────────────────────────────────────────

export interface Components {
  parser: { name: string; states: number } | null;
  ingress_tables: { name: string }[];
  egress_tables: { name: string }[];
  actions: { name: string }[];
  headers: { name: string; type: string }[];
  deparser: { name: string; order: string[] } | null;
  table_schemas: TableSchema[];
}

export async function getComponents(): Promise<Components> {
  return apiFetch<Components>('/info/components');
}

export async function getSnapshots(): Promise<{ snapshots: string[] }> {
  return apiFetch<{ snapshots: string[] }>('/info/snapshots');
}

// ── Rules / Generate ─────────────────────────────────────────────────────────

export async function generateRules(): Promise<{ message: string; rules: any }> {
  return apiFetch<{ message: string; rules: any }>('/generate/rules', { method: 'POST' });
}
