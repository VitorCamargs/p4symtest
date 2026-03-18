import { useState } from 'react';
import { FolderTree, Settings, ChevronLeft, ChevronRight } from 'lucide-react';
import NetworkConfigModal, { useNetworkConfig } from './NetworkConfigModal';

export default function LeftPanel({ isCollapsed = false, onToggle }: { isCollapsed?: boolean, onToggle?: () => void }) {
  const [showConfig, setShowConfig] = useState(false);
  const { config, setConfig } = useNetworkConfig();

  const totalRoutes = config.switches.reduce(
    (a, s) => a + s.ipv4Routes.length + s.tunnelRoutes.length, 0
  );

  return (
    <>
      {/* ---- File Manager Section ---- */}
      <div className="panel-header" style={{ justifyContent: isCollapsed ? 'center' : 'space-between', padding: isCollapsed ? '0.8rem 0' : '0.8rem 1rem' }}>
        {!isCollapsed ? (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <FolderTree size={18} /> <span style={{ fontSize: '0.85rem' }}>File Manager</span>
            </div>
            {onToggle && <ChevronLeft size={18} cursor="pointer" onClick={onToggle} style={{ color: 'var(--text-muted)' }} />}
          </>
        ) : (
          onToggle && <ChevronRight size={18} cursor="pointer" onClick={onToggle} style={{ color: 'var(--text-muted)' }} />
        )}
      </div>

      <div className="panel-content" style={{ padding: isCollapsed ? '1rem 0' : '1rem' }}>
        <div style={{ marginBottom: '1.5rem', display: 'flex', flexDirection: 'column', alignItems: isCollapsed ? 'center' : 'stretch' }}>
          <div style={{
            padding: '0.5rem', borderRadius: '4px', backgroundColor: 'var(--bg-surface)', cursor: 'pointer',
            display: 'flex', alignItems: 'center', gap: '0.5rem', justifyContent: isCollapsed ? 'center' : 'flex-start'
          }} title="programa.p4">
            <span style={{ color: 'var(--accent)', display: 'flex' }}>📝</span>
            {!isCollapsed && <span style={{ fontSize: '0.85rem' }}>programa.p4</span>}
          </div>
        </div>
      </div>

      {/* ---- Configurations Section ---- */}
      <div
        className="panel-header"
        onClick={() => setShowConfig(true)}
        style={{
          borderTop: '1px solid var(--border)', borderBottom: 'none',
          justifyContent: isCollapsed ? 'center' : 'flex-start',
          padding: isCollapsed ? '0.8rem 0' : '0.8rem 1rem',
          cursor: 'pointer',
          transition: 'background 0.15s',
        }}
        title="Network Configurations"
        onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-surface)')}
        onMouseLeave={e => (e.currentTarget.style.background = '')}
      >
        <Settings size={18} color={showConfig ? 'var(--accent)' : undefined} />
        {!isCollapsed && <span style={{ fontSize: '0.85rem', marginLeft: '0.4rem' }}>Configurations</span>}
      </div>

      {/* ---- Config Summary (only when expanded) ---- */}
      {!isCollapsed && (
        <div
          style={{ padding: '0.6rem 1rem', cursor: 'pointer', borderBottom: '1px solid var(--border)' }}
          onClick={() => setShowConfig(true)}
        >
          {config.switches.length === 0 ? (
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: 0 }}>No network configured.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem' }}>
                <span style={{ color: 'var(--text-muted)' }}>Switches</span>
                <span style={{ color: 'var(--accent)', fontWeight: 600 }}>{config.switches.length}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem' }}>
                <span style={{ color: 'var(--text-muted)' }}>IPv4 routes</span>
                <span style={{ color: 'var(--text-main)' }}>{config.switches.reduce((a, s) => a + s.ipv4Routes.length, 0)}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem' }}>
                <span style={{ color: 'var(--text-muted)' }}>Tunnel entries</span>
                <span style={{ color: 'var(--text-main)' }}>{config.switches.reduce((a, s) => a + s.tunnelRoutes.length, 0)}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem' }}>
                <span style={{ color: 'var(--text-muted)' }}>Egress MACs</span>
                <span style={{ color: 'var(--text-main)' }}>{config.switches.reduce((a, s) => a + s.egressSmac.length, 0)}</span>
              </div>
              <div
                style={{ marginTop: '0.2rem', fontSize: '0.7rem', color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: '0.3rem', opacity: 0.8 }}
              >
                {/* tiny dot indicator */}
                <span style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: totalRoutes > 0 ? 'var(--success)' : 'var(--danger)', display: 'inline-block' }} />
                {totalRoutes > 0 ? 'Configured' : 'Empty — click to edit'}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ---- Modal ---- */}
      {showConfig && (
        <NetworkConfigModal config={config} setConfig={setConfig} onClose={() => setShowConfig(false)} />
      )}
    </>
  );
}
