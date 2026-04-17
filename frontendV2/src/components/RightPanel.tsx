import { useState, useRef, useEffect, type ReactNode } from 'react';
import { Activity, ChevronDown, ChevronRight, ArrowRight, CheckCircle2, XCircle, Eye, EyeOff, Info } from 'lucide-react';
import { createPortal } from 'react-dom';
import { parseConstraint, prettyField, prettyFieldValue, prettyComplexConstraint } from '../lib/smt2pretty';

// ── PathItem ──────────────────────────────────────────────────────────────────

function normalizeHistoryList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((v) => String(v));
}

function sameHistory(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

function asFieldUpdates(value: unknown): Record<string, string> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
    out[k] = String(v);
  }
  return out;
}

function findParentStateForStage(pathData: any, parentStates: any[], targetName: string | undefined): any | null {
  if (!Array.isArray(parentStates) || !parentStates.length) return null;

  const currentDesc = typeof pathData?.description === 'string' ? pathData.description : '';
  const currentHistory = normalizeHistoryList(pathData?.history);

  const expectedDesc =
    targetName && currentDesc.endsWith(` -> ${targetName}`)
      ? currentDesc.slice(0, -(` -> ${targetName}`).length)
      : currentDesc;

  const expectedHistory =
    targetName && currentHistory[currentHistory.length - 1] === targetName
      ? currentHistory.slice(0, -1)
      : currentHistory;

  const byHistory = parentStates.filter((s) => sameHistory(normalizeHistoryList(s?.history), expectedHistory));
  if (byHistory.length === 1) return byHistory[0];
  if (byHistory.length > 1) {
    const byDesc = byHistory.find((s) => String(s?.description ?? '') === expectedDesc);
    if (byDesc) return byDesc;
    return byHistory[0];
  }

  const byDesc = parentStates.find((s) => String(s?.description ?? '') === expectedDesc);
  return byDesc ?? null;
}

function diffFieldUpdates(current: Record<string, string>, baseline: Record<string, string>): Record<string, string> {
  const delta: Record<string, string> = {};
  for (const [field, value] of Object.entries(current)) {
    if (baseline[field] !== value) {
      delta[field] = value;
    }
  }
  return delta;
}

function stageDisplayName(stage: string | undefined | null): string {
  if (!stage) return 'current_stage';
  const lower = stage.toLowerCase();
  if (lower === 'parser' || lower === 'deparser') return lower;
  return stage.split('.').pop() || stage;
}

function compactText(value: string, max = 92): string {
  if (value.length <= max) return value;
  return `${value.slice(0, max - 3)}...`;
}

function tooltipFieldName(field: string): string {
  const lower = field.toLowerCase();
  if (lower.endsWith('standard_metadata.egress_spec')) return 'port';
  if (lower.endsWith('is_dropped')) return 'is_dropped';
  if (lower.endsWith('.ttl')) return 'ttl';
  if (lower.endsWith('.dstaddr')) return 'dst_addr';
  if (lower.endsWith('.srcaddr')) return 'src_addr';
  return field.replace(/^hdr\./, '');
}

function summarizeChangedVariables(
  updates: Record<string, string>
): string[] {
  const lines: string[] = [];

  for (const [field, expr] of Object.entries(updates)) {
    const values = Array.from(
      new Set(
        collectIteBranches(expr)
          .map((b) => normalizeScalarSymbol(b.result))
          .filter((v) => v !== field)
          .map((v) => normalizeResult(v, field))
          .filter((v) => v && v !== 'none')
      )
    );
    if (!values.length) continue;

    lines.push(`${tooltipFieldName(prettyField(field))}: ${values.join(' | ')}`);
  }

  return lines;
}

