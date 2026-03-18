import { useState } from 'react';
import Editor from '@monaco-editor/react';
import { Play, Code2, Settings2, Trash2 } from 'lucide-react';
import { mockData } from '../lib/mockData';

export default function CenterPanel({ onVerify, executionChain, setExecutionChain }: {
  onVerify: (type: string, name: string) => void;
  executionChain: string[];
  setExecutionChain: React.Dispatch<React.SetStateAction<string[]>>;
}) {
  const [code, setCode] = useState(mockData.p4ProgramContent);
  const [compiledData, setCompiledData] = useState<any>(null);

  const handleCompile = () => {
    setCompiledData(mockData.compiledStructures);
    setExecutionChain([]); // Reset on compile
  };

  const handleVerifyNode = (type: string, name: string) => {
    const shortName = name.split('.').pop() || name;
    if (type === 'parser') {
      // Running parser creates the root state
      setExecutionChain([shortName]);
    } else {
      // Running table appends to the state chain
      setExecutionChain(prev => [...prev, shortName]);
    }
    onVerify(type, name);
  };

  const StructureItem = ({ type, name }: { type: string, name: string }) => {
    // Only parser can be run when chain is empty
    const isDisabled = type !== 'parser' && executionChain.length === 0;

    return (
      <div style={{ background: 'var(--bg-surface)', padding: '0.8rem 1rem', borderRadius: '6px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', opacity: isDisabled ? 0.6 : 1 }}>
        <h4 style={{ margin: 0, color: 'var(--text-main)', fontSize: '0.85rem' }}>{name}</h4>
        <button 
          onClick={() => handleVerifyNode(type, name)}
          disabled={isDisabled}
          style={{ 
            background: isDisabled ? 'transparent' : 'var(--border)', 
            color: isDisabled ? 'var(--text-muted)' : 'white', 
            border: isDisabled ? '1px solid var(--border)' : 'none', 
            padding: '0.3rem 0.6rem', 
            borderRadius: '4px', 
            cursor: isDisabled ? 'not-allowed' : 'pointer', 
            fontSize: '0.75rem' 
          }}
          title={isDisabled ? "Select an Input State to verify this table" : "Run Verification"}
        >
          Verify
        </button>
      </div>
    );
  };

  return (
    <>
      <div className="panel-header" style={{ justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Code2 size={18} /> P4 Source Code
        </div>
        <button 
          onClick={handleCompile}
          style={{ 
            display: 'flex', alignItems: 'center', gap: '0.4rem', 
            background: 'var(--accent)', color: '#fff', 
            border: 'none', padding: '0.4rem 0.8rem', 
            borderRadius: '4px', cursor: 'pointer', fontWeight: 600, fontSize: '0.8rem' 
          }}
        >
          <Play size={14} fill="currentColor" /> Compile Program
        </button>
      </div>
      
      <div style={{ flex: 1, minHeight: 0 }}>
        <Editor
          height="100%"
          defaultLanguage="cpp"
          theme="vs-dark"
          value={code}
          onChange={(val) => setCode(val || '')}
          options={{ minimap: { enabled: false }, fontSize: 13, padding: { top: 16 } }}
        />
      </div>

      <div className="panel-header" style={{ borderTop: '1px solid var(--border)', borderBottom: '1px solid var(--border)', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <Settings2 size={18} /> Compiled Structures
        </div>
        
        {/* Input State Indicator */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'var(--bg-surface)', padding: '0.2rem 0.6rem', borderRadius: '4px', border: '1px solid var(--border)' }}>
          <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Loaded State:</span>
          <span style={{ fontSize: '0.75rem', color: executionChain.length > 0 ? 'var(--accent)' : 'var(--danger)', fontWeight: 600, fontFamily: 'monospace' }}>
            {executionChain.length > 0 ? executionChain.join(' -> ') : 'None Loaded'}
          </span>
          {executionChain.length > 0 && (
            <button 
              onClick={() => setExecutionChain([])} 
              style={{ background: 'transparent', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', color: 'var(--danger)', padding: '0 0 0 0.4rem', marginLeft: '0.2rem', borderLeft: '1px solid var(--border)' }}
              title="Clear Input State"
            >
              <Trash2 size={12} />
            </button>
          )}
        </div>
      </div>
      <div className="panel-content" style={{ flex: 'none', height: '30%', overflowY: 'auto' }}>
        {!compiledData ? (
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', textAlign: 'center', marginTop: '2rem' }}>
            Compile the code to view structures.
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            
            {/* Parsers */}
            {compiledData.parsers?.length > 0 && (
              <div>
                <h3 style={{ fontSize: '0.8rem', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>Parsers</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  {compiledData.parsers.map((p: any, idx: number) => (
                    <StructureItem key={idx} type="parser" name={p.name} />
                  ))}
                </div>
              </div>
            )}

            {/* Pipelines (Ingress / Egress) */}
            {compiledData.pipelines?.map((pipe: any, pIdx: number) => (
              <div key={pIdx}>
                <h3 style={{ fontSize: '0.8rem', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>Pipeline: {pipe.name}</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  {pipe.tables?.map((table: any, idx: number) => (
                    <StructureItem key={idx} type="table" name={table.name} />
                  ))}
                </div>
              </div>
            ))}

            {/* Deparsers */}
            {compiledData.deparsers?.length > 0 && (
              <div>
                <h3 style={{ fontSize: '0.8rem', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>Deparsers</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  {compiledData.deparsers.map((d: any, idx: number) => (
                    <StructureItem key={idx} type="deparser" name={d.name} />
                  ))}
                </div>
              </div>
            )}

          </div>
        )}
      </div>
    </>
  );
}
