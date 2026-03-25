import { useState, useRef, useEffect } from 'react';
import { Activity, ChevronDown, ChevronRight, ArrowRight, CheckCircle2, XCircle, Eye, EyeOff } from 'lucide-react';
import { parseConstraint, prettyField, prettyFieldValue, prettyComplexConstraint } from '../lib/smt2pretty';

// ── PathItem ──────────────────────────────────────────────────────────────────

const PathItem = ({
  pathData,
  index,
  displayName,
  activeVerification,
  compiledData,
}: {
  pathData: any;
  index: number;
  displayName?: string;
  activeVerification: { type: string; name: string } | null;
  compiledData?: any;
}) => {
  const [expanded, setExpanded] = useState(false);

  const rawNodes = pathData.description ? pathData.description.split(' -> ') : [];
  const pathNodes = rawNodes.map((node: string) => {
    const match = node.match(/\[(.*?)\]/);
    return match ? match[1] : node;
  });

  let status = 'Processed';
  let StatusIcon = CheckCircle2;
  let statusColor = 'var(--success)';

  const targetType = activeVerification?.type;
  const targetName = activeVerification?.name;

  if (targetType === 'parser' || targetType === 'deparser') {
    if (
      pathData.description?.toLowerCase().includes('drop') ||
      pathData.history?.some((h: string) => h.toLowerCase().includes('drop'))
    ) {
      status = 'Dropped';
      StatusIcon = XCircle;
      statusColor = 'var(--danger)';
    } else {
      status = 'Parsed';
    }
  } else {
    if (targetName && pathData.history?.includes(targetName)) {
      status = 'Evaluated';
    } else {
      status = 'Missed Conditions';
      StatusIcon = XCircle;
      statusColor = 'var(--text-muted)';
    }
  }

  return (
    <div style={{ background: 'var(--bg-panel)', padding: '0.8rem', borderRadius: '6px', border: '1px solid var(--border)' }}>
      <div
        onClick={() => setExpanded(!expanded)}
        style={{ display: 'flex', alignItems: 'center', gap: '0.8rem', cursor: 'pointer', userSelect: 'none' }}
      >
        {expanded ? <ChevronDown size={16} color="var(--accent)" /> : <ChevronRight size={16} color="var(--accent)" />}

        <span style={{ fontWeight: 600, color: 'var(--text-main)', fontSize: '0.85rem', minWidth: '60px' }}>
          {displayName || `Path ${index + 1}`}
        </span>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginLeft: 'auto', background: 'var(--bg-surface)', padding: '0.3rem 0.6rem', borderRadius: '4px', color: statusColor, fontSize: '0.75rem', fontWeight: 600 }}>
          <StatusIcon size={14} /> {status}
        </div>
      </div>

      {!expanded && pathNodes.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginTop: '0.8rem', marginLeft: '1.8rem', overflowX: 'auto', paddingBottom: '0.4rem' }}>
          {pathNodes.map((node: string, i: number) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <div style={{ background: 'var(--bg-surface)', color: 'var(--text-main)', padding: '0.2rem 0.6rem', borderRadius: '12px', fontSize: '0.7rem', whiteSpace: 'nowrap', border: '1px solid var(--border)' }}>
                {node}
              </div>
              {i < pathNodes.length - 1 && <ArrowRight size={12} color="var(--text-muted)" />}
            </div>
          ))}
        </div>
      )}

      {expanded && (
        <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--border)', fontSize: '0.75rem', marginLeft: '1.8rem' }}>
          {pathNodes.length > 0 && (
            <div style={{ marginBottom: '1rem' }}>
              <strong style={{ color: 'var(--accent)', display: 'block', marginBottom: '0.6rem' }}>Path Trace:</strong>
              <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '0.4rem' }}>
                {pathNodes.map((node: string, i: number) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.4rem' }}>
                    <div style={{ background: 'var(--bg-surface)', color: 'var(--text-main)', padding: '0.3rem 0.8rem', borderRadius: '16px', fontSize: '0.75rem', border: '1px solid var(--accent)' }}>
                      {node}
                    </div>
                    {i < pathNodes.length - 1 && <ArrowRight size={14} color="var(--text-muted)" />}
                  </div>
                ))}
              </div>
            </div>
          )}

          {status === 'Missed Conditions' && pathData.z3_constraints_smt2 && (
            (() => {
              const allPipelines: any[] = compiledData?.pipelines || [];
              let failedCondition = '';

              for (const pipeline of allPipelines) {
                const gatingNode = (pipeline.conditionals || []).find(
                  (cond: any) => cond.true_next === targetName
                );
                if (gatingNode?.source_info?.source_fragment) {
                  failedCondition = gatingNode.source_info.source_fragment;
                  break;
                }
              }

              if (!failedCondition) {
                failedCondition = 'Table reachability condition not met';
              }

              return (
                <div style={{ marginBottom: '1rem', padding: '0.8rem', background: 'rgba(239, 68, 68, 0.05)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '6px' }}>
                  <strong style={{ color: '#ef4444', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <XCircle size={14} /> Pruned by Condition Verifier
                  </strong>
                  <div style={{ marginTop: '0.5rem', color: '#fca5a5', fontSize: '0.75rem' }}>
                    Failed condition: <code style={{ background: 'rgba(0,0,0,0.3)', padding: '0.2rem 0.4rem', borderRadius: '4px' }}>{failedCondition}</code>
                  </div>
                </div>
              );
            })()
          )}

          {pathData.present_headers && (
            <div style={{ marginBottom: '1rem' }}>
              <strong style={{ color: 'var(--accent)' }}>Present Headers:</strong><br />
              <span style={{ color: '#94a3b8' }}>{pathData.present_headers.join(', ')}</span>
            </div>
          )}

          {pathData.field_updates && Object.keys(pathData.field_updates).length > 0 && (
            <FieldUpdatesView updates={pathData.field_updates} />
          )}

          {pathData.z3_constraints_smt2 && (
            <Z3ConstraintsView constraints={pathData.z3_constraints_smt2} />
          )}
        </div>
      )}
    </div>
  );
};

