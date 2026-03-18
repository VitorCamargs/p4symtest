import { useState } from 'react';
import { Activity, ChevronDown, ChevronRight, ArrowRight, CheckCircle2, XCircle, Eye, EyeOff } from 'lucide-react';
import { mockData } from '../lib/mockData';
import { parseConstraint, parseIte, prettyField, prettyComplexConstraint } from '../lib/smt2pretty';

const PathItem = ({ pathData, index, activeVerification }: { pathData: any, index: number, activeVerification: { type: string, name: string } | null }) => {
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
    if (pathData.description?.toLowerCase().includes('drop') || pathData.history?.some((h: string) => h.toLowerCase().includes('drop'))) {
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
          Path {index + 1}
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
              const targetName = activeVerification?.name || '';

              // Replicate backend find_path_to_table:
              // Walk pipeline conditionals to find which one gates this table (true_next == table).
              const allPipelines: any[] = mockData.compiledStructures?.pipelines || [];
              let failedCondition = '';

              for (const pipeline of allPipelines) {
                const gatingNode = (pipeline.conditionals || []).find(
                  (cond: any) => cond.true_next === targetName
                );
                if (gatingNode?.source_info?.source_fragment) {
                  // source_fragment is the original P4 condition string, e.g.
                  // "hdr.ipv4.isValid() && !hdr.myTunnel.isValid()"
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
              <strong style={{ color: 'var(--accent)' }}>Present Headers:</strong><br/>
              <span style={{ color: '#94a3b8' }}>{pathData.present_headers.join(', ')}</span>
            </div>
          )}

          {/* ---- Field Updates: visual ITE decision table ---- */}
          {pathData.field_updates && Object.keys(pathData.field_updates).length > 0 && (
            <FieldUpdatesView updates={pathData.field_updates} />
          )}

          {/* ---- Z3 Constraints: visual badges + raw toggle ---- */}
          {pathData.z3_constraints_smt2 && (
            <Z3ConstraintsView constraints={pathData.z3_constraints_smt2} />
          )}
        </div>
      )}
    </div>
  );
};

