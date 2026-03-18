import { useState } from 'react';
import { X, Plus, Trash2, Router, Network, ChevronDown, ChevronRight } from 'lucide-react';

// ---- Types ----
interface Ipv4Route { dstAddr: string; prefix: number; port: number; dstMac: string; }
interface TunnelRoute { dst_id: number; port: number; }
interface EgressSmac { port: number; smac: string; }

interface SwitchConfig {
  id: string;
  ipv4Routes: Ipv4Route[];
  tunnelRoutes: TunnelRoute[];
  egressSmac: EgressSmac[];
}

interface NetworkConfig {
  numSwitches: number;
  switches: SwitchConfig[];
}

function makeSwitchConfig(id: string): SwitchConfig {
  return {
    id,
    ipv4Routes: [{ dstAddr: '10.0.0.1', prefix: 32, port: 1, dstMac: '00:00:00:00:01:01' }],
    tunnelRoutes: [{ dst_id: 1, port: 1 }],
    egressSmac: [{ port: 1, smac: '00:00:00:00:00:01' }],
  };
}

const inputStyle: React.CSSProperties = {
  background: 'var(--bg-dark)', border: '1px solid var(--border)',
  color: 'var(--text-main)', padding: '0.35rem 0.5rem', borderRadius: '4px',
  fontSize: '0.78rem', width: '100%', fontFamily: 'monospace',
};

const cellStyle: React.CSSProperties = { padding: '0.3rem 0.4rem', verticalAlign: 'middle' };

function TableHeader({ cols }: { cols: string[] }) {
  return (
    <thead>
      <tr style={{ borderBottom: '1px solid var(--border)' }}>
        {cols.map(c => (
          <th key={c} style={{ ...cellStyle, color: 'var(--text-muted)', fontSize: '0.72rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', textAlign: 'left' }}>{c}</th>
        ))}
        <th style={{ ...cellStyle, width: '32px' }} />
      </tr>
    </thead>
  );
}

