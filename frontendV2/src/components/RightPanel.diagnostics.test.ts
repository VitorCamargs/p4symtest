import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import diagnosticsMock from '../mocks/default/table_warning_diagnostics.json';
import unavailableMock from '../mocks/default/table_diagnostics_unavailable.json';
import type { TableDiagnostics, TableOutputStates } from '../lib/api';
import RightPanel from './RightPanel';

function resultWithDiagnostics(diagnostics?: TableDiagnostics): TableOutputStates {
  const states = [
    {
      description: 'start [extract ethernet] -> parse_ipv4 [extract ipv4] -> MyIngress.ipv4_lpm',
      history: ['Parser', 'MyIngress.ipv4_lpm'],
      present_headers: ['ethernet', 'ipv4'],
    },
  ] as TableOutputStates;

  if (diagnostics) {
    Object.defineProperty(states, 'diagnostics', {
      value: diagnostics,
      enumerable: false,
      configurable: true,
    });
  }

  return states;
}

function renderRightPanel(diagnostics?: TableDiagnostics): string {
  return renderToStaticMarkup(
    createElement(RightPanel, {
      activeVerification: { type: 'table', name: 'MyIngress.ipv4_lpm' },
      verificationResult: resultWithDiagnostics(diagnostics),
      parentVerificationResult: [],
    })
  );
}

describe('RightPanel diagnostics', () => {
  it('renders warning type, severity, confidence, inconclusive state, and evidence', () => {
    const markup = renderRightPanel(diagnosticsMock as TableDiagnostics);

    expect(markup).toContain('unexpected_drop');
    expect(markup).toContain('high');
    expect(markup).toContain('82% confidence');
    expect(markup).toContain('inconclusive');
    expect(markup).toContain('fact-drop-001');
    expect(markup).toContain('All output states satisfy egress_spec == DROP.');
    expect(markup).toContain('standard_metadata.egress_spec');
  });

  it('renders without diagnostics without crashing', () => {
    expect(() => renderRightPanel()).not.toThrow();
    expect(renderRightPanel()).not.toContain('table-diagnostics');
  });

  it('renders diagnostics_unavailable state', () => {
    const markup = renderRightPanel(unavailableMock as TableDiagnostics);

    expect(markup).toContain('diagnostics_unavailable');
    expect(markup).toContain('llm-analyzer timeout');
  });
});
