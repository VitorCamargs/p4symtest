import { useState, useRef, useEffect } from 'react';
import { FolderTree, Settings, ChevronLeft, ChevronRight, Plus, FolderUp } from 'lucide-react';
import NetworkConfigModal, { useNetworkConfig } from './NetworkConfigModal';
import { getApiScenario, setApiScenario, fetchMockSource } from '../lib/api';
import type { TableSchema } from '../lib/api';

export default function LeftPanel({ 
  isCollapsed = false, 
  onToggle,
  files = [],
  activeFileName = null,
  onCreateFile = () => {},
  onUploadFile = () => {},
  onSelectFile = () => {},
  tableSchemas = [],
}: { 
  isCollapsed?: boolean, 
  onToggle?: () => void,
  files?: string[],
  activeFileName?: string | null,
  onCreateFile?: (name: string) => void,
  onUploadFile?: (name: string, content: string) => void,
  onSelectFile?: (name: string) => void,
  tableSchemas?: TableSchema[],
}) {
  const [showConfig, setShowConfig] = useState(false);
  const { config, setConfig } = useNetworkConfig();

  const [isCreatingFile, setIsCreatingFile] = useState(false);
  const [newFileName, setNewFileName] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleCreateSubmit = () => {
    if (newFileName.trim()) {
      onCreateFile(newFileName.trim());
    }
    setIsCreatingFile(false);
    setNewFileName('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleCreateSubmit();
    if (e.key === 'Escape') {
      setIsCreatingFile(false);
      setNewFileName('');
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    const reader = new FileReader();
    reader.onload = (evt) => {
      const content = evt.target?.result as string;
      onUploadFile(file.name, content);
    };
    reader.readAsText(file);
    e.target.value = '';
  };

  const totalEntries = config.switches.reduce(
    (a, s) => a + Object.values(s.tables).reduce((t, entries) => t + entries.length, 0), 0
  );

  // Auto-load the source code for the current scenario on mount
  useEffect(() => {
    if (import.meta.env.DEV) {
      fetchMockSource()
        .then(res => {
          if (res.source) onUploadFile('programa.p4', res.source);
        })
        .catch(err => console.error("Could not fetch mock source:", err));
    }
  }, []);

  return (
    <>
      {/* ---- File Manager Section ---- */}
      <div className="panel-header" style={{ justifyContent: isCollapsed ? 'center' : 'space-between', padding: isCollapsed ? '0.8rem 0' : '0.8rem 1rem' }}>
        {!isCollapsed ? (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <FolderTree size={18} /> <span style={{ fontSize: '0.85rem' }}>File Manager</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <span title="New File" style={{ display: 'flex', cursor: 'pointer' }} onClick={() => setIsCreatingFile(true)}>
                <Plus size={16} style={{ color: 'var(--text-muted)' }} />
              </span>
              <span title="Upload File" style={{ display: 'flex', cursor: 'pointer' }} onClick={() => fileInputRef.current?.click()}>
                <FolderUp size={16} style={{ color: 'var(--text-muted)' }} />
              </span>
              {onToggle && (
                <span title="Collapse" style={{ display: 'flex', cursor: 'pointer', paddingLeft: '0.2rem' }} onClick={onToggle}>
                  <ChevronLeft size={18} style={{ color: 'var(--text-muted)' }} />
                </span>
              )}
            </div>
          </>
        ) : (
          onToggle && <ChevronRight size={18} cursor="pointer" onClick={onToggle} style={{ color: 'var(--text-muted)' }} />
        )}
      </div>

      <div className="panel-content" style={{ padding: isCollapsed ? '1rem 0' : '1rem' }}>
        <input 
          type="file" 
          ref={fileInputRef} 
          style={{ display: 'none' }} 
          accept=".p4"
          onChange={handleFileUpload} 
        />
        <div style={{ marginBottom: '1.5rem', display: 'flex', flexDirection: 'column', gap: '0.2rem', alignItems: isCollapsed ? 'center' : 'stretch' }}>
          {files.map(fileName => (
             <div 
               key={fileName}
               onClick={() => onSelectFile(fileName)}
               style={{
                padding: '0.4rem 0.5rem', borderRadius: '4px', cursor: 'pointer',
                backgroundColor: activeFileName === fileName ? 'rgba(56, 189, 248, 0.1)' : 'transparent',
                display: 'flex', alignItems: 'center', gap: '0.5rem', justifyContent: isCollapsed ? 'center' : 'flex-start'
             }} title={fileName}>
                <span style={{ color: 'var(--accent)', display: 'flex' }}>📝</span>
                {!isCollapsed && <span style={{ fontSize: '0.85rem', color: activeFileName === fileName ? 'var(--accent)' : 'var(--text-main)', fontWeight: activeFileName === fileName ? 600 : 400 }}>{fileName}</span>}
             </div>
          ))}

          {isCreatingFile && !isCollapsed && (
            <div style={{
              padding: '0.4rem 0.5rem', borderRadius: '4px',
              backgroundColor: 'var(--bg-surface)',
              display: 'flex', alignItems: 'center', gap: '0.5rem'
            }}>
              <span style={{ color: 'var(--accent)', display: 'flex' }}>📝</span>
              <input
                autoFocus
                type="text"
                value={newFileName}
                onChange={e => setNewFileName(e.target.value)}
                onKeyDown={handleKeyDown}
                onBlur={handleCreateSubmit}
                placeholder="filename.p4"
                style={{
                  background: 'transparent',
                  border: 'none',
                  outline: 'none',
                  color: 'var(--text-main)',
                  fontSize: '0.85rem',
                  width: '100%'
                }}
              />
            </div>
          )}
          
          {files.length === 0 && !isCreatingFile && !isCollapsed && (
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textAlign: 'center', padding: '1.5rem 0' }}>
              No files open.
            </div>
          )}
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

      {/* ---- Scenario Toggle ---- */}
      {!isCollapsed && import.meta.env.DEV && (
        <div style={{ padding: '0.6rem 1rem', borderTop: '1px solid var(--border)', borderBottom: '1px solid var(--border)' }}>
          <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Mock Scenario</label>
          <select
            value={getApiScenario()}
            onChange={(e) => {
              setApiScenario(e.target.value);
              window.location.reload();
            }}
            style={{ width: '100%', padding: '0.3rem', marginTop: '0.3rem', background: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-main)', borderRadius: '4px', fontSize: '0.8rem' }}
          >
            <option value="default">Default</option>
            <option value="custom">Custom Test</option>
          </select>
        </div>
      )}

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
                <span style={{ color: 'var(--text-muted)' }}>Table entries</span>
                <span style={{ color: 'var(--text-main)' }}>{totalEntries}</span>
              </div>
              <div
                style={{ marginTop: '0.2rem', fontSize: '0.7rem', color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: '0.3rem', opacity: 0.8 }}
              >
                <span style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: totalEntries > 0 ? 'var(--success)' : 'var(--danger)', display: 'inline-block' }} />
                {totalEntries > 0 ? 'Configured' : 'Empty — click to edit'}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ---- Modal ---- */}
      {showConfig && (
        <NetworkConfigModal
          config={config}
          setConfig={setConfig}
          onClose={() => setShowConfig(false)}
          tableSchemas={tableSchemas}
        />
      )}
    </>
  );
}
