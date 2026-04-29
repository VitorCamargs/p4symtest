import { afterEach, describe, expect, it, vi } from 'vitest';

const diagnosticsPayload = {
  diagnostics_version: 'onda0.mock.v1',
  table_name: 'MyIngress.ipv4_lpm',
  expected_behavior: 'The table applies IPv4 forwarding logic.',
  observed_behavior: 'The analyzer returned a mock warning.',
  inconclusive: false,
  warnings: [
    {
      type: 'unexpected_drop',
      severity: 'high',
      confidence: 0.78,
      source: 'llm_hypothesis',
      evidence_ids: ['state.summary'],
      explanation: 'Dropped states were observed.',
      suggested_action: 'Inspect egress_spec assignments.',
    },
  ],
  evidence: [
    {
      id: 'state.summary',
      source: 'snapshot_summary',
      summary: 'Two input states produced two output states.',
    },
  ],
  model_info: {
    provider: 'mock',
    model: 'deterministic-table-warning',
    prompt_version: 'mock-table-warning-v1',
  },
  rag_context_ids: [],
};

function installBrowserGlobals() {
  vi.stubGlobal('localStorage', {
    getItem: vi.fn(() => null),
    setItem: vi.fn(),
  });
}

function mockFetchJson(payload: unknown) {
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true,
    json: async () => payload,
  })));
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe('backend diagnostics API contract', () => {
  it('attaches backend table diagnostics to output states', async () => {
    installBrowserGlobals();
    mockFetchJson({
      message: 'table done',
      results_summary: [],
      output_states: [{ description: 'symbolic path' }],
      output_file: 'table_output.json',
      diagnostics: diagnosticsPayload,
    });

    const { analyzeTable } = await import('./api');
    const result = await analyzeTable('MyIngress.ipv4_lpm', 's1', 'parser_states.json');

    expect(result.diagnostics).toEqual(diagnosticsPayload);
    expect(result.output_states.diagnostics).toEqual(diagnosticsPayload);
    expect(Object.keys(result.output_states)).not.toContain('diagnostics');
  });

  it('attaches backend egress diagnostics to output states', async () => {
    installBrowserGlobals();
    mockFetchJson({
      message: 'egress done',
      output_states: [{ description: 'egress symbolic path' }],
      output_file: 'egress_output.json',
      diagnostics: diagnosticsPayload,
    });

    const { analyzeEgressTable } = await import('./api');
    const result = await analyzeEgressTable(
      'MyEgress.egress_port_smac',
      's1',
      'ingress_output.json'
    );

    expect(result.diagnostics).toEqual(diagnosticsPayload);
    expect(result.output_states.diagnostics).toEqual(diagnosticsPayload);
    expect(Object.keys(result.output_states)).not.toContain('diagnostics');
  });
});
