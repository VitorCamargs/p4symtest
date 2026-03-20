import { useState } from 'react';
import Editor from '@monaco-editor/react';
import { Play, Code2, Settings2, Trash2, Loader2 } from 'lucide-react';
import { uploadP4, analyzeParser, analyzeTable, analyzeEgressTable, analyzeDeparser } from '../lib/api';

export default function CenterPanel({
  code,
  onChangeCode,
  hasActiveFile,
  onVerificationComplete,
  onCompileComplete,
  executionChain,
  setExecutionChain,
  lastOutputFile,
  onClearChain,
}: {
  code: string;
  onChangeCode: (newCode: string) => void;
  hasActiveFile: boolean;
  onVerificationComplete: (type: string, name: string, outputFile: string, result: any) => void;
  onCompileComplete: (fsm: any) => void;
  executionChain: string[];
  setExecutionChain: React.Dispatch<React.SetStateAction<string[]>>;
  lastOutputFile: string | null;
  onClearChain: () => void;
}) {
  const [compiledData, setCompiledData] = useState<any>(null);
  const [isCompiling, setIsCompiling] = useState(false);
  const [compileError, setCompileError] = useState<string | null>(null);
  const [verifyingNode, setVerifyingNode] = useState<string | null>(null);
  const [verifyError, setVerifyError] = useState<string | null>(null);

  // ── Derive which pipeline a table belongs to from compiledData ──────────────
  const getPipelineName = (tableName: string): string | null => {
    if (!compiledData?.pipelines) return null;
    for (const pipeline of compiledData.pipelines) {
      if (pipeline.tables?.some((t: any) => t.name === tableName)) {
        return pipeline.name; // 'ingress' or 'egress'
      }
    }
    return null;
  };

  // ── Compile ─────────────────────────────────────────────────────────────────
  const handleCompile = async () => {
    setIsCompiling(true);
    setCompileError(null);
    onClearChain();
    try {
      const blob = new Blob([code], { type: 'text/plain' });
      const result = await uploadP4(blob, 'programa.p4');
      setCompiledData(result.fsm_data);
      onCompileComplete(result.fsm_data);
    } catch (err: any) {
      setCompileError(err.message ?? 'Compile failed');
    } finally {
      setIsCompiling(false);
    }
  };

  // ── Verify ──────────────────────────────────────────────────────────────────
  const handleVerifyNode = async (type: string, name: string) => {
    setVerifyingNode(name);
    setVerifyError(null);

    // Visual chain update
    const shortName = name.split('.').pop() || name;
    if (type === 'parser') {
      setExecutionChain([shortName]);
    } else {
      setExecutionChain(prev => [...prev, shortName]);
    }

    try {
      let outputFile: string;
      let result: any;

      if (type === 'parser') {
        const res = await analyzeParser();
        outputFile = res.output_file;
        result = res.states; // array of path objects

      } else if (type === 'deparser') {
        if (!lastOutputFile) throw new Error('No input state available. Run parser first.');
        const res = await analyzeDeparser(lastOutputFile);
        outputFile = res.output_file;
        result = res.analysis_results;

      } else {
        // table (ingress or egress)
        if (!lastOutputFile) throw new Error('No input state available. Run parser first.');
        const switchId = 's1'; // TODO: read from NetworkConfigModal context
        const pipelineName = getPipelineName(name);

        let res: any;
        if (pipelineName === 'egress') {
          res = await analyzeEgressTable(name, switchId, lastOutputFile);
        } else {
          res = await analyzeTable(name, switchId, lastOutputFile);
        }
        outputFile = res.output_file;
        result = res.output_states;
      }

      onVerificationComplete(type, name, outputFile, result);
    } catch (err: any) {
      setVerifyError(err.message ?? 'Verification failed');
      // Roll back the chain item we optimistically added
      setExecutionChain(prev => prev.slice(0, -1));
    } finally {
      setVerifyingNode(null);
    }
  };

  // ── Sub-component: single structure row ─────────────────────────────────────
  const StructureItem = ({ type, name }: { type: string, name: string }) => {
    const isDisabled = type !== 'parser' && executionChain.length === 0;
    const isLoading = verifyingNode === name;

    return (
      <div style={{
        background: 'var(--bg-surface)', padding: '0.8rem 1rem', borderRadius: '6px',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        opacity: isDisabled ? 0.6 : 1
      }}>
        <h4 style={{ margin: 0, color: 'var(--text-main)', fontSize: '0.85rem' }}>{name}</h4>
        <button
          onClick={() => handleVerifyNode(type, name)}
          disabled={isDisabled || !!verifyingNode}
          style={{
            background: isDisabled ? 'transparent' : 'var(--border)',
            color: isDisabled ? 'var(--text-muted)' : 'white',
            border: isDisabled ? '1px solid var(--border)' : 'none',
            padding: '0.3rem 0.6rem',
            borderRadius: '4px',
            cursor: isDisabled || !!verifyingNode ? 'not-allowed' : 'pointer',
            fontSize: '0.75rem',
            display: 'flex', alignItems: 'center', gap: '0.3rem'
          }}
          title={isDisabled ? 'Run parser first to load an input state' : 'Run Verification'}
        >
          {isLoading
            ? <><Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} /> Running...</>
            : 'Verify'
          }
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
          disabled={isCompiling || !hasActiveFile}
          style={{
            display: 'flex', alignItems: 'center', gap: '0.4rem',
            background: 'var(--accent)', color: '#fff',
            border: 'none', padding: '0.4rem 0.8rem',
            borderRadius: '4px', cursor: (isCompiling || !hasActiveFile) ? 'not-allowed' : 'pointer',
            fontWeight: 600, fontSize: '0.8rem', opacity: (isCompiling || !hasActiveFile) ? 0.7 : 1
          }}
        >
          {isCompiling
            ? <><Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> Compiling...</>
            : <><Play size={14} fill="currentColor" /> Compile Program</>
          }
        </button>
      </div>

      {compileError && (
        <div style={{
          background: 'rgba(239,68,68,0.1)', borderBottom: '1px solid rgba(239,68,68,0.3)',
          padding: '0.5rem 1rem', fontSize: '0.75rem', color: '#ef4444'
        }}>
          ⚠ Compile error: {compileError}
        </div>
      )}

      <div style={{ flex: 1, minHeight: 0, position: 'relative' }}>
        {!hasActiveFile ? (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            Select or create a file in the File Manager to start editing.
          </div>
        ) : (
          <Editor
            height="100%"
            defaultLanguage="cpp"
            theme="vs-dark"
            value={code}
            onChange={(val) => onChangeCode(val || '')}
            options={{ minimap: { enabled: false }, fontSize: 13, padding: { top: 16 } }}
          />
        )}
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
              onClick={onClearChain}
              style={{ background: 'transparent', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', color: 'var(--danger)', padding: '0 0 0 0.4rem', marginLeft: '0.2rem', borderLeft: '1px solid var(--border)' }}
              title="Clear Input State"
            >
              <Trash2 size={12} />
            </button>
          )}
        </div>
      </div>

      {verifyError && (
        <div style={{
          background: 'rgba(239,68,68,0.1)', borderBottom: '1px solid rgba(239,68,68,0.3)',
          padding: '0.5rem 1rem', fontSize: '0.75rem', color: '#ef4444'
        }}>
          ⚠ Verification error: {verifyError}
        </div>
      )}

      <div className="panel-content" style={{ flex: 'none', height: '30%', overflowY: 'auto' }}>
        {!compiledData ? (
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', textAlign: 'center', marginTop: '2rem' }}>
            Paste your P4 code above and click Compile to view structures.
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

      {/* Spinner keyframe */}
      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </>
  );
}
