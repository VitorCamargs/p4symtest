import { AlertTriangle, CircleAlert, Info, WifiOff } from 'lucide-react';
import type {
  TableDiagnostics,
  TableDiagnosticsUnavailable,
  TableOutputStates,
  TableWarning,
  TableWarningEvidence,
  TableWarningSeverity,
} from '../lib/api';

function isDiagnosticsUnavailable(diagnostics: TableDiagnostics): diagnostics is TableDiagnosticsUnavailable {
  return 'diagnostics_unavailable' in diagnostics && diagnostics.diagnostics_unavailable === true;
}

function isDiagnosticsPayload(value: unknown): value is TableDiagnostics {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Record<string, unknown>;
  if (candidate.diagnostics_unavailable === true) return true;
  return typeof candidate.diagnostics_version === 'string' && Array.isArray(candidate.warnings);
}

export function readTableDiagnostics(verificationResult: unknown): TableDiagnostics | null {
  if (!verificationResult) return null;

  if (Array.isArray(verificationResult)) {
    const diagnostics = (verificationResult as TableOutputStates).diagnostics;
    return isDiagnosticsPayload(diagnostics) ? diagnostics : null;
  }

  if (typeof verificationResult === 'object') {
    const candidate = (verificationResult as { diagnostics?: unknown }).diagnostics ?? verificationResult;
    return isDiagnosticsPayload(candidate) ? candidate : null;
  }

  return null;
}

function severityStyle(severity: TableWarningSeverity): { color: string; bg: string; border: string } {
  if (severity === 'high') return { color: '#fca5a5', bg: 'rgba(239,68,68,0.1)', border: 'rgba(239,68,68,0.35)' };
  if (severity === 'medium') return { color: '#fbbf24', bg: 'rgba(245,158,11,0.1)', border: 'rgba(245,158,11,0.35)' };
  if (severity === 'low') return { color: '#93c5fd', bg: 'rgba(59,130,246,0.1)', border: 'rgba(59,130,246,0.35)' };
  return { color: '#cbd5e1', bg: 'rgba(148,163,184,0.1)', border: 'rgba(148,163,184,0.28)' };
}

function confidenceLabel(confidence: number): string {
  const clamped = Math.max(0, Math.min(1, Number.isFinite(confidence) ? confidence : 0));
  return `${Math.round(clamped * 100)}% confidence`;
}

function EvidenceItem({ evidence }: { evidence: TableWarningEvidence }) {
  return (
    <li style={{ color: 'var(--text-main)', lineHeight: 1.45 }}>
      <span style={{ color: '#93c5fd', fontFamily: 'monospace' }}>{evidence.id}</span>
      <span style={{ color: 'var(--text-muted)' }}> [{evidence.source}] </span>
      <span>{evidence.summary}</span>
      {evidence.location && (
        <span style={{ color: 'var(--text-muted)' }}> ({evidence.location})</span>
      )}
    </li>
  );
}