// ---- Visual: Field Updates ----
function FieldUpdatesView({ updates }: { updates: Record<string, string> }) {
  const [showRaw, setShowRaw] = useState(false);
  return (
    <div style={{ marginBottom: '1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
        <strong style={{ color: 'var(--accent)', fontSize: '0.8rem' }}>Field Updates</strong>
        <button onClick={() => setShowRaw(r => !r)} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.7rem' }}>
          {showRaw ? <EyeOff size={12} /> : <Eye size={12} />} {showRaw ? 'Visual' : 'Raw SMT2'}
        </button>
      </div>
      {showRaw ? (
        <div style={{ background: '#0a0a0a', padding: '0.8rem', borderRadius: '6px', fontFamily: 'monospace', color: '#10b981', fontSize: '0.7rem', overflowX: 'auto', whiteSpace: 'pre' }}>
          {Object.entries(updates).map(([f, v]) => `${f} = ${v}`).join('\n')}
        </div>
      ) : (
        Object.entries(updates).map(([field, expr]) => {
          const branches = parseIte(expr, field);
          return (
            <div key={field} style={{ marginBottom: '0.8rem', border: '1px solid var(--border)', borderRadius: '6px', overflow: 'hidden' }}>
              <div style={{ background: 'var(--bg-surface)', padding: '0.4rem 0.8rem', borderBottom: '1px solid var(--border)', fontSize: '0.75rem' }}>
                <span style={{ color: 'var(--text-muted)' }}>field</span>{' '}
                <code style={{ color: '#94a3b8', fontFamily: 'monospace' }}>{prettyField(field)}</code>
              </div>
              {branches ? (
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.75rem' }}>
                  <thead>
                    <tr style={{ background: 'rgba(255,255,255,0.03)' }}>
                      <th style={{ padding: '0.3rem 0.8rem', textAlign: 'left', color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.7rem', textTransform: 'uppercase' }}>If</th>
                      <th style={{ padding: '0.3rem 0.8rem', textAlign: 'left', color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.7rem', textTransform: 'uppercase' }}>Then</th>
                    </tr>
                  </thead>
                  <tbody>
                    {branches.map((b, bi) => (
                      <tr key={bi} style={{ borderTop: '1px solid var(--border)', background: b.condition === 'else' ? 'rgba(239,68,68,0.04)' : 'transparent' }}>
                        <td style={{ padding: '0.35rem 0.8rem', fontFamily: 'monospace', color: b.condition === 'else' ? 'var(--text-muted)' : '#fbbf24', fontSize: '0.75rem' }}>{b.condition}</td>
                        <td style={{ padding: '0.35rem 0.8rem', fontFamily: 'monospace', color: '#10b981', fontSize: '0.75rem' }}>{b.result}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div style={{ padding: '0.5rem 0.8rem', color: '#94a3b8', fontSize: '0.75rem', fontFamily: 'monospace' }}>{String(expr)}</div>
              )}
            </div>
          );
        })
      )}
    </div>
  );
}

// ---- Visual: Z3 Constraints ----
const OP_COLORS: Record<string, { bg: string; color: string }> = {
  '==': { bg: 'rgba(34,197,94,0.1)', color: '#22c55e' },
  '!=': { bg: 'rgba(239,68,68,0.1)', color: '#ef4444' },
  'is true': { bg: 'rgba(56,189,248,0.1)', color: '#38bdf8' },
  'is false': { bg: 'rgba(239,68,68,0.08)', color: '#f87171' },
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

import s1MyIngressIpv4LpmFromParserStatesOutput from '../mocks/s1_MyIngress_ipv4_lpm_from_parser_states_output.json';
import deparserOutputFromIpv4LpmFromParserStates from '../mocks/deparser_output_from_s1_MyIngress_ipv4_lpm_from_parser_states_output.json';
import s1MyEgressFromIpv4LpmChainOutput from '../mocks/s1_MyEgress_egress_port_smac_from_s1_MyIngress_ipv4_lpm_from_parser_states_output_output.json';

export default function RightPanel({ activeVerification, executionChain }: {
  activeVerification: { type: string, name: string } | null;
  executionChain: string[];
}) {
  const logs = mockData.executionLogs;

  // Build a chain key from the execution chain for mock selection.
  // Example: ['parser', 'ipv4_lpm'] → 'parser→ipv4_lpm'
  const chainKey = executionChain.join('→');

  const getLogDisplay = () => {
    if (!activeVerification) return null;

    const { type, name } = activeVerification;

    if (type === 'parser') return logs.parserStates;
    if (type === 'deparser') {
      // If previous chain had ipv4_lpm, use the richer deparser mock
      if (chainKey.includes('ipv4_lpm')) return deparserOutputFromIpv4LpmFromParserStates;
      return logs.deparserOutputFromParserStates;
    }
    if (name === 'MyIngress.ipv4_lpm') {
      // Always from parser states when parser was run first
      if (chainKey.includes('parser')) return s1MyIngressIpv4LpmFromParserStatesOutput;
      return logs.s1MyIngressIpv4LpmOutput;
    }
    if (name === 'MyIngress.myTunnel_exact') return logs.s1MyIngressMyTunnelExactOutput;
    if (name === 'MyEgress.egress_port_smac') {
      // Chain: parser → ipv4_lpm → egress  →  IPv4-forwarded paths + 3 missed
      if (chainKey.includes('ipv4_lpm')) return s1MyEgressFromIpv4LpmChainOutput;
      // Chain: parser → myTunnel_exact → egress  →  tunnel-forwarded paths + 2 missed
      if (chainKey.includes('myTunnel_exact')) return logs.s1MyEgressFromMyTunnelChainOutput;
      // Chain: parser → egress only
      return logs.s1MyEgressEgressPortSmacOutput;
    }

    return logs.s1TblDropFromParserStatesOutput;
  };

  const activeLogs = getLogDisplay();
  const numPaths = Array.isArray(activeLogs) ? activeLogs.length : 0;

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
          <div style={{ 
            display: 'flex',
            flexDirection: 'column',
            gap: '0.6rem',
            overflowY: 'auto',
            flex: 1
          }}>
            {!activeVerification ? (
              <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem', textAlign: 'center', marginTop: '2rem' }}>
                Select a structure in the center panel and click "Run Verification" to view execution paths.
              </span>
            ) : (
              Array.isArray(activeLogs) ? (
                activeLogs.map((log, idx) => <PathItem key={idx} pathData={log} index={idx} activeVerification={activeVerification} />)
              ) : (
                <div style={{ background: '#0a0a0a', padding: '1rem', borderRadius: '6px', color: '#94a3b8', fontSize: '0.75rem', fontFamily: 'monospace', overflowX: 'auto' }}>
                  {JSON.stringify(activeLogs, null, 2)}
                </div>
              )
            )}
          </div>
        </div>
      </div>
    </>
  );
}
