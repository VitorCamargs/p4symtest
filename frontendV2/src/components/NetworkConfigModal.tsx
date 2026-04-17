import { useState, useEffect, Fragment } from 'react';
import { X, Plus, Trash2, Router, Network, ChevronDown, ChevronRight } from 'lucide-react';
import type { TableSchema, TableAction, TableKey } from '../lib/api';

// ── Types ─────────────────────────────────────────────────────────────────────

/** One row in a table: a set of match values (keyed by field name) + chosen action + its params. */
export interface TableEntry {
  match: Record<string, string>;   // field → value string (e.g. "10.0.0.1" for LPM)
  matchMask?: Record<string, string>; // field → mask string (ternary only)
  matchPrefix?: Record<string, number>; // field → prefix len (lpm only)
  action: string;
  action_params: Record<string, string>; // param name → value string
}

/** Per-switch config: a map from table name to list of entries. */
export type SwitchTableConfig = Record<string, TableEntry[]>;
export type ExecutionMode = 'auto_concrete' | 'full_symbolic';

export interface NetworkConfig {
  numSwitches: number;
  switches: Array<{ id: string; tables: SwitchTableConfig }>;
}

// ── CSS helpers ───────────────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  background: 'var(--bg-dark)', border: '1px solid var(--border)',
  color: 'var(--text-main)', padding: '0.35rem 0.5rem', borderRadius: '4px',
  fontSize: '0.78rem', width: '100%', fontFamily: 'monospace',
};
const cellStyle: React.CSSProperties = { padding: '0.3rem 0.4rem', verticalAlign: 'middle' };
const btnBase: React.CSSProperties = {
  background: 'transparent', border: 'none', cursor: 'pointer', display: 'flex',
};

// ── Header row generator ──────────────────────────────────────────────────────

function isMappableField(fieldName: string): boolean {
  const f = fieldName.toLowerCase();
  return (
    f.includes('addr') || f.includes('ip') || f.includes('mac') ||
    f.includes('port') || f.includes('spec') || f.includes('egress') ||
    f.includes('tunnel') || f.includes('id') || f.includes('prefix') ||
    f.includes('class')
  );
}

function colsForSchema(schema: TableSchema): string[] {
  const matchCols: string[] = [];
  schema.keys.forEach(k => {
    if (!isMappableField(k.field)) return;
    matchCols.push(k.field);
    if (k.match_type === 'lpm') matchCols.push(`${k.field}/prefix`);
    if (k.match_type === 'ternary') matchCols.push(`${k.field}/mask`);
  });
  
  return [...matchCols, 'Action & Parameters'];
}

function isSymbolicToken(v: string): boolean {
  const t = v.trim().toLowerCase();
  return t === '' || t === 'symbolic' || t === 'sym' || t === '__symbolic__' || t === '*' || t === 'auto' || t === 'default';
}

function isIpv4(v: string): boolean {
  const m = v.trim().match(/^(\d{1,3})(\.\d{1,3}){3}$/);
  if (!m) return false;
  return v.trim().split('.').every((p) => {
    const n = Number(p);
    return Number.isFinite(n) && n >= 0 && n <= 255;
  });
}

function prefixToIpv4Mask(prefix: number): string {
  const p = Math.max(0, Math.min(32, Math.trunc(prefix)));
  const parts: number[] = [];
  for (let i = 0; i < 4; i++) {
    const rem = Math.max(0, Math.min(8, p - i * 8));
    const octet = rem === 0 ? 0 : (0xff << (8 - rem)) & 0xff;
    parts.push(octet);
  }
  return parts.join('.');
}

function parseIpv4Cidr(v: string): { ip: string; prefix: number } | null {
  const m = v.trim().match(/^(\d{1,3}(?:\.\d{1,3}){3})\/(\d{1,2})$/);
  if (!m) return null;
  const ip = m[1];
  const prefix = Number(m[2]);
  if (!isIpv4(ip) || !Number.isFinite(prefix) || prefix < 0 || prefix > 32) return null;
  return { ip, prefix };
}

