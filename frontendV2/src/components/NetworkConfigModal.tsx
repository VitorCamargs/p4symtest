import { useState } from 'react';
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

function colsForSchema(schema: TableSchema): string[] {
  const matchCols: string[] = [];
  schema.keys.forEach(k => {
    matchCols.push(k.field);
    if (k.match_type === 'lpm') matchCols.push(`${k.field}/prefix`);
    if (k.match_type === 'ternary') matchCols.push(`${k.field} (mask)`);
  });
  const actionCols = ['Action'];
  const allParamNames = new Set<string>();
  schema.actions.forEach(a => a.params.forEach(p => allParamNames.add(p.name)));
  return [...matchCols, ...actionCols, ...Array.from(allParamNames)];
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
  const setMatch = (field: string, val: string) =>
    onChange({ ...entry, match: { ...entry.match, [field]: val } });
  const setMask = (field: string, val: string) =>
    onChange({ ...entry, matchMask: { ...(entry.matchMask ?? {}), [field]: val } });
  const setPrefix = (field: string, val: number) =>
    onChange({ ...entry, matchPrefix: { ...(entry.matchPrefix ?? {}), [field]: val } });
  const setAction = (val: string) => onChange({ ...entry, action: val, action_params: {} });
  const setParam = (name: string, val: string) =>
    onChange({ ...entry, action_params: { ...entry.action_params, [name]: val } });

  const chosenAction = schema.actions.find(a => a.name === entry.action) as TableAction | undefined;

  return (
    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
      {/* Match key columns */}
      {schema.keys.map((k: TableKey) => (
        <>
          <td key={k.field} style={cellStyle}>
            <input style={inputStyle} value={entry.match[k.field] ?? ''}
              onChange={e => setMatch(k.field, e.target.value)}
              placeholder={k.match_type === 'lpm' ? '10.0.0.0' : k.match_type === 'ternary' ? '0x0a000001' : '0'} />
          </td>
          {k.match_type === 'lpm' && (
            <td key={`${k.field}/prefix`} style={{ ...cellStyle, width: '60px' }}>
              <input style={inputStyle} type="number" min={0} max={128}
                value={entry.matchPrefix?.[k.field] ?? 32}
                onChange={e => setPrefix(k.field, +e.target.value)} />
            </td>
          )}
          {k.match_type === 'ternary' && (
            <td key={`${k.field}_mask`} style={cellStyle}>
              <input style={inputStyle} value={entry.matchMask?.[k.field] ?? ''}
                onChange={e => setMask(k.field, e.target.value)}
                placeholder="0xffffffff" />
            </td>
          )}
        </>
      ))}

      {/* Action selector */}
      <td style={cellStyle}>
        <select style={{ ...inputStyle, cursor: 'pointer' }} value={entry.action} onChange={e => setAction(e.target.value)}>
          {schema.actions.map(a => (
            <option key={a.name} value={a.name}>{a.name.replace(/^.*\./, '')}</option>
          ))}
        </select>
      </td>

      {/* Action params */}
      {chosenAction?.params.map(p => (
        <td key={p.name} style={cellStyle}>
          <input style={inputStyle} value={entry.action_params[p.name] ?? ''}
            onChange={e => setParam(p.name, e.target.value)}
            placeholder={p.name} />
        </td>
      ))}

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
                  {cols.map(c => (
                    <th key={c} style={{ ...cellStyle, color: 'var(--text-muted)', fontSize: '0.72rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', textAlign: 'left', whiteSpace: 'nowrap' }}>
                      {c.replace(/^.*\./, '').replace('/prefix', ' /len')}
                    </th>
                  ))}
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

export function useNetworkConfig() {
  const [config, setConfig] = useState<NetworkConfig>({ numSwitches: 1, switches: [{ id: 's1', tables: {} }] });
  return { config, setConfig };
}

// ── Main Modal ────────────────────────────────────────────────────────────────

export default function NetworkConfigModal({
  config, setConfig, onClose, tableSchemas,
}: {
  config: NetworkConfig;
  setConfig: (c: NetworkConfig) => void;
  onClose: () => void;
  tableSchemas: TableSchema[];
}) {
  const updateSwitch = (i: number, sw: { id: string; tables: SwitchTableConfig }) =>
    setConfig({ ...config, switches: config.switches.map((s, idx) => idx === i ? sw : s) });

  const removeSwitch = (i: number) =>
    setConfig({ ...config, switches: config.switches.filter((_, idx) => idx !== i) });

  const addSwitch = () => {
    const nextId = `s${config.switches.length + 1}`;
    setConfig({ ...config, switches: [...config.switches, { id: nextId, tables: {} }] });
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
                Tables are generated from the loaded P4 program · equivalent to runtime_config.json
              </div>
            </div>
          </div>
          <button onClick={onClose} style={{ ...btnBase, color: 'var(--text-muted)' }}><X size={20} /></button>
        </div>

        {/* Summary bar */}
        <div style={{ padding: '0.6rem 1.5rem', background: 'var(--bg-surface)', borderBottom: '1px solid var(--border)', display: 'flex', gap: '1.5rem', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
          <span><strong style={{ color: 'var(--accent)' }}>{config.switches.length}</strong> switches</span>
          <span><strong style={{ color: 'var(--accent)' }}>{tableSchemas.filter(s => s.keys.length > 0).length}</strong> configurable tables</span>
          <span><strong style={{ color: 'var(--accent)' }}>{totalEntries}</strong> total entries</span>
        </div>

        {/* Body */}
        <div style={{ overflowY: 'auto', flex: 1, padding: '1.2rem 1.5rem' }}>
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
          <button onClick={addSwitch} style={{
            width: '100%', background: 'transparent', border: '1px dashed var(--border)',
            color: 'var(--accent)', padding: '0.7rem', borderRadius: '8px',
            cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
            gap: '0.5rem', fontSize: '0.85rem', fontWeight: 600,
          }}>
            <Plus size={16} /> Add Switch
          </button>
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