function humanizeConstraintLine(raw: string): string | null {
  const smt = raw.trim();
  if (!smt) return null;

  const validMatch = smt.match(/^\(=\s+([a-zA-Z0-9_.$]+)\.\$valid\$\s+#b([01])\)$/);
  if (validMatch) {
    const header = validMatch[1];
    const state = validMatch[2] === '1' ? 'is valid' : 'is invalid';
    return `${prettyField(header)} ${state}`;
  }

  const parsed = parseConstraint(smt);
  if (!parsed.isComplex && parsed.field && parsed.op && parsed.value !== undefined) {
    if (parsed.op === '==') return `${parsed.field} is ${parsed.value}`;
    if (parsed.op === '!=') return `${parsed.field} is not ${parsed.value}`;
    return `${parsed.field} ${parsed.op} ${parsed.value}`;
  }

  if (smt.includes('distinct') && (smt.includes('#b111111111') || smt.includes('#x1ff'))) {
    return 'Packet is not dropped (egress_spec != DROP)';
  }

  const pretty = prettyComplexConstraint(smt).trim();
  if (!pretty || pretty === smt) return null;
  return pretty;
}

function summarizeConstraintList(
  constraints: unknown
): string[] {
  if (!Array.isArray(constraints)) return [];

  const unique: string[] = [];
  const seen = new Set<string>();
  for (const c of constraints) {
    if (typeof c !== 'string') continue;
    const pretty = humanizeConstraintLine(c);
    if (!pretty) continue;
    if (seen.has(pretty)) continue;
    seen.add(pretty);
    unique.push(pretty);
  }

  return unique;
}

function getGatingConditionSource(targetName: string | undefined, compiledData?: any): string | null {
  if (!targetName) return null;
  const allPipelines: any[] = compiledData?.pipelines || [];
  for (const pipeline of allPipelines) {
    const gatingNode = (pipeline.conditionals || []).find(
      (cond: any) => cond.true_next === targetName
    );
    if (gatingNode?.source_info?.source_fragment) {
      return String(gatingNode.source_info.source_fragment);
    }
  }
  return null;
}

function InfoHint({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLSpanElement | null>(null);
  const tooltipRef = useRef<HTMLDivElement | null>(null);
  const [coords, setCoords] = useState<{ left: number; top: number; placement: 'top' | 'bottom' } | null>(null);

  useEffect(() => {
    if (!open) return;

    const updatePosition = () => {
      const trigger = triggerRef.current;
      if (!trigger) return;

      const rect = trigger.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const margin = 12;
      const gap = 8;

      let left = centerX;
      let top = rect.bottom + gap;
      let placement: 'top' | 'bottom' = 'bottom';

      const tip = tooltipRef.current;
      const tipWidth = tip?.offsetWidth ?? 0;
      const tipHeight = tip?.offsetHeight ?? 0;

      if (tipWidth > 0) {
        const minCenter = margin + tipWidth / 2;
        const maxCenter = window.innerWidth - margin - tipWidth / 2;
        left = Math.max(minCenter, Math.min(maxCenter, centerX));
      }

      if (tipHeight > 0 && top + tipHeight + margin > window.innerHeight) {
        const above = rect.top - gap - tipHeight;
        if (above >= margin) {
          top = above;
          placement = 'top';
        }
      }

      setCoords({ left, top, placement });
    };

    const raf1 = requestAnimationFrame(() => {
      updatePosition();
      requestAnimationFrame(updatePosition);
    });

    window.addEventListener('resize', updatePosition);
    window.addEventListener('scroll', updatePosition, true);
    return () => {
      cancelAnimationFrame(raf1);
      window.removeEventListener('resize', updatePosition);
      window.removeEventListener('scroll', updatePosition, true);
    };
  }, [open, text]);

  return (
    <span
      ref={triggerRef}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      tabIndex={0}
      style={{ display: 'inline-flex', alignItems: 'center', color: 'var(--text-muted)', cursor: 'help', position: 'relative', outline: 'none' }}
      aria-label={text}
    >
      <Info size={12} />
      {open && typeof document !== 'undefined' && createPortal(
        <div
          ref={tooltipRef}
          style={{
            position: 'fixed',
            left: coords?.left ?? 0,
            top: coords?.top ?? 0,
            transform: 'translateX(-50%)',
            zIndex: 9999,
            width: 'min(360px, calc(100vw - 24px))',
            padding: '0.45rem 0.55rem',
            borderRadius: '6px',
            border: '1px solid var(--border)',
            background: 'rgba(12, 17, 27, 0.98)',
            color: '#cbd5e1',
            fontSize: '0.68rem',
            lineHeight: 1.4,
            boxShadow: '0 8px 24px rgba(0,0,0,0.35)',
            pointerEvents: 'none',
            whiteSpace: 'pre-line',
          }}
        >
          {text}
        </div>,
        document.body
      )}
    </span>
  );
}

function HoverTextHint({
  text,
  children,
}: {
  text: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLSpanElement | null>(null);
  const tooltipRef = useRef<HTMLDivElement | null>(null);
  const [coords, setCoords] = useState<{ left: number; top: number } | null>(null);

  useEffect(() => {
    if (!open) return;

    const updatePosition = () => {
      const trigger = triggerRef.current;
      if (!trigger) return;

      const rect = trigger.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const margin = 12;
      const gap = 8;

      let left = centerX;
      let top = rect.bottom + gap;
      const tip = tooltipRef.current;
      const tipWidth = tip?.offsetWidth ?? 0;
      const tipHeight = tip?.offsetHeight ?? 0;

      if (tipWidth > 0) {
        const minCenter = margin + tipWidth / 2;
        const maxCenter = window.innerWidth - margin - tipWidth / 2;
        left = Math.max(minCenter, Math.min(maxCenter, centerX));
      }

      if (tipHeight > 0 && top + tipHeight + margin > window.innerHeight) {
        const above = rect.top - gap - tipHeight;
        if (above >= margin) {
          top = above;
        }
      }

      setCoords({ left, top });
    };

    const raf1 = requestAnimationFrame(() => {
      updatePosition();
      requestAnimationFrame(updatePosition);
    });

    window.addEventListener('resize', updatePosition);
    window.addEventListener('scroll', updatePosition, true);
    return () => {
      cancelAnimationFrame(raf1);
      window.removeEventListener('resize', updatePosition);
      window.removeEventListener('scroll', updatePosition, true);
    };
  }, [open, text]);

  return (
    <span
      ref={triggerRef}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      tabIndex={0}
      style={{ display: 'inline-block', width: '100%', cursor: 'help', outline: 'none' }}
      aria-label={text}
    >
      {children}
      {open && typeof document !== 'undefined' && createPortal(
        <div
          ref={tooltipRef}
          style={{
            position: 'fixed',
            left: coords?.left ?? 0,
            top: coords?.top ?? 0,
            transform: 'translateX(-50%)',
            zIndex: 9999,
            width: 'min(620px, calc(100vw - 24px))',
            padding: '0.55rem 0.65rem',
            borderRadius: '6px',
            border: '1px solid var(--border)',
            background: 'rgba(12, 17, 27, 0.98)',
            color: '#cbd5e1',
            fontSize: '0.7rem',
            lineHeight: 1.45,
            boxShadow: '0 8px 24px rgba(0,0,0,0.35)',
            pointerEvents: 'none',
            whiteSpace: 'pre-line',
          }}
        >
          {text}
        </div>,
        document.body
      )}
    </span>
  );
}

const PathItem = ({
  pathData,
  index,
  displayName,
  activeVerification,
  compiledData,
  parentStates,
}: {
  pathData: any;
  index: number;
  displayName?: string;
  activeVerification: { type: string; name: string } | null;
  compiledData?: any;
  parentStates?: any[];
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

  const reachedSelectedStage =
    targetType === 'parser' ||
    targetType === 'deparser' ||
    (!!targetName && Array.isArray(pathData.history) && pathData.history.includes(targetName));

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

  const currentUpdates = asFieldUpdates(pathData.field_updates);
  const parentState = findParentStateForStage(pathData, parentStates ?? [], targetName);
  const parentUpdates = asFieldUpdates(parentState?.field_updates);
  const stageLabel = targetName ?? activeVerification?.type ?? 'current stage';
  const gatingCondition = getGatingConditionSource(targetName, compiledData);

  const stageUpdates =
    reachedSelectedStage
      ? (parentState ? diffFieldUpdates(currentUpdates, parentUpdates) : currentUpdates)
      : {};
  const hasStageUpdates = Object.keys(stageUpdates).length > 0;
  const shouldRenderStageBlock = hasStageUpdates || reachedSelectedStage || Object.keys(currentUpdates).length > 0;
  const inheritedConditionSummary = summarizeConstraintList(
    parentState?.z3_constraints_smt2 ?? pathData.z3_constraints_smt2
  );
  const parentStageName = stageDisplayName(parentState?.history?.[parentState.history.length - 1]);
  const parentChangedVariables = summarizeChangedVariables(parentUpdates);
  const currentChangedVariables = summarizeChangedVariables(stageUpdates);
  const stackedReachBaseConditions = (() => {
    const lines: string[] = [];
    if (gatingCondition) lines.push(`To reach this stage: ${gatingCondition}`);
    inheritedConditionSummary.forEach((line) => {
      if (!lines.includes(line)) lines.push(line);
    });
    return lines;
  })();

  const stageInfoTooltip = (() => {
    const lines: string[] = [];
    if (parentState && parentChangedVariables.length) {
      lines.push(`${parentStageName}:`);
      parentChangedVariables.forEach((line) => lines.push(line));
    }
    if (currentChangedVariables.length) {
      lines.push(`${stageDisplayName(stageLabel)}:`);
      currentChangedVariables.forEach((line) => lines.push(line));
    }
    if (!lines.length) {
      lines.push('No variables changed in this execution stage.');
    }
    return lines.join('\n');
  })();

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

          {shouldRenderStageBlock && (
            hasStageUpdates ? (
              <FieldUpdatesView
                updates={stageUpdates}
                stageLabel={stageLabel}
                infoTooltip={stageInfoTooltip}
                baseReachConditions={stackedReachBaseConditions}
              />
            ) : (
                <div style={{ marginBottom: '1rem', padding: '0.7rem 0.8rem', border: '1px solid var(--border)', borderRadius: '6px', background: 'rgba(255,255,255,0.02)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.25rem' }}>
                  <strong style={{ color: 'var(--accent)', fontSize: '0.8rem' }}>Field Updates (Current Stage)</strong>
                  <InfoHint text={stageInfoTooltip} />
                </div>
                <span style={{ color: 'var(--text-muted)', fontSize: '0.74rem' }}>
                  No field updates generated at this stage for this path.
                </span>
              </div>
            )
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

function parseBitVecLiteral(lit: string): { value: bigint; width: number } | null {
  if (typeof lit !== 'string') return null;
  if (lit.startsWith('#x')) {
    const hex = lit.slice(2);
    if (!hex) return null;
    try {
      return { value: BigInt(`0x${hex}`), width: hex.length * 4 };
    } catch {
      return null;
    }
  }
  if (lit.startsWith('#b')) {
    const bin = lit.slice(2);
    if (!bin || /[^01]/.test(bin)) return null;
    try {
      return { value: BigInt(`0b${bin}`), width: bin.length };
    } catch {
      return null;
    }
  }
  return null;
}

function ipv4FromBitVecLiteral(lit: string): string | null {
  const parsed = parseBitVecLiteral(lit);
  if (!parsed || parsed.width !== 32) return null;
  const value = parsed.value & 0xffff_ffffn;
  const a = Number((value >> 24n) & 0xffn);
  const b = Number((value >> 16n) & 0xffn);
  const c = Number((value >> 8n) & 0xffn);
  const d = Number(value & 0xffn);
  return `${a}.${b}.${c}.${d}`;
}

function toBitVecLiteral(value: bigint, width: number): string {
  if (width <= 0) return '#x0';
  if (width % 4 === 0) {
    const digits = Math.ceil(width / 4);
    return `#x${value.toString(16).padStart(digits, '0')}`;
  }
  return `#b${value.toString(2).padStart(width, '0')}`;
}

function liftExtractLiteralToField(hi: number, lo: number, extractedLiteral: string): string | null {
  if (!Number.isFinite(hi) || !Number.isFinite(lo) || hi < lo || lo < 0) return null;
  const parsed = parseBitVecLiteral(extractedLiteral);
  if (!parsed) return null;

  const extractWidth = hi - lo + 1;
  const fullWidth = hi + 1;
  if (extractWidth <= 0 || fullWidth <= 0) return null;

  const extractMask = (1n << BigInt(extractWidth)) - 1n;
  const normalized = parsed.value & extractMask;
  const lifted = normalized << BigInt(lo);
  return toBitVecLiteral(lifted, fullWidth);
}

function parseIpv4PrefixExtract(
  hi: number,
  lo: number,
  field: string,
  rhsLiteral: string,
): { ip: string; prefix: number } | null {
  const f = field.toLowerCase();
  const isIpv4Field =
    f.includes('ipv4.') && (f.includes('dstaddr') || f.includes('srcaddr') || f.includes('ipaddr'));
  if (!isIpv4Field) return null;
  if (!Number.isFinite(hi) || !Number.isFinite(lo) || hi !== 31 || lo < 0 || lo > 31 || hi < lo) return null;

  const prefix = 32 - lo;
  if (prefix <= 0 || prefix > 32) return null;

  const lifted = liftExtractLiteralToField(hi, lo, rhsLiteral);
  if (!lifted) return null;
  const ip = ipv4FromBitVecLiteral(lifted);
  if (!ip) return null;
  return { ip, prefix };
}

function escapeRegex(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function replaceSExprSymbol(input: string, symbol: string, replacement: string): string {
  const escaped = escapeRegex(symbol);
  const re = new RegExp(`(^|[\\s()])${escaped}(?=($|[\\s()]))`, 'g');
  return input.replace(re, `$1${replacement}`);
}

function canonicalizeSExpr(expr: string): string {
  const trimmed = expr.trim();
  if (!trimmed) return '';
  if (!(trimmed.startsWith('(') && trimmed.endsWith(')'))) {
    return trimmed.replace(/\s+/g, ' ');
  }
  const inner = trimmed.slice(1, -1).trim();
  const tokens = splitSmtTokens(inner);
  if (!tokens.length) return '()';
  return `(${tokens.map((t) => canonicalizeSExpr(t)).join(' ')})`;
}

function inlineLetBindings(expr: string): string {
  let current = expr.trim();
  let guard = 0;

  while (guard < 24 && current.startsWith('(let ') && current.endsWith(')')) {
    const inner = current.slice(1, -1).trim();
    const tokens = splitSmtTokens(inner);
    if (tokens.length < 3 || tokens[0] !== 'let') break;

    const bindingsExpr = tokens[1];
    let body = tokens.slice(2).join(' ').trim();
    if (!(bindingsExpr.startsWith('(') && bindingsExpr.endsWith(')'))) break;

    const bindingItems = splitSmtTokens(bindingsExpr.slice(1, -1).trim());
    const bindings: Array<{ name: string; value: string }> = [];
    for (const item of bindingItems) {
      if (!(item.startsWith('(') && item.endsWith(')'))) continue;
      const pair = splitSmtTokens(item.slice(1, -1).trim());
      if (pair.length < 2) continue;
      bindings.push({ name: pair[0], value: pair.slice(1).join(' ') });
    }

    for (const { name, value } of bindings) {
      const resolved = inlineLetBindings(value);
      body = replaceSExprSymbol(body, name, resolved);
    }

    current = body;
    guard++;
  }

  return current;
}

function conditionToAtoms(condition: string): Set<string> {
  const atoms = new Set<string>();

  const walk = (expr: string) => {
    const normalized = canonicalizeSExpr(expr);
    if (!normalized || normalized === 'Always') return;
    if (!(normalized.startsWith('(') && normalized.endsWith(')'))) {
      atoms.add(normalized);
      return;
    }

    const tokens = splitSmtTokens(normalized.slice(1, -1).trim());
    if (!tokens.length) return;
    if (tokens[0] === 'and' && tokens.length > 1) {
      tokens.slice(1).forEach((t) => walk(t));
      return;
    }
    atoms.add(normalized);
  };

  walk(condition);
  return atoms;
}

function joinConditions(pathConditions: string[]): string {
  const normalized = pathConditions.map((c) => canonicalizeSExpr(c)).filter(Boolean);
  if (!normalized.length) return 'Always';
  if (normalized.length === 1) return normalized[0];
  return `(and ${normalized.join(' ')})`;
}

function isSubset(subset: Set<string>, superset: Set<string>): boolean {
  for (const atom of subset) {
    if (!superset.has(atom)) return false;
  }
  return true;
}

type TriBool = 'true' | 'false' | 'unknown';

function buildTruthMapFromCondition(condition: string): Map<string, boolean> {
  const truth = new Map<string, boolean>();
  const atoms = conditionToAtoms(condition);

  for (const atom of atoms) {
    const normalized = canonicalizeSExpr(atom);
    if (!normalized) continue;
    if (normalized.startsWith('(not ') && normalized.endsWith(')')) {
      const tokens = splitSmtTokens(normalized.slice(1, -1).trim());
      if (tokens[0] === 'not' && tokens.length >= 2) {
        const inner = canonicalizeSExpr(tokens[1]);
        if (inner) truth.set(inner, false);
      }
      truth.set(normalized, true);
      continue;
    }

    truth.set(normalized, true);
    const neg = canonicalizeSExpr(`(not ${normalized})`);
    if (neg) truth.set(neg, false);
  }

  return truth;
}

function evalConditionWithTruth(condition: string, truth: Map<string, boolean>): TriBool {
  const normalized = canonicalizeSExpr(condition);
  if (!normalized || normalized === 'Always') return 'true';

  const direct = truth.get(normalized);
  if (direct === true) return 'true';
  if (direct === false) return 'false';

  if (!(normalized.startsWith('(') && normalized.endsWith(')'))) return 'unknown';
  const tokens = splitSmtTokens(normalized.slice(1, -1).trim());
  if (!tokens.length) return 'unknown';

  const op = tokens[0];
  if (op === 'not' && tokens.length >= 2) {
    const inner = evalConditionWithTruth(tokens[1], truth);
    if (inner === 'true') return 'false';
    if (inner === 'false') return 'true';
    return 'unknown';
  }

  if (op === 'and' && tokens.length >= 2) {
    let hasUnknown = false;
    for (let i = 1; i < tokens.length; i++) {
      const r = evalConditionWithTruth(tokens[i], truth);
      if (r === 'false') return 'false';
      if (r === 'unknown') hasUnknown = true;
    }
    return hasUnknown ? 'unknown' : 'true';
  }

  if (op === 'or' && tokens.length >= 2) {
    let hasUnknown = false;
    for (let i = 1; i < tokens.length; i++) {
      const r = evalConditionWithTruth(tokens[i], truth);
      if (r === 'true') return 'true';
      if (r === 'unknown') hasUnknown = true;
    }
    return hasUnknown ? 'unknown' : 'false';
  }

  return 'unknown';
}

type EqBitConstraint = {
  field: string;
  bits: Map<number, 0 | 1>;
};

function bitsFromLiteral(value: bigint, width: number, offset = 0): Map<number, 0 | 1> {
  const bits = new Map<number, 0 | 1>();
  if (width <= 0) return bits;
  const mask = (1n << BigInt(width)) - 1n;
  const normalized = value & mask;
  for (let i = 0; i < width; i++) {
    const bit = Number((normalized >> BigInt(i)) & 1n) as 0 | 1;
    bits.set(offset + i, bit);
  }
  return bits;
}

function parseEqBitConstraint(expr: string): EqBitConstraint | null {
  const normalized = canonicalizeSExpr(expr);
  if (!(normalized.startsWith('(') && normalized.endsWith(')'))) return null;
  const tokens = splitSmtTokens(normalized.slice(1, -1).trim());
  if (tokens[0] !== '=' || tokens.length < 3) return null;

  const lhs = tokens[1];
  const rhs = tokens[2];
  const parsed = parseBitVecLiteral(rhs);
  if (!parsed) return null;

  if (/^[a-zA-Z0-9_.$]+$/.test(lhs)) {
    return {
      field: lhs,
      bits: bitsFromLiteral(parsed.value, parsed.width, 0),
    };
  }

  const extractMatch = lhs.match(/^\(\(_ extract (\d+) (\d+)\)\s+([a-zA-Z0-9_.$]+)\)$/);
  if (!extractMatch) return null;

  const hi = Number(extractMatch[1]);
  const lo = Number(extractMatch[2]);
  const field = extractMatch[3];
  if (!Number.isFinite(hi) || !Number.isFinite(lo) || hi < lo || lo < 0) return null;

  const width = hi - lo + 1;
  return {
    field,
    bits: bitsFromLiteral(parsed.value, width, lo),
  };
}

function constraintsConflict(a: EqBitConstraint, b: EqBitConstraint): boolean {
  if (a.field !== b.field) return false;
  for (const [pos, abit] of a.bits.entries()) {
    const bbit = b.bits.get(pos);
    if (bbit !== undefined && bbit !== abit) return true;
  }
  return false;
}

function exprDefinitelyFalseByPositiveConflicts(
  expr: string,
  positiveConstraints: EqBitConstraint[]
): boolean {
  const normalized = canonicalizeSExpr(expr);
  if (!normalized || normalized === 'Always') return false;

  const eqConstraint = parseEqBitConstraint(normalized);
  if (eqConstraint) {
    return positiveConstraints.some((pos) => constraintsConflict(pos, eqConstraint));
  }

  if (!(normalized.startsWith('(') && normalized.endsWith(')'))) return false;
  const tokens = splitSmtTokens(normalized.slice(1, -1).trim());
  if (!tokens.length) return false;

  if (tokens[0] === 'and' && tokens.length > 1) {
    return tokens.slice(1).some((t) =>
      exprDefinitelyFalseByPositiveConflicts(t, positiveConstraints)
    );
  }

  if (tokens[0] === 'or' && tokens.length > 1) {
    return tokens.slice(1).every((t) =>
      exprDefinitelyFalseByPositiveConflicts(t, positiveConstraints)
    );
  }

  return false;
}

function simplifyDisplayCondition(condition: string): string {
  const normalized = canonicalizeSExpr(condition);
  if (!normalized || normalized === 'Always') return 'Always';
  if (!(normalized.startsWith('(') && normalized.endsWith(')'))) return normalized;

  const tokens = splitSmtTokens(normalized.slice(1, -1).trim());
  if (tokens[0] !== 'and' || tokens.length <= 2) return normalized;

  const conjuncts = tokens.slice(1).map((c) => canonicalizeSExpr(c));
  const positiveConstraints = conjuncts
    .filter((c) => !c.startsWith('(not '))
    .map((c) => parseEqBitConstraint(c))
    .filter((c): c is EqBitConstraint => c !== null);

  const kept: string[] = [];
  for (const conj of conjuncts) {
    if (conj.startsWith('(not ') && conj.endsWith(')')) {
      const innerTokens = splitSmtTokens(conj.slice(1, -1).trim());
      if (innerTokens[0] === 'not' && innerTokens.length >= 2) {
        const inner = canonicalizeSExpr(innerTokens[1]);
        const negConstraint = parseEqBitConstraint(inner);
        if (negConstraint) {
          const redundant = positiveConstraints.some((pos) => constraintsConflict(pos, negConstraint));
          if (redundant) continue;
        }

        // Handle composite negations like:
        // (not (and A B)) and A and C, where C conflicts with B.
        // In this case the negated conjunct is always true and can be removed.
        if (exprDefinitelyFalseByPositiveConflicts(inner, positiveConstraints)) {
          continue;
        }
      }
    }
    kept.push(conj);
  }

  if (!kept.length) return 'Always';
  if (kept.length === 1) return kept[0];
  return `(and ${kept.join(' ')})`;
}

function prettyBranchConditionLabel(
  simplifiedCondition: string,
  rowIndex: number,
  totalRows: number
): string {
  const canonical = canonicalizeSExpr(simplifiedCondition);
  const lastRow = rowIndex === totalRows - 1;

  if (!canonical || canonical === 'Always') {
    return totalRows > 1 && lastRow ? 'else' : 'Always';
  }

  if (!(canonical.startsWith('(') && canonical.endsWith(')'))) {
    return prettyCondition(canonical);
  }

  const tokens = splitSmtTokens(canonical.slice(1, -1).trim());
  if (!tokens.length) return prettyCondition(canonical);

  if (tokens[0] === 'not' && tokens.length >= 2) {
    if (lastRow) return 'else';
    return `else if ${prettyCondition(tokens[1])}`;
  }

  if (tokens[0] === 'and' && tokens.length > 1) {
    const atoms = tokens.slice(1).map((t) => canonicalizeSExpr(t)).filter(Boolean);
    const positives = atoms.filter((a) => !a.startsWith('(not '));
    const negatives = atoms.filter((a) => a.startsWith('(not '));

    if (lastRow && positives.length === 0 && negatives.length > 0) {
      return 'else';
    }

    if (positives.length >= 1 && negatives.length >= 1) {
      const body =
        positives.length === 1
          ? prettyCondition(positives[0])
          : positives.map((p) => prettyCondition(p)).join(' AND ');
      return `else if ${body}`;
    }
  }

  return prettyCondition(canonical);
}

function branchScore(branches: FieldBranch[]): number {
  if (!branches.length) return Number.NEGATIVE_INFINITY;
  const unique = new Map<string, FieldBranch>();
  branches.forEach((b) => {
    if (!unique.has(b.conditionKey)) unique.set(b.conditionKey, b);
  });
  const normalized = Array.from(unique.values());
  const meaningful = normalized.filter((b) => b.conditionKey !== 'Always');
  if (!meaningful.length && normalized.length <= 1) return Number.NEGATIVE_INFINITY;

  const totalAtomCount = normalized.reduce((acc, b) => acc + b.atomCount, 0);
  const orPenalty = normalized.reduce((acc, b) => {
    if (b.conditionKey.includes('(or ')) return acc + 30;
    if (b.conditionKey.includes('(not (or ')) return acc + 20;
    return acc;
  }, 0);

  return normalized.length * 100 + totalAtomCount - orPenalty;
}

function normalizeScalarSymbol(expr: string): string {
  let trimmed = expr.trim();
  let guard = 0;
  while (guard < 8 && trimmed.startsWith('(') && trimmed.endsWith(')')) {
    const inner = trimmed.slice(1, -1).trim();
    if (!inner || /[\s()]/.test(inner)) break;
    trimmed = inner;
    guard++;
  }
  return trimmed;
}

type FieldBranch = {
  condition: string;
  conditionKey: string;
  atoms: Set<string>;
  atomCount: number;
  result: string;
};

function collectIteBranches(expr: string): FieldBranch[] {
  const branches: Array<{ condition: string; result: string }> = [];
  const expanded = inlineLetBindings(expr);

  const walk = (node: string, pathConditions: string[]) => {
    const trimmed = node.trim();
    if (trimmed.startsWith('(') && trimmed.endsWith(')')) {
      const tokens = splitSmtTokens(trimmed.slice(1, -1).trim());
      if (tokens[0] === 'ite' && tokens.length >= 4) {
        const cond = tokens[1];
        const thenExpr = tokens[2];
        const elseExpr = tokens.slice(3).join(' ');
        walk(thenExpr, [...pathConditions, cond]);
        walk(elseExpr, [...pathConditions, `(not ${cond})`]);
        return;
      }
    }

    branches.push({
      condition: joinConditions(pathConditions),
      result: trimmed,
    });
  };

  walk(expanded, []);

  return branches.map((branch) => {
    const conditionKey = canonicalizeSExpr(branch.condition);
    const atoms = conditionToAtoms(conditionKey);
    return {
      ...branch,
      conditionKey,
      atoms,
      atomCount: atoms.size,
    };
  });
}

function prettyCondition(condition: string): string {
  const normalized = canonicalizeSExpr(condition);
  if (!normalized || normalized === 'Always') return 'Always';
  if (!(normalized.startsWith('(') && normalized.endsWith(')')) ) return normalized;

  const tokens = splitSmtTokens(normalized.slice(1, -1).trim());
  if (!tokens.length) return normalized;

  const op = tokens[0];
  if ((op === 'and' || op === 'or') && tokens.length > 1) {
    const sep = op === 'and' ? ' AND ' : ' OR ';
    return tokens.slice(1).map((t) => prettyCondition(t)).join(sep);
  }

  if (op === 'not' && tokens.length >= 2) {
    return `NOT (${prettyCondition(tokens[1])})`;
  }

  if (op === '=' && tokens.length >= 3) {
    const lhs = tokens[1];
    const rhs = tokens[2];

    const extractMatch = lhs.match(/^\(\(_ extract (\d+) (\d+)\)\s+([a-zA-Z0-9_.$]+)\)$/);
    if (extractMatch) {
      const hi = Number(extractMatch[1]);
      const lo = Number(extractMatch[2]);
      const field = extractMatch[3];
      const maybePrefix = parseIpv4PrefixExtract(hi, lo, field, rhs);
      if (maybePrefix) {
        if (maybePrefix.prefix === 32) {
          return `${prettyField(field)} == ${maybePrefix.ip}`;
        }
        return `${prettyField(field)} in ${maybePrefix.ip}/${maybePrefix.prefix}`;
      }

      if (hi === lo) {
        const bit = parseBitVecLiteral(rhs);
        const bitValue = bit && bit.width === 1 ? (bit.value === 0n ? '0' : '1') : rhs;
        return `${prettyField(field)}[${hi}] == ${bitValue}`;
      }

      const lifted = liftExtractLiteralToField(hi, lo, rhs);
      if (lifted) {
        return `${prettyField(field)}[${hi}:${lo}] == ${prettyFieldValue(lifted, field)}`;
      }

      return `${prettyField(field)}[${hi}:${lo}] == ${rhs}`;
    }

    if (/^[a-zA-Z0-9_.$]+$/.test(lhs)) {
      return `${prettyField(lhs)} == ${prettyFieldValue(rhs, lhs)}`;
    }
  }

  return normalized;
}

function prettyExtractIte(res: string, targetField: string): string | null {
  const m = res.match(/^\(ite\s+\(=\s+\(\(_ extract (\d+) (\d+)\)\s+([a-zA-Z0-9_.$]+)\)\s+(#[xb][0-9a-fA-F]+)\)\s+(#[xb][0-9a-fA-F]+)\s+(#[xb][0-9a-fA-F]+)\)$/);
  if (!m) return null;

  const hi = Number(m[1]);
  const lo = Number(m[2]);
  const sourceField = m[3];
  const condValue = m[4];
  const thenValue = m[5];
  const elseValue = m[6];
  const maybePrefix = parseIpv4PrefixExtract(hi, lo, sourceField, condValue);
  if (maybePrefix) {
    const condExpr = maybePrefix.prefix === 32
      ? `${prettyField(sourceField)} == ${maybePrefix.ip}`
      : `${prettyField(sourceField)} in ${maybePrefix.ip}/${maybePrefix.prefix}`;
    return `if ${condExpr} then ${prettyFieldValue(thenValue, targetField)} else ${prettyFieldValue(elseValue, targetField)}`;
  }

  const liftedCond = liftExtractLiteralToField(hi, lo, condValue);
  const condPretty = liftedCond ? prettyFieldValue(liftedCond, sourceField) : prettyFieldValue(condValue, sourceField);
  return `if ${prettyField(sourceField)}[${hi}:${lo}] == ${condPretty} then ${prettyFieldValue(thenValue, targetField)} else ${prettyFieldValue(elseValue, targetField)}`;
}

function normalizeResult(res: string, targetField: string): string {
  const itePretty = prettyExtractIte(res, targetField);
  if (itePretty) return itePretty;

  const trimmed = res.trim();
  const isAtomicToken =
    trimmed.length > 0 &&
    !trimmed.includes('(') &&
    !trimmed.includes(')') &&
    !/\s/.test(trimmed);

  let r = (trimmed.startsWith('#') || isAtomicToken)
    ? prettyFieldValue(trimmed, targetField)
    : trimmed;
  if (r.includes('(bvadd #xff ')) {
    const m = r.match(/\(bvadd #xff\s+([a-zA-Z0-9_.$]+)\)/);
    if (m) r = `${prettyField(m[1])} - 1`;
  }
  return r;
}

export type FieldUpdateRow = {
  label: string;
  isElse?: boolean;
  stackedReachLines: string[];
  stackedReachCompact: string;
  cells: string[];
};

export function buildFieldUpdateRows(
  updates: Record<string, string>,
  baseReachConditions: string[] = []
): FieldUpdateRow[] {
  const rawFields = Object.keys(updates);
  if (!rawFields.length) return [];

  const branchesByField = new Map<string, FieldBranch[]>();
  const conditionOrder: string[] = [];
  const conditionInfo = new Map<string, { raw: string; atoms: Set<string> }>();

  rawFields.forEach((field) => {
    const branches = collectIteBranches(updates[field]);
    branchesByField.set(field, branches);
  });

  const pivotField = rawFields.reduce((best, field) => {
    if (!best) return field;
    const bestScore = branchScore(branchesByField.get(best) || []);
    const fieldScore = branchScore(branchesByField.get(field) || []);
    return fieldScore > bestScore ? field : best;
  }, rawFields[0] || '');

  const pivotBranchesRaw = branchesByField.get(pivotField) || [];
  const seenPivot = new Set<string>();
  const pivotBranches = pivotBranchesRaw.filter((b) => {
    if (seenPivot.has(b.conditionKey)) return false;
    seenPivot.add(b.conditionKey);
    return true;
  });

  pivotBranches.forEach((branch) => {
    conditionInfo.set(branch.conditionKey, { raw: branch.condition, atoms: branch.atoms });
    conditionOrder.push(branch.conditionKey);
  });

  return conditionOrder.map((conditionKey, rowIndex) => {
    const info = conditionInfo.get(conditionKey)!;
    const rowAtoms = info.atoms;
    const rowTruth = buildTruthMapFromCondition(conditionKey);

    const cells = rawFields.map((field) => {
      const candidates = branchesByField.get(field) || [];
      const exact = candidates.find((c) => c.conditionKey === conditionKey);

      let selected = exact;
      if (!selected) {
        selected = candidates
          .filter((c) => evalConditionWithTruth(c.conditionKey, rowTruth) === 'true')
          .sort((a, b) => b.atomCount - a.atomCount)[0];
      }
      if (!selected) {
        selected = candidates
          .filter((c) => c.conditionKey === 'Always' || isSubset(c.atoms, rowAtoms))
          .sort((a, b) => b.atomCount - a.atomCount)[0];
      }

      if (!selected) return 'none';
      const scalar = normalizeScalarSymbol(selected.result);
      if (scalar === field) return 'none';
      return normalizeResult(scalar, field);
    });

    const simplified = simplifyDisplayCondition(info.raw);
    const normalizedLabel = prettyBranchConditionLabel(simplified, rowIndex, conditionOrder.length);
    const isElse = normalizedLabel.toLowerCase().startsWith('else') || normalizedLabel === 'Always';
    const stackedReachLines = (() => {
      const lines: string[] = [];
      lines.push('Inherited reach conditions:');
      if (baseReachConditions.length) {
        baseReachConditions.forEach((line) => lines.push(`- ${line}`));
      } else {
        lines.push('- none');
      }
      return lines;
    })();
    const stackedReachCompact = compactText(
      `${baseReachConditions.length ? `${baseReachConditions.length} cond.` : 'none'}`,
      14
    );

    return {
      label: normalizedLabel,
      isElse,
      stackedReachLines,
      stackedReachCompact,
      cells,
    };
  });
}

function FieldUpdatesView({
  updates,
  stageLabel,
  infoTooltip,
  baseReachConditions = [],
}: {
  updates: Record<string, string>;
  stageLabel?: string;
  infoTooltip?: string;
  baseReachConditions?: string[];
}) {
  const [showRaw, setShowRaw] = useState(false);
  const columns = Object.keys(updates).map(k => prettyField(k));
  const rows: FieldUpdateRow[] = showRaw ? [] : buildFieldUpdateRows(updates, baseReachConditions);

  return (
    <div style={{ marginBottom: '1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.8rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <strong style={{ color: 'var(--accent)', fontSize: '0.8rem' }}>Field Updates (Current Stage)</strong>
          {infoTooltip && (
            <InfoHint text={infoTooltip} />
          )}
          {stageLabel && (
            <span style={{ color: 'var(--text-muted)', fontSize: '0.68rem', fontFamily: 'monospace' }}>
              {stageLabel}
            </span>
          )}
        </div>
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
                <th colSpan={columns.length + 2} style={{ padding: '0.6rem 0.8rem', textAlign: 'center', color: 'var(--text-main)', fontSize: '0.75rem', fontWeight: 600 }}>
                  <code style={{ color: '#38bdf8', fontFamily: 'monospace', fontWeight: 700, background: 'transparent', fontSize: '0.8rem' }}>Conditions</code>
                </th>
              </tr>
              <tr style={{ background: 'rgba(255,255,255,0.03)', borderBottom: '1px solid var(--border)' }}>
                <th style={{ padding: '0.35rem 0.5rem', textAlign: 'left', color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.7rem', borderRight: '1px solid var(--border)', width: '96px', minWidth: '96px', maxWidth: '110px', whiteSpace: 'nowrap' }}>
                  Reach
                </th>
                <th style={{ padding: '0.4rem 0.8rem', textAlign: 'left', color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.7rem', borderRight: '1px solid var(--border)', width: '15%' }}>
                  Row Condition
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
                  <td style={{ padding: '0.35rem 0.5rem', borderRight: '1px solid var(--border)', width: '96px', minWidth: '96px', maxWidth: '110px' }}>
                    <HoverTextHint text={row.stackedReachLines.join('\n')}>
                      <span
                        style={{
                          display: 'block',
                          fontFamily: 'monospace',
                          color: '#93c5fd',
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          fontSize: '0.72rem',
                        }}
                      >
                        {row.stackedReachCompact}
                      </span>
                    </HoverTextHint>
                  </td>
                  <td style={{ padding: '0.4rem 0.8rem', borderRight: '1px solid var(--border)', fontFamily: 'monospace', color: row.isElse ? 'var(--text-muted)' : '#fbbf24', fontWeight: row.isElse ? 400 : 700, whiteSpace: 'normal', minWidth: '260px' }}>
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
  const parsed = (() => {
    const seen = new Set<string>();
    const out: ReturnType<typeof parseConstraint>[] = [];
    for (const raw of constraints) {
      const p = parseConstraint(raw);
      const key = !p.isComplex && p.field && p.op
        ? `${p.field}|${p.op}|${String(p.value ?? '')}`
        : prettyComplexConstraint(p.original).trim().replace(/\s+/g, ' ');
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(p);
    }
    return out;
  })();
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
  parentVerificationResult,
  compiledData,
}: {
  activeVerification: { type: string; name: string } | null;
  verificationResult: any;
  parentVerificationResult?: any;
  compiledData?: any;
}) {
  const activeLogs: any[] = Array.isArray(verificationResult) ? verificationResult : [];
  const parentStates: any[] = Array.isArray(parentVerificationResult) ? parentVerificationResult : [];
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
                  parentStates={parentStates}
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