function inferTernaryMask(field: string, value: string): string {
  const f = field.toLowerCase();
  const raw = value.trim();
  if (isSymbolicToken(raw)) return '0.0.0.0';

  const cidr = parseIpv4Cidr(raw);
  if (cidr) return prefixToIpv4Mask(cidr.prefix);

  if (isIpv4(raw)) {
    // Common intent for routing-like fields: x.x.x.0 means /24 network.
    if ((f.includes('dstaddr') || f.includes('dst_addr')) && raw.endsWith('.0')) return '255.255.255.0';
    return '255.255.255.255';
  }

  if (f.includes('mac')) return 'ff:ff:ff:ff:ff:ff';
  return '0xffffffff';
}

// ── Dynamic row ───────────────────────────────────────────────────────────────

function EntryRow({
  entry, schema, onChange, onRemove,
}: {
  entry: TableEntry;
  schema: TableSchema;
  onChange: (e: TableEntry) => void;
  onRemove: () => void;
}) {
  const setMatch = (key: TableKey, val: string) => {
    let normalized = val.trim();
    const nextMatch = { ...entry.match, [key.field]: normalized };
    const next: TableEntry = { ...entry, match: nextMatch };

    if (key.match_type === 'ternary') {
      const cidr = parseIpv4Cidr(normalized);
      const nextMask = { ...(entry.matchMask ?? {}) };

      if (cidr) {
        normalized = cidr.ip;
        next.match[key.field] = normalized;
        nextMask[key.field] = prefixToIpv4Mask(cidr.prefix);
      } else if (!nextMask[key.field] || nextMask[key.field].trim() === '') {
        nextMask[key.field] = inferTernaryMask(key.field, normalized);
      }

      next.matchMask = nextMask;
    }

    onChange(next);
  };

  const setPrefix = (field: string, val: number) =>
    onChange({ ...entry, matchPrefix: { ...(entry.matchPrefix ?? {}), [field]: val } });

  const setMask = (field: string, val: string) =>
    onChange({ ...entry, matchMask: { ...(entry.matchMask ?? {}), [field]: val } });
  
  const setAction = (val: string) => onChange({ ...entry, action: val, action_params: {} });

  const setParam = (name: string, val: string) =>
    onChange({ ...entry, action_params: { ...entry.action_params, [name]: val } });

  const chosenAction = schema.actions.find(a => a.name === entry.action) as TableAction | undefined;

  return (
    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
      {/* Match key columns - only show mappable ones */}
      {schema.keys.filter(k => isMappableField(k.field)).map((k: TableKey) => (
        <Fragment key={k.field}>
          <td style={cellStyle}>
            <input style={inputStyle} value={entry.match[k.field] ?? ''}
              onChange={e => setMatch(k, e.target.value)}
              placeholder={k.match_type === 'ternary' ? 'symbolic or 10.0.2.0/24' : 'symbolic'} />
          </td>
          {k.match_type === 'lpm' && (
            <td key={`${k.field}/prefix`} style={{ ...cellStyle, width: '60px' }}>
              <input style={inputStyle} type="number" min={0} max={128}
                value={entry.matchPrefix?.[k.field] ?? 32}
                onChange={e => setPrefix(k.field, +e.target.value)} />
            </td>
          )}
          {k.match_type === 'ternary' && (
            <td key={`${k.field}/mask`} style={{ ...cellStyle, minWidth: '130px' }}>
              <input
                style={inputStyle}
                value={entry.matchMask?.[k.field] ?? ''}
                onChange={e => setMask(k.field, e.target.value)}
                placeholder="255.255.255.255"
              />
            </td>
          )}

        </Fragment>
      ))}

      <td style={cellStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', width: '100%' }}>
          <select value={entry.action} onChange={e => setAction(e.target.value)} style={{ ...inputStyle, width: 'auto', minWidth: '150px', flexShrink: 0, padding: '2px' }}>
            {schema.actions.map(a => <option key={a.name} value={a.name}>{a.name}</option>)}
          </select>
          
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', flexGrow: 1 }}>
            {chosenAction?.params.map(p => (
              <div key={p.name} style={{ display: 'flex', alignItems: 'center', gap: '4px', background: 'rgba(255,255,255,0.03)', padding: '2px 6px', borderRadius: '4px', flexGrow: 1, minWidth: '100px' }}>
                <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>{p.name}:</span>
                <input 
                  style={{ ...inputStyle, width: '100%', background: 'transparent', border: 'none', borderBottom: '1px solid rgba(255,255,255,0.1)' }} 
                  value={entry.action_params[p.name] ?? ''}
                  onChange={e => setParam(p.name, e.target.value)}
                  placeholder="symbolic" 
                />
              </div>
            ))}
          </div>
        </div>
      </td>

      <td style={cellStyle}>
        <button onClick={onRemove} style={{ ...btnBase, color: 'var(--danger)' }}>
          <Trash2 size={14} />
        </button>
      </td>
    </tr>
  );
}

// ── Per-table section ─────────────────────────────────────────────────────────

function TableSection({
  schema, entries, onChange,
}: {
  schema: TableSchema;
  entries: TableEntry[];
  onChange: (entries: TableEntry[]) => void;
}) {
  const [open, setOpen] = useState(false);

  const defaultEntry = (): TableEntry => ({
    match: Object.fromEntries(schema.keys.map(k => [k.field, ''])),
    action: schema.actions[0]?.name ?? 'NoAction',
    action_params: {},
  });

  const addEntry = () => onChange([...entries, defaultEntry()]);
  const updateEntry = (i: number, e: TableEntry) => onChange(entries.map((r, idx) => idx === i ? e : r));
  const removeEntry = (i: number) => onChange(entries.filter((_, idx) => idx !== i));

  const cols = colsForSchema(schema);
  const displayName = schema.name.replace(/^.*\./, '');
  const matchTypes = schema.keys.map(k => k.match_type).join(', ');
  const subtitle = schema.keys.length > 0 ? matchTypes : 'no keys';

  return (
    <div style={{ marginBottom: '0.6rem', border: '1px solid var(--border)', borderRadius: '6px', overflow: 'hidden' }}>
      <div onClick={() => setOpen(o => !o)}
        style={{ padding: '0.6rem 1rem', background: 'var(--bg-surface)', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center', userSelect: 'none' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-main)' }}>{displayName}</span>
          <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontFamily: 'monospace' }}>({subtitle})</span>
          <span style={{ fontSize: '0.7rem', color: 'var(--accent)', marginLeft: '0.4rem' }}>{entries.length} entries</span>
        </div>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </div>

      {open && (
        <div style={{ padding: '0.8rem 1rem', background: 'var(--bg-dark)', overflowX: 'auto' }}>
          {schema.keys.length === 0 ? (
            <p style={{ color: 'var(--text-muted)', fontSize: '0.78rem' }}>
              This table has no match keys (internal/synthetic table). Default action: <code>{schema.default_action}</code>
            </p>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  {cols.map(c => {
                    // Decide labeling based on field relationships
                    const isMatch = schema.keys.some(k => 
                      k.field === c || 
                      `${k.field}/prefix` === c || 
                      `${k.field}/mask` === c
                    );
                    const isAction = c === 'Action & Parameters';
                    const isParam = !isMatch && !isAction;

                    let baseLabel = c.replace(/^.*\./, '').replace('/prefix', ' /len').replace('/mask', ' /mask');
                    if (isMatch) baseLabel = `MATCH: ${baseLabel}`;
                    if (isParam) baseLabel = `PARAM: ${baseLabel}`;
                    
                    return (
                      <th key={c} style={{ ...cellStyle, color: isMatch ? 'var(--accent)' : 'var(--text-muted)', fontSize: '0.72rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', textAlign: 'left', whiteSpace: 'nowrap' }}>
                        {baseLabel}
                      </th>
                    );
                  })}
                  <th style={{ ...cellStyle, width: '32px' }} />
                </tr>
              </thead>
              <tbody>
                {entries.map((e, i) => (
                  <EntryRow key={i} entry={e} schema={schema}
                    onChange={v => updateEntry(i, v)} onRemove={() => removeEntry(i)} />
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={cols.length + 1} style={cellStyle}>
                    <button onClick={addEntry}
                      style={{ background: 'transparent', border: '1px dashed var(--border)', color: 'var(--accent)', padding: '0.3rem 0.8rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <Plus size={12} /> Add Entry
                    </button>
                  </td>
                </tr>
              </tfoot>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

// ── Per-switch section ────────────────────────────────────────────────────────

function SwitchSection({
  sw, schemas, onUpdate, onRemove,
}: {
  sw: { id: string; tables: SwitchTableConfig };
  schemas: TableSchema[];
  onUpdate: (s: { id: string; tables: SwitchTableConfig }) => void;
  onRemove: () => void;
}) {
  const updateTable = (name: string, entries: TableEntry[]) =>
    onUpdate({ ...sw, tables: { ...sw.tables, [name]: entries } });

  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: '8px', overflow: 'hidden', marginBottom: '1rem' }}>
      <div style={{ padding: '0.8rem 1rem', background: 'var(--bg-panel)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <Router size={16} color="var(--accent)" />
          <span style={{ fontWeight: 700, color: 'var(--text-main)', fontSize: '0.9rem' }}>{sw.id.toUpperCase()}</span>
        </div>
        <button onClick={onRemove}
          style={{ ...btnBase, alignItems: 'center', gap: '0.3rem', fontSize: '0.75rem', color: 'var(--danger)' }}>
          <Trash2 size={14} /> Remove
        </button>
      </div>
      <div style={{ padding: '0.8rem 1rem', background: 'var(--bg-dark)' }}>
        {schemas.filter(s => s.keys.length > 0).map(schema => (
          <TableSection
            key={schema.name}
            schema={schema}
            entries={sw.tables[schema.name] ?? []}
            onChange={entries => updateTable(schema.name, entries)}
          />
        ))}
        {schemas.filter(s => s.keys.length === 0).length > 0 && (
          <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '0.4rem' }}>
            {schemas.filter(s => s.keys.length === 0).map(s => s.name.replace(/^.*\./, '')).join(', ')} — synthetic tables, no configuration needed.
          </p>
        )}
      </div>
    </div>
  );
}

// ── Hooks ─────────────────────────────────────────────────────────────────────

import type { TopologyNode, TopologyEdge } from './TopologyDiagram';
import TopologyDiagram, { defaultNodes, defaultEdges } from './TopologyDiagram';
import { autoPopulateTables } from '../lib/autoPopulate';

export interface TopologyConfig {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  switches: Array<{ id: string; tables: SwitchTableConfig }>;
  executionMode: ExecutionMode;
}

export function useNetworkConfig(tableSchemas: TableSchema[] = []) {
  const [config, setConfig] = useState<TopologyConfig>(() => ({
    nodes: defaultNodes,
    edges: defaultEdges,
    switches: autoPopulateTables(defaultNodes, defaultEdges, [], tableSchemas),
    executionMode: 'auto_concrete',
  }));

  // Re-populate when schemas arrive (e.g. after compiling a P4 file)
  const schemasKey = tableSchemas.map(s => s.name).join(',');
  useEffect(() => {
    if (!tableSchemas.length) return;
    setConfig(prev => ({
      ...prev,
      switches: autoPopulateTables(prev.nodes, prev.edges, [], tableSchemas),
    }));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schemasKey]);

  return { config, setConfig };
}

// ── Main Modal ────────────────────────────────────────────────────────────────

export default function NetworkConfigModal({
  config, setConfig, onClose, tableSchemas,
}: {
  config: TopologyConfig;
  setConfig: (c: TopologyConfig) => void;

  onClose: () => void;
  tableSchemas: TableSchema[];
}) {
  const setExecutionMode = (mode: ExecutionMode) =>
    setConfig({ ...config, executionMode: mode });

  const updateSwitch = (i: number, sw: { id: string; tables: SwitchTableConfig }) =>
    setConfig({ ...config, switches: config.switches.map((s, idx) => idx === i ? sw : s) });

  const removeSwitch = (i: number) => {
    // We should also remove the node from the diagram if a switch is removed from the bottom!
    const targetSw = config.switches[i];
    const newNodes = config.nodes.filter(n => n.id !== targetSw.id);
    const newEdges = config.edges.filter(e => e.source !== targetSw.id && e.target !== targetSw.id);
    setConfig({ ...config, nodes: newNodes, edges: newEdges, switches: config.switches.filter((_, idx) => idx !== i) });
  };

  const handleNodesChange = (nodes: TopologyNode[]) => {
    setConfig({ ...config, nodes, switches: autoPopulateTables(nodes, config.edges, config.switches, tableSchemas) });
  };

  const handleEdgesChange = (edges: TopologyEdge[]) => {
    setConfig({ ...config, edges, switches: autoPopulateTables(config.nodes, edges, config.switches, tableSchemas) });
  };

  const totalEntries = config.switches.reduce(
    (acc, sw) => acc + Object.values(sw.tables).reduce((a, e) => a + e.length, 0), 0,
  );

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }} onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={{
        background: 'var(--bg-panel)', border: '1px solid var(--border)', borderRadius: '12px',
        width: 'min(96vw, 900px)', maxHeight: '90vh',
        display: 'flex', flexDirection: 'column', boxShadow: '0 20px 60px rgba(0,0,0,0.6)',
      }}>
        {/* Header */}
        <div style={{ padding: '1.2rem 1.5rem', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.8rem' }}>
            <Network size={20} color="var(--accent)" />
            <div>
              <div style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-main)' }}>Network Configuration</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                Design your network topology to auto-generate basic routing tables from the loaded P4 program
              </div>
            </div>
          </div>
          <button onClick={onClose} style={{ ...btnBase, color: 'var(--text-muted)' }}><X size={20} /></button>
        </div>

        {/* Summary bar */}
        <div style={{ padding: '0.6rem 1.5rem', background: 'var(--bg-surface)', borderBottom: '1px solid var(--border)', display: 'flex', gap: '1.5rem', fontSize: '0.78rem', color: 'var(--text-muted)', alignItems: 'center', flexWrap: 'wrap' }}>
          <span><strong style={{ color: 'var(--accent)' }}>{config.switches.length}</strong> switches</span>
          <span><strong style={{ color: 'var(--accent)' }}>{tableSchemas.filter(s => s.keys.length > 0).length}</strong> configurable tables</span>
          <span><strong style={{ color: 'var(--accent)' }}>{totalEntries}</strong> total entries</span>
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>Execution Mode</span>
            <select
              value={config.executionMode}
              onChange={(e) => setExecutionMode(e.target.value as ExecutionMode)}
              style={{
                background: 'var(--bg-dark)',
                border: '1px solid var(--border)',
                color: 'var(--text-main)',
                borderRadius: '4px',
                padding: '0.2rem 0.5rem',
                fontSize: '0.75rem',
              }}
            >
              <option value="auto_concrete">Auto Concrete (default)</option>
              <option value="full_symbolic">Full Symbolic</option>
            </select>
          </div>
        </div>

        {/* Body */}
        <div style={{ overflowY: 'auto', flex: 1, padding: '1.2rem 1.5rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          
          <TopologyDiagram 
            nodes={config.nodes} 
            edges={config.edges} 
            onNodesChange={handleNodesChange} 
            onEdgesChange={handleEdgesChange} 
          />

          <div>
            {tableSchemas.length === 0 && (
              <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                No table schemas loaded. Please compile/upload a P4 program first.
              </div>
            )}
            {config.switches.map((sw, i) => (
              <SwitchSection
                key={sw.id} sw={sw} schemas={tableSchemas}
                onUpdate={s => updateSwitch(i, s)} onRemove={() => removeSwitch(i)}
              />
            ))}
          </div>
        </div>

        {/* Footer */}
        <div style={{ padding: '1rem 1.5rem', borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'flex-end', gap: '0.8rem' }}>
          <button onClick={onClose}
            style={{ background: 'transparent', border: '1px solid var(--border)', color: 'var(--text-muted)', padding: '0.5rem 1.2rem', borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem' }}>
            Cancel
          </button>
          <button onClick={onClose}
            style={{ background: 'var(--accent)', border: 'none', color: '#fff', padding: '0.5rem 1.4rem', borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 600 }}>
            Apply Configuration
          </button>
        </div>
      </div>
    </div>
  );
}