// ── FieldUpdatesView ──────────────────────────────────────────────────────────

// --- Evaluator utility for FieldUpdatesView ---
function splitSmtTokens(s: string): string[] {
  const tokens: string[] = [];
  let depth = 0;
  let current = '';
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (c === '(') { depth++; current += c; }
    else if (c === ')') {
      depth--; current += c;
      if (depth === 0) { tokens.push(current.trim()); current = ''; }
    }
    else if (/\s/.test(c)) {
      if (depth === 0) {
        if (current.trim()) { tokens.push(current.trim()); current = ''; }
      } else current += c;
    } else current += c;
  }
  if (current.trim()) tokens.push(current.trim());
  return tokens;
}

function evalSExpr(expr: string, bindings: Record<string, string>): string {
  expr = expr.trim();
  while(true) {
    const letM = expr.match(/^\(let\s+\(\(.*?\)\)\n?\s*([\s\S]+)\)$/s) || expr.match(/^\(let\s+\(.*?\)\s+([\s\S]+)\)$/s);
    if (letM) expr = letM[letM.length - 1].trim();
    else break;
  }
  
  if (!expr.startsWith('(')) return expr;

  const inner = expr.substring(1, expr.length - 1).trim();
  const tokens = splitSmtTokens(inner);
  
  if (tokens.length === 0) return expr;
  
  if (tokens[0] === 'ite') {
    const cond = evalSExpr(tokens[1], bindings);
    if (cond === 'true') return evalSExpr(tokens[2], bindings);
    if (cond === 'false') return evalSExpr(tokens.slice(3).join(' '), bindings);
    return expr; // Unresolved condition
  }
  
  if (tokens[0] === '=') {
    const a = evalSExpr(tokens[1], bindings);
    const b = evalSExpr(tokens[2], bindings);
    if (bindings[a]) return bindings[a] === b ? 'true' : 'false';
    if (bindings[b]) return bindings[b] === a ? 'true' : 'false';
    return 'unknown';
  }
  
  if (tokens[0] === 'or') {
    let hasUnknown = false;
    for(let i = 1; i < tokens.length; i++) {
      const res = evalSExpr(tokens[i], bindings);
      if (res === 'true') return 'true';
      if (res !== 'false') hasUnknown = true;
    }
    return hasUnknown ? 'unknown' : 'false';
  }
  
  return expr;
}