function WarningCard({
  warning,
  evidenceById,
}: {
  warning: TableWarning;
  evidenceById: Map<string, TableWarningEvidence>;
}) {
  const tone = severityStyle(warning.severity);
  const linkedEvidence = warning.evidence_ids
    .map((id) => evidenceById.get(id))
    .filter((evidence): evidence is TableWarningEvidence => Boolean(evidence));
  const missingEvidenceIds = warning.evidence_ids.filter((id) => !evidenceById.has(id));

  return (
    <div style={{ border: `1px solid ${tone.border}`, borderRadius: '6px', background: 'rgba(255,255,255,0.02)', padding: '0.75rem' }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.45rem', marginBottom: '0.55rem' }}>
        <code style={{ color: '#e5e7eb', fontSize: '0.75rem', fontWeight: 700 }}>{warning.type}</code>
        <span style={{ color: tone.color, background: tone.bg, border: `1px solid ${tone.border}`, borderRadius: '4px', padding: '0.12rem 0.42rem', fontSize: '0.68rem', fontWeight: 700 }}>
          {warning.severity}
        </span>
        <span style={{ color: '#cbd5e1', background: 'rgba(148,163,184,0.08)', border: '1px solid rgba(148,163,184,0.22)', borderRadius: '4px', padding: '0.12rem 0.42rem', fontSize: '0.68rem', fontWeight: 700 }}>
          {confidenceLabel(warning.confidence)}
        </span>
        <span style={{ color: 'var(--text-muted)', fontSize: '0.68rem', fontFamily: 'monospace' }}>
          {warning.source}
        </span>
      </div>

      <div style={{ color: 'var(--text-main)', fontSize: '0.76rem', lineHeight: 1.45, marginBottom: '0.45rem' }}>
        {warning.explanation}
      </div>
      <div style={{ color: '#cbd5e1', fontSize: '0.74rem', lineHeight: 1.45, marginBottom: '0.55rem' }}>
        <strong style={{ color: '#a7f3d0' }}>Suggested action:</strong> {warning.suggested_action}
      </div>

      <div style={{ color: 'var(--text-muted)', fontSize: '0.7rem', fontWeight: 700, marginBottom: '0.3rem' }}>
        Evidence
      </div>
      {linkedEvidence.length > 0 || missingEvidenceIds.length > 0 ? (
        <ul style={{ margin: 0, paddingLeft: '1rem', display: 'flex', flexDirection: 'column', gap: '0.25rem', fontSize: '0.72rem' }}>
          {linkedEvidence.map((evidence) => <EvidenceItem key={evidence.id} evidence={evidence} />)}
          {missingEvidenceIds.map((id) => (
            <li key={id} style={{ color: 'var(--text-muted)', fontFamily: 'monospace' }}>{id}</li>
          ))}
        </ul>
      ) : (
        <div style={{ color: 'var(--text-muted)', fontSize: '0.72rem' }}>No evidence linked to this warning.</div>
      )}
    </div>
  );
}

export function TableDiagnosticsPanel({ diagnostics }: { diagnostics?: TableDiagnostics | null }) {
  if (!diagnostics) return null;

  if (isDiagnosticsUnavailable(diagnostics)) {
    return (
      <section data-testid="table-diagnostics" style={{ background: 'var(--bg-panel)', padding: '1rem', borderRadius: '6px', border: '1px solid rgba(148,163,184,0.24)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', color: '#e5e7eb', fontWeight: 700, fontSize: '0.86rem', marginBottom: '0.6rem' }}>
          <WifiOff size={15} color="#fbbf24" /> Diagnostics
        </div>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem', color: '#fbbf24', background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.28)', borderRadius: '4px', padding: '0.18rem 0.45rem', fontSize: '0.72rem', fontFamily: 'monospace', fontWeight: 700 }}>
          diagnostics_unavailable
        </div>
        {(diagnostics.reason || diagnostics.message) && (
          <div style={{ color: 'var(--text-muted)', fontSize: '0.76rem', lineHeight: 1.45, marginTop: '0.55rem' }}>
            {diagnostics.reason ?? diagnostics.message}
          </div>
        )}
      </section>
    );
  }

  const warnings = diagnostics.warnings ?? [];
  const evidence = diagnostics.evidence ?? [];
  const evidenceById = new Map(evidence.map((item) => [item.id, item]));

  return (
    <section data-testid="table-diagnostics" style={{ background: 'var(--bg-panel)', padding: '1rem', borderRadius: '6px', border: '1px solid var(--border)' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.6rem', marginBottom: '0.75rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', color: '#e5e7eb', fontWeight: 700, fontSize: '0.86rem' }}>
          <AlertTriangle size={15} color="#fbbf24" /> Diagnostics
        </div>
        <span style={{ color: 'var(--text-muted)', fontSize: '0.68rem', fontFamily: 'monospace' }}>
          {diagnostics.diagnostics_version}
        </span>
      </div>

      {diagnostics.inconclusive && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: '#fbbf24', background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.25)', borderRadius: '6px', padding: '0.5rem 0.6rem', fontSize: '0.74rem', marginBottom: '0.7rem' }}>
          <CircleAlert size={13} /> <strong>inconclusive</strong>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.45rem', marginBottom: '0.85rem', fontSize: '0.74rem', lineHeight: 1.45 }}>
        <div>
          <span style={{ color: 'var(--text-muted)', fontWeight: 700 }}>Table:</span>{' '}
          <code style={{ color: '#93c5fd' }}>{diagnostics.table_name}</code>
        </div>
        <div>
          <span style={{ color: 'var(--text-muted)', fontWeight: 700 }}>Expected:</span>{' '}
          <span style={{ color: 'var(--text-main)' }}>{diagnostics.expected_behavior}</span>
        </div>
        <div>
          <span style={{ color: 'var(--text-muted)', fontWeight: 700 }}>Observed:</span>{' '}
          <span style={{ color: 'var(--text-main)' }}>{diagnostics.observed_behavior}</span>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
        {warnings.length > 0 ? (
          warnings.map((warning, index) => (
            <WarningCard key={`${warning.type}-${index}`} warning={warning} evidenceById={evidenceById} />
          ))
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--text-muted)', fontSize: '0.74rem', border: '1px solid var(--border)', borderRadius: '6px', padding: '0.6rem' }}>
            <Info size={13} /> No warnings returned by diagnostics.
          </div>
        )}
      </div>

      {evidence.length > 0 && (
        <details style={{ marginTop: '0.85rem', color: 'var(--text-main)', fontSize: '0.73rem' }}>
          <summary style={{ cursor: 'pointer', color: 'var(--text-muted)', fontWeight: 700 }}>Evidence catalog</summary>
          <ul style={{ margin: '0.5rem 0 0', paddingLeft: '1rem', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
            {evidence.map((item) => <EvidenceItem key={item.id} evidence={item} />)}
          </ul>
        </details>
      )}
    </section>
  );
}
