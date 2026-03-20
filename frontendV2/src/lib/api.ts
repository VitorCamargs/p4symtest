// api.ts — Centralized API client for P4SymTest
// All requests go to VITE_API_URL (defaults to mock backend at localhost:5001)

const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:5001/api';

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(body.error ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

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
  output_states: any[];
  output_file: string; // e.g. 's1_MyIngress_ipv4_lpm_from_parser_states_output.json'
}

export async function analyzeTable(
  table_name: string,
  switch_id: string,
  input_states: string
): Promise<TableResult> {
  return apiFetch<TableResult>('/analyze/table', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ table_name, switch_id, input_states }),
  });
}

export interface EgressTableResult {
  message: string;
  output_states: any[];
  output_file: string;
}

export async function analyzeEgressTable(
  table_name: string,
  switch_id: string,
  input_states: string
): Promise<EgressTableResult> {
  return apiFetch<EgressTableResult>('/analyze/egress_table', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ table_name, switch_id, input_states }),
  });
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