// ---- Sub-tables ----
function Ipv4Table({ routes, onChange }: { routes: Ipv4Route[], onChange: (r: Ipv4Route[]) => void }) {
  const update = (i: number, patch: Partial<Ipv4Route>) =>
    onChange(routes.map((r, idx) => idx === i ? { ...r, ...patch } : r));
  const add = () => onChange([...routes, { dstAddr: '10.0.0.1', prefix: 32, port: 1, dstMac: '00:00:00:00:01:01' }]);
  const remove = (i: number) => onChange(routes.filter((_, idx) => idx !== i));
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
      <TableHeader cols={['Dst IP', 'Prefix', 'Port', 'Dst MAC']} />
      <tbody>
        {routes.map((r, i) => (
          <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
            <td style={cellStyle}><input style={inputStyle} value={r.dstAddr} onChange={e => update(i, { dstAddr: e.target.value })} /></td>
            <td style={{ ...cellStyle, width: '60px' }}><input style={inputStyle} type="number" min={1} max={32} value={r.prefix} onChange={e => update(i, { prefix: +e.target.value })} /></td>
            <td style={{ ...cellStyle, width: '60px' }}><input style={inputStyle} type="number" min={1} value={r.port} onChange={e => update(i, { port: +e.target.value })} /></td>
            <td style={cellStyle}><input style={inputStyle} value={r.dstMac} onChange={e => update(i, { dstMac: e.target.value })} /></td>
            <td style={cellStyle}><button onClick={() => remove(i)} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--danger)', display: 'flex' }}><Trash2 size={14} /></button></td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr><td colSpan={5} style={cellStyle}>
          <button onClick={add} style={{ background: 'transparent', border: '1px dashed var(--border)', color: 'var(--accent)', padding: '0.3rem 0.8rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <Plus size={12} /> Add Route
          </button>
        </td></tr>
      </tfoot>
    </table>
  );
}

function TunnelTable({ routes, onChange }: { routes: TunnelRoute[], onChange: (r: TunnelRoute[]) => void }) {
  const update = (i: number, patch: Partial<TunnelRoute>) =>
    onChange(routes.map((r, idx) => idx === i ? { ...r, ...patch } : r));
  const add = () => onChange([...routes, { dst_id: routes.length + 1, port: 1 }]);
  const remove = (i: number) => onChange(routes.filter((_, idx) => idx !== i));
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
      <TableHeader cols={['Tunnel Dst ID', 'Output Port']} />
      <tbody>
        {routes.map((r, i) => (
          <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
            <td style={cellStyle}><input style={inputStyle} type="number" min={1} value={r.dst_id} onChange={e => update(i, { dst_id: +e.target.value })} /></td>
            <td style={cellStyle}><input style={inputStyle} type="number" min={1} value={r.port} onChange={e => update(i, { port: +e.target.value })} /></td>
            <td style={cellStyle}><button onClick={() => remove(i)} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--danger)', display: 'flex' }}><Trash2 size={14} /></button></td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr><td colSpan={3} style={cellStyle}>
          <button onClick={add} style={{ background: 'transparent', border: '1px dashed var(--border)', color: 'var(--accent)', padding: '0.3rem 0.8rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <Plus size={12} /> Add Tunnel Entry
          </button>
        </td></tr>
      </tfoot>
    </table>
  );
}

function EgressTable({ entries, onChange }: { entries: EgressSmac[], onChange: (e: EgressSmac[]) => void }) {
  const update = (i: number, patch: Partial<EgressSmac>) =>
    onChange(entries.map((r, idx) => idx === i ? { ...r, ...patch } : r));
  const add = () => onChange([...entries, { port: entries.length + 1, smac: '00:00:00:00:00:01' }]);
  const remove = (i: number) => onChange(entries.filter((_, idx) => idx !== i));
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem' }}>
      <TableHeader cols={['Egress Port', 'Src MAC']} />
      <tbody>
        {entries.map((r, i) => (
          <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
            <td style={{ ...cellStyle, width: '100px' }}><input style={inputStyle} type="number" min={1} value={r.port} onChange={e => update(i, { port: +e.target.value })} /></td>
            <td style={cellStyle}><input style={inputStyle} value={r.smac} onChange={e => update(i, { smac: e.target.value })} /></td>
            <td style={cellStyle}><button onClick={() => remove(i)} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--danger)', display: 'flex' }}><Trash2 size={14} /></button></td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr><td colSpan={3} style={cellStyle}>
          <button onClick={add} style={{ background: 'transparent', border: '1px dashed var(--border)', color: 'var(--accent)', padding: '0.3rem 0.8rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <Plus size={12} /> Add Egress Entry
          </button>
        </td></tr>
      </tfoot>
    </table>
  );
}

// ---- Switch Section ----
function SwitchSection({ sw, onUpdate, onRemove }: { sw: SwitchConfig, onUpdate: (s: SwitchConfig) => void, onRemove: () => void }) {
  const [open, setOpen] = useState<string | null>('ipv4');

  const Section = ({ id, label, children }: { id: string, label: string, children: React.ReactNode }) => (
    <div style={{ marginBottom: '0.6rem', border: '1px solid var(--border)', borderRadius: '6px', overflow: 'hidden' }}>
      <div
        onClick={() => setOpen(open === id ? null : id)}
        style={{ padding: '0.6rem 1rem', background: 'var(--bg-surface)', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center', userSelect: 'none' }}
      >
        <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-main)' }}>{label}</span>
        {open === id ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </div>
      {open === id && <div style={{ padding: '0.8rem 1rem', background: 'var(--bg-dark)' }}>{children}</div>}
    </div>
  );

  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: '8px', overflow: 'hidden', marginBottom: '1rem' }}>
      <div style={{ padding: '0.8rem 1rem', background: 'var(--bg-panel)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <Router size={16} color="var(--accent)" />
          <span style={{ fontWeight: 700, color: 'var(--text-main)', fontSize: '0.9rem' }}>{sw.id.toUpperCase()}</span>
        </div>
        <button onClick={onRemove} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--danger)', display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.75rem' }}>
          <Trash2 size={14} /> Remove
        </button>
      </div>
      <div style={{ padding: '0.8rem 1rem', background: 'var(--bg-dark)' }}>
        <Section id="ipv4" label="IPv4 LPM Table (MyIngress.ipv4_lpm)">
          <Ipv4Table routes={sw.ipv4Routes} onChange={r => onUpdate({ ...sw, ipv4Routes: r })} />
        </Section>
        <Section id="tunnel" label="Tunnel Exact Table (MyIngress.myTunnel_exact)">
          <TunnelTable routes={sw.tunnelRoutes} onChange={r => onUpdate({ ...sw, tunnelRoutes: r })} />
        </Section>
        <Section id="egress" label="Egress Source MAC (MyEgress.egress_port_smac)">
          <EgressTable entries={sw.egressSmac} onChange={e => onUpdate({ ...sw, egressSmac: e })} />
        </Section>
      </div>
    </div>
  );
}

// ---- Initial config from backend runtime_config.json defaults ----
const DEFAULT_CONFIG: NetworkConfig = {
  numSwitches: 3,
  switches: [
    {
      id: 's1',
      ipv4Routes: [
        { dstAddr: '10.0.0.1', prefix: 32, port: 1, dstMac: '00:00:00:01:01' },
        { dstAddr: '10.0.0.2', prefix: 32, port: 2, dstMac: '10:cf:f1:43:53:02' },
        { dstAddr: '10.0.0.3', prefix: 32, port: 3, dstMac: '10:cf:f1:43:54:02' },
      ],
      tunnelRoutes: [{ dst_id: 1, port: 1 }, { dst_id: 2, port: 2 }, { dst_id: 3, port: 3 }],
      egressSmac: [{ port: 1, smac: '10:cf:f1:43:59:01' }, { port: 2, smac: '10:cf:f1:43:59:02' }, { port: 3, smac: '10:cf:f1:43:59:03' }],
    },
    {
      id: 's2',
      ipv4Routes: [
        { dstAddr: '10.0.0.1', prefix: 32, port: 2, dstMac: '10:cf:f1:43:59:06' },
        { dstAddr: '10.0.0.2', prefix: 32, port: 1, dstMac: '00:00:00:02:02' },
        { dstAddr: '10.0.0.3', prefix: 32, port: 3, dstMac: '10:cf:f1:43:54:03' },
      ],
      tunnelRoutes: [{ dst_id: 1, port: 2 }, { dst_id: 2, port: 1 }, { dst_id: 3, port: 3 }],
      egressSmac: [{ port: 1, smac: '10:cf:f1:43:61:61' }, { port: 2, smac: '10:cf:f1:43:61:62' }, { port: 3, smac: '10:cf:f1:43:61:63' }],
    },
    {
      id: 's3',
      ipv4Routes: [
        { dstAddr: '10.0.0.1', prefix: 32, port: 2, dstMac: '10:cf:f1:43:59:07' },
        { dstAddr: '10.0.0.2', prefix: 32, port: 3, dstMac: '10:cf:f1:43:61:63' },
        { dstAddr: '10.0.0.3', prefix: 32, port: 1, dstMac: '00:00:00:03:03' },
      ],
      tunnelRoutes: [{ dst_id: 1, port: 2 }, { dst_id: 2, port: 3 }, { dst_id: 3, port: 1 }],
      egressSmac: [{ port: 1, smac: '10:cf:f1:43:64:41' }, { port: 2, smac: '10:cf:f1:43:64:42' }, { port: 3, smac: '10:cf:f1:43:64:43' }],
    },
  ],
};

// ---- Main Modal ----
export function useNetworkConfig() {
  const [config, setConfig] = useState<NetworkConfig>(DEFAULT_CONFIG);
  return { config, setConfig };
}

export default function NetworkConfigModal({ config, setConfig, onClose }: {
  config: NetworkConfig,
  setConfig: (c: NetworkConfig) => void,
  onClose: () => void,
}) {
  const updateSwitch = (i: number, sw: SwitchConfig) =>
    setConfig({ ...config, switches: config.switches.map((s, idx) => idx === i ? sw : s) });

  const removeSwitch = (i: number) =>
    setConfig({ ...config, switches: config.switches.filter((_, idx) => idx !== i) });

  const addSwitch = () => {
    const nextId = `s${config.switches.length + 1}`;
    setConfig({ ...config, switches: [...config.switches, makeSwitchConfig(nextId)] });
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }} onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={{
        background: 'var(--bg-panel)', border: '1px solid var(--border)', borderRadius: '12px',
        width: 'min(92vw, 800px)', maxHeight: '88vh',
        display: 'flex', flexDirection: 'column', boxShadow: '0 20px 60px rgba(0,0,0,0.6)',
      }}>
        {/* ---- Header ---- */}
        <div style={{ padding: '1.2rem 1.5rem', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.8rem' }}>
            <Network size={20} color="var(--accent)" />
            <div>
              <div style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-main)' }}>Network Configuration</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Configure switches and routing tables (equivalent to runtime_config.json)</div>
            </div>
          </div>
          <button onClick={onClose} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', display: 'flex' }}>
            <X size={20} />
          </button>
        </div>

        {/* ---- Summary Bar ---- */}
        <div style={{ padding: '0.6rem 1.5rem', background: 'var(--bg-surface)', borderBottom: '1px solid var(--border)', display: 'flex', gap: '1.5rem', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
          <span><strong style={{ color: 'var(--accent)' }}>{config.switches.length}</strong> switches</span>
          <span><strong style={{ color: 'var(--accent)' }}>{config.switches.reduce((a, s) => a + s.ipv4Routes.length, 0)}</strong> IPv4 routes</span>
          <span><strong style={{ color: 'var(--accent)' }}>{config.switches.reduce((a, s) => a + s.tunnelRoutes.length, 0)}</strong> tunnel entries</span>
          <span><strong style={{ color: 'var(--accent)' }}>{config.switches.reduce((a, s) => a + s.egressSmac.length, 0)}</strong> egress MACs</span>
        </div>

        {/* ---- Scrollable body ---- */}
        <div style={{ overflowY: 'auto', flex: 1, padding: '1.2rem 1.5rem' }}>
          {config.switches.map((sw, i) => (
            <SwitchSection key={sw.id} sw={sw} onUpdate={s => updateSwitch(i, s)} onRemove={() => removeSwitch(i)} />
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

        {/* ---- Footer ---- */}
        <div style={{ padding: '1rem 1.5rem', borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'flex-end', gap: '0.8rem' }}>
          <button onClick={onClose} style={{ background: 'transparent', border: '1px solid var(--border)', color: 'var(--text-muted)', padding: '0.5rem 1.2rem', borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem' }}>
            Cancel
          </button>
          <button onClick={onClose} style={{ background: 'var(--accent)', border: 'none', color: '#fff', padding: '0.5rem 1.4rem', borderRadius: '6px', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 600 }}>
            Apply Configuration
          </button>
        </div>
      </div>
    </div>
  );
}