function normalizeResult(res: string, targetField: string): string {
  let r = res.startsWith('#') ? prettyFieldValue(res, targetField) : res;
  if (r.includes('(bvadd #xff ')) {
    const m = r.match(/\(bvadd #xff\s+([a-zA-Z0-9_.$]+)\)/);
    if (m) r = `${prettyField(m[1])} - 1`;
  }
  return r;
}

function FieldUpdatesView({ updates }: { updates: Record<string, string> }) {
  const [showRaw, setShowRaw] = useState(false);

  // 1. Analyze condition variables
  const subjectValues = new Map<string, Set<string>>();
  const regex = /\(=\s+([a-zA-Z0-9_.$]+)\s+(#[xb][0-9a-fA-F]+)\)/g;
  
  Object.values(updates).forEach(expr => {
    let m;
    while ((m = regex.exec(expr)) !== null) {
      if (!subjectValues.has(m[1])) subjectValues.set(m[1], new Set());
      subjectValues.get(m[1])!.add(m[2]);
    }
  });

  let primarySubject = 'Condition';
  let maxVals = 0;
  subjectValues.forEach((vals, subj) => {
    if (vals.size > maxVals) { maxVals = vals.size; primarySubject = subj; }
  });

  const columns = Object.keys(updates).map(k => prettyField(k));
  const rawFields = Object.keys(updates);
  
  const rows: { label: string, isElse?: boolean, cells: string[] }[] = [];

  if (!showRaw) {
    if (maxVals > 0) {
      // Generate row for each matched value
      const values = Array.from(subjectValues.get(primarySubject) || []);
      values.forEach(val => {
        const bindings = { [primarySubject]: val };
        const cells = rawFields.map((rf) => {
           const r = evalSExpr(updates[rf], bindings);
           return r === rf || (r.includes('ite') && r === updates[rf]) ? 'none' : normalizeResult(r, rf);
        });
        rows.push({ label: prettyFieldValue(val, primarySubject), cells });
      });
      // Generate else row
      const elseBindings = { [primarySubject]: '#xUnmatchedValue' };
      const elseCells = rawFields.map((rf) => {
         const r = evalSExpr(updates[rf], elseBindings);
         return r === rf || (r.includes('ite') && r === updates[rf]) ? 'none' : normalizeResult(r, rf);
      });
      if (elseCells.some(c => c !== 'none')) {
        rows.push({ label: 'else', isElse: true, cells: elseCells });
      }
    } else {
      // Unconditional assignment fallback
      const row = rawFields.map((rf) => normalizeResult(updates[rf], rf));
      rows.push({ label: 'Always', cells: row });
    }
  }

  const pSubjFormat = primarySubject !== 'Condition' ? prettyField(primarySubject) : 'Condition';

  return (
    <div style={{ marginBottom: '1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.8rem' }}>
        <strong style={{ color: 'var(--accent)', fontSize: '0.8rem' }}>Field Updates</strong>
        <button onClick={() => setShowRaw(r => !r)} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.7rem' }}>
          {showRaw ? <EyeOff size={12} /> : <Eye size={12} />} {showRaw ? 'Visual' : 'Raw SMT2'}
        </button>
      </div>
      
      {showRaw ? (
        <div style={{ background: '#0a0a0a', padding: '0.8rem', borderRadius: '6px', fontFamily: 'monospace', color: '#10b981', fontSize: '0.7rem', overflowX: 'auto', whiteSpace: 'pre' }}>
          {Object.entries(updates).map(([f, v]) => `${f} = ${v}`).join('\\n')}
        </div>
      ) : (
        <div style={{ border: '1px solid var(--border)', borderRadius: '6px', overflow: 'hidden', overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.75rem', minWidth: '400px' }}>
            <thead>
              <tr style={{ background: 'var(--bg-surface)', borderBottom: '1px solid var(--border)' }}>
                <th colSpan={columns.length + 1} style={{ padding: '0.6rem 0.8rem', textAlign: 'center', color: 'var(--text-main)', fontSize: '0.75rem', fontWeight: 600 }}>
                  <code style={{ color: '#38bdf8', fontFamily: 'monospace', fontWeight: 700, background: 'transparent', fontSize: '0.8rem' }}>{pSubjFormat}</code>
                </th>
              </tr>
              <tr style={{ background: 'rgba(255,255,255,0.03)', borderBottom: '1px solid var(--border)' }}>
                <th style={{ padding: '0.4rem 0.8rem', textAlign: 'left', color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.7rem', borderRight: '1px solid var(--border)', width: '15%' }}>
                  {pSubjFormat}
                </th>
                {columns.map(c => (
                  <th key={c} style={{ padding: '0.4rem 0.8rem', textAlign: 'left', color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.7rem', borderRight: '1px solid var(--border)' }}>
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} style={{ borderBottom: i < rows.length - 1 ? '1px solid var(--border)' : 'none', background: row.isElse ? 'rgba(0,0,0,0.1)' : 'transparent' }}>
                  <td style={{ padding: '0.4rem 0.8rem', borderRight: '1px solid var(--border)', fontFamily: 'monospace', color: row.isElse ? 'var(--text-muted)' : '#fbbf24', fontWeight: row.isElse ? 400 : 700 }}>
                    {row.label}
                  </td>
                  {row.cells.map((cell, ci) => (
                    <td key={ci} style={{ padding: '0.4rem 0.8rem', borderRight: '1px solid var(--border)', fontFamily: 'monospace', color: cell !== 'none' ? '#10b981' : 'var(--text-muted)', opacity: cell !== 'none' ? 1 : 0.4 }}>
                       {cell !== 'none' ? (
                          <span style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>{cell}</span>
                       ) : 'none'}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Z3ConstraintsView ─────────────────────────────────────────────────────────

const OP_COLORS: Record<string, { bg: string; color: string }> = {
  '==':      { bg: 'rgba(34,197,94,0.1)',   color: '#22c55e' },
  '!=':      { bg: 'rgba(239,68,68,0.1)',   color: '#ef4444' },
  'is true': { bg: 'rgba(56,189,248,0.1)',  color: '#38bdf8' },
  'is false':{ bg: 'rgba(239,68,68,0.08)', color: '#f87171' },
};

function Z3ConstraintsView({ constraints }: { constraints: string[] }) {
  const [showRaw, setShowRaw] = useState(false);
  const parsed = constraints.map(parseConstraint);
  return (
    <div style={{ marginBottom: '0.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
        <strong style={{ color: 'var(--accent)', fontSize: '0.8rem' }}>Z3 Constraints</strong>
        <button onClick={() => setShowRaw(r => !r)} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.7rem' }}>
          {showRaw ? <EyeOff size={12} /> : <Eye size={12} />} {showRaw ? 'Visual' : 'Raw SMT2'}
        </button>
      </div>
      {showRaw ? (
        <div style={{ background: '#0a0a0a', padding: '0.8rem', borderRadius: '6px', fontFamily: 'monospace', color: '#10b981', fontSize: '0.7rem', overflowX: 'auto', whiteSpace: 'pre', boxShadow: 'inset 0 0 10px rgba(0,0,0,0.5)' }}>
          {constraints.join('\n')}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
          {parsed.map((p, i) => {
            if (!p.isComplex && p.field && p.op) {
              const style = OP_COLORS[p.op] || { bg: 'var(--bg-surface)', color: 'var(--text-main)' };
              return (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.35rem 0.7rem', background: 'var(--bg-surface)', borderRadius: '6px', border: `1px solid ${style.color}22` }}>
                  <code style={{ color: '#94a3b8', fontSize: '0.75rem', fontFamily: 'monospace', flex: 1 }}>{p.field}</code>
                  <span style={{ background: style.bg, color: style.color, padding: '0.15rem 0.5rem', borderRadius: '4px', fontSize: '0.72rem', fontWeight: 700, flexShrink: 0 }}>{p.op}</span>
                  <code style={{ color: style.color, fontSize: '0.75rem', fontFamily: 'monospace', flexShrink: 0 }}>{p.value}</code>
                </div>
              );
            }
            return (
              <div key={i} style={{ padding: '0.35rem 0.7rem', background: 'rgba(168,85,247,0.07)', border: '1px solid rgba(168,85,247,0.2)', borderRadius: '6px', color: '#c4b5fd', fontSize: '0.72rem', fontFamily: 'monospace' }}>
                {prettyComplexConstraint(p.original)}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── RightPanel ────────────────────────────────────────────────────────────────

export default function RightPanel({
  activeVerification,
  verificationResult,
  compiledData,
}: {
  activeVerification: { type: string; name: string } | null;
  verificationResult: any;
  compiledData?: any;
}) {
  const activeLogs: any[] = Array.isArray(verificationResult) ? verificationResult : [];
  const numPaths = activeLogs.length;

  const pathMapRef = useRef<Map<string, number>>(new Map());
  const pathCounterRef = useRef<number>(1);

  useEffect(() => {
    if (!activeVerification) {
      pathMapRef.current.clear();
      pathCounterRef.current = 1;
    }
  }, [activeVerification]);

  const getPathDisplayName = (state: any, index: number, allStates: any[]) => {
    const defaultName = `Path ${index + 1}`;
    if (!state.path_id) return defaultName;

    if (!pathMapRef.current.has(state.path_id)) {
       pathMapRef.current.set(state.path_id, pathCounterRef.current++);
    }
    const baseNum = pathMapRef.current.get(state.path_id);
    
    const duplicates = allStates.filter(s => s.path_id === state.path_id);
    if (duplicates.length > 1) {
       const subIdx = duplicates.indexOf(state);
       return `Path ${baseNum}.${subIdx + 1}`;
    }
    return `Path ${baseNum}`;
  };

  // Pre-calculate display names and sorting keys
  const renderedLogs = activeLogs.map((log, idx) => {
    const displayName = getPathDisplayName(log, idx, activeLogs);
    const match = displayName.match(/Path (\d+)(?:\.(\d+))?/);
    const baseNum = match ? parseInt(match[1], 10) : 9999;
    const subNum = match && match[2] ? parseInt(match[2], 10) : 0;
    return { log, idx, displayName, baseNum, subNum };
  });

  // Sort by base number, then sub number
  renderedLogs.sort((a, b) => {
    if (a.baseNum !== b.baseNum) return a.baseNum - b.baseNum;
    return a.subNum - b.subNum;
  });

  return (
    <>
      <div className="panel-header">
        <Activity size={18} /> Execution Info
      </div>
      <div className="panel-content" style={{ display: 'flex', flexDirection: 'column', gap: '1rem', background: 'var(--bg-dark)' }}>

        <div style={{ background: 'var(--bg-panel)', padding: '1rem', borderRadius: '6px', border: '1px solid var(--border)' }}>
          <h4 style={{ marginBottom: '0.8rem', color: '#fff', fontSize: '0.9rem' }}>Verification Results</h4>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.6rem', fontSize: '0.85rem' }}>
            <div style={{ color: 'var(--text-muted)' }}>Target:</div>
            <div style={{ color: 'var(--accent)', fontWeight: 600 }}>{activeVerification?.name || 'None'}</div>
            <div style={{ color: 'var(--text-muted)' }}>Type:</div>
            <div style={{ textTransform: 'capitalize' }}>{activeVerification?.type || '-'}</div>
            <div style={{ color: 'var(--text-muted)' }}>Paths Explored:</div>
            <div>{numPaths}</div>
            <div style={{ color: 'var(--text-muted)' }}>Status:</div>
            <div style={{ color: activeVerification ? 'var(--success)' : 'var(--text-muted)' }}>
              {activeVerification ? 'Verified' : 'Waiting'}
            </div>
          </div>
        </div>

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
          <h4 style={{ fontSize: '0.9rem', marginBottom: '0.8rem', color: 'var(--text-main)' }}>Path Logs</h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem', overflowY: 'auto', flex: 1 }}>
            {!activeVerification ? (
              <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem', textAlign: 'center', marginTop: '2rem' }}>
                Select a structure in the center panel and click "Verify" to view execution paths.
              </span>
            ) : renderedLogs.length > 0 ? (
              renderedLogs.map(({ log, idx, displayName }) => (
                <PathItem
                  key={idx}
                  pathData={log}
                  index={idx}
                  displayName={displayName}
                  activeVerification={activeVerification}
                  compiledData={compiledData}
                />
              ))
            ) : (
              <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem', textAlign: 'center', marginTop: '2rem' }}>
                No paths returned for this verification.
              </span>
            )}
          </div>
        </div>

      </div>
    </>
  );
}
