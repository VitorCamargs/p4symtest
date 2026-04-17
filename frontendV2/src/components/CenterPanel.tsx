import { useState, useRef, useEffect } from 'react';
import Editor from '@monaco-editor/react';
import { Play, Code2, Settings2, Loader2, LocateFixed, ChevronDown, ArrowRight } from 'lucide-react';
import { uploadP4, analyzeParser, analyzeTable, analyzeEgressTable, analyzeDeparser, getComponents, syncExecutionConfig } from '../lib/api';
import type { SourceInfo } from '../lib/api';
import type { TopologyConfig } from './NetworkConfigModal';

export default function CenterPanel({
  code,
  onChangeCode,
  hasActiveFile,
  onVerificationComplete,
  onCompileComplete,
  executionChain,
  stageHistory,
  currentStageIndex,
  onSelectStage,
  lastOutputFile,
  onClearChain,
  networkConfig,
}: {
  code: string;
  onChangeCode: (newCode: string) => void;
  hasActiveFile: boolean;
  onVerificationComplete: (type: string, name: string, outputFile: string, result: any) => void;
  onCompileComplete: (fsm: any) => void;
  executionChain: string[];
  stageHistory: Array<{ chain: string[] }>;
  currentStageIndex: number;
  onSelectStage: (index: number) => void;
  lastOutputFile: string | null;
  onClearChain: () => void;
  networkConfig: TopologyConfig | null;
}) {
  const [compiledData, setCompiledData] = useState<any>(null);
  const [isCompiling, setIsCompiling] = useState(false);
  const [compileError, setCompileError] = useState<string | null>(null);
  const [verifyingNode, setVerifyingNode] = useState<string | null>(null);
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const [isStageMenuOpen, setIsStageMenuOpen] = useState(false);

  const editorRef = useRef<any>(null);
  const monacoRef = useRef<any>(null);
  const decorationsRef = useRef<any[]>([]);
  const stageMenuRef = useRef<HTMLDivElement | null>(null);
  const stagePathScrollRef = useRef<HTMLDivElement | null>(null);

  const handleEditorDidMount = (editor: any, monaco: any) => {
    editorRef.current = editor;
    monacoRef.current = monaco;
  };

  // ── Helper to find the matching closing brace line ──────────────────────────
  const findBlockEndLine = (source: string, startLine: number): number => {
    const lines = source.split('\n');
    let openBraces = 0;
    let foundInitialBrace = false;

    // Scan from the startLine downwards
    for (let i = startLine - 1; i < lines.length; i++) {
        const lineStr = lines[i];
        
        for (let char of lineStr) {
            if (char === '{') {
                openBraces++;
                foundInitialBrace = true;
            } else if (char === '}') {
                openBraces--;
                if (foundInitialBrace && openBraces === 0) {
                    return i + 1; // 1-indexed
                }
            }
        }
        
        // If we haven't encountered a block brace yet, check if this is an implicit multi-line primitive block (like contiguous assignments).
        // We traverse downwards until we hit a clear struct/closure keyword or the end of the file.
        if (!foundInitialBrace) {
            if (i < lines.length - 1) {
                // Look ahead to the next line skipping blank lines. If it starts a new major block or a condition, stop.
                let nextIdx = i + 1;
                while (nextIdx < lines.length && lines[nextIdx].trim() === '') nextIdx++;
                
                if (nextIdx < lines.length) {
                    const nextLineTrim = lines[nextIdx].trim();
                    if (nextLineTrim.match(/^(if|else|while|switch|table|action|control|apply)\b/) || nextLineTrim.startsWith('}')) {
                        return i + 1; // Stop at the current line
                    }
                }
            }
        }
    }
    return startLine; // Fallback
  };

  const jumpToSource = (info: SourceInfo | undefined) => {
    if (!info || !editorRef.current || !monacoRef.current) return;
    const { line } = info;
    const endLine = findBlockEndLine(code, line);

    editorRef.current.revealLineInCenter(line);
    editorRef.current.setPosition({ lineNumber: line, column: 1 });
    
    decorationsRef.current = editorRef.current.deltaDecorations(
      decorationsRef.current,
      [
        {
          range: new monacoRef.current.Range(line, 1, endLine, 1),
          options: {
            isWholeLine: true,
            className: 'myLineHighlight',
          }
        }
      ]
    );
  };


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

  const currentStageChain = stageHistory[currentStageIndex]?.chain ?? [];
  const getPrefixStageIndex = (depth: number): number => {
    if (depth <= 0) return 0;
    const prefix = currentStageChain.slice(0, depth);
    for (let i = currentStageIndex; i >= 0; i--) {
      const chain = stageHistory[i]?.chain ?? [];
      if (chain.length !== depth) continue;
      let same = true;
      for (let j = 0; j < depth; j++) {
        if (chain[j] !== prefix[j]) {
          same = false;
          break;
        }
      }
      if (same) return i;
    }
    return 0;
  };

  useEffect(() => {
    const onDocClick = (evt: MouseEvent) => {
      const node = stageMenuRef.current;
      if (!node) return;
      if (evt.target instanceof Node && !node.contains(evt.target)) {
        setIsStageMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, []);

  useEffect(() => {
    const node = stagePathScrollRef.current;
    if (!node) return;
    requestAnimationFrame(() => {
      node.scrollLeft = node.scrollWidth;
    });
  }, [currentStageIndex, currentStageChain.join('->')]);

  // ── Compile ─────────────────────────────────────────────────────────────────
  const handleCompile = async () => {
    setIsCompiling(true);
    setCompileError(null);
    onClearChain();
    try {
      const blob = new Blob([code], { type: 'text/plain' });
      const result = await uploadP4(blob, 'programa.p4');
      setCompiledData(result.fsm_data);
      // Also fetch the enriched components (which includes table_schemas)
      const components = await getComponents();
      onCompileComplete({ ...result.fsm_data, ...components });
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
        if (!networkConfig) throw new Error('Network configuration is not available yet.');

        await syncExecutionConfig(networkConfig);

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
    } finally {
      setVerifyingNode(null);
    }
  };

  // ── Sub-component: single structure row ─────────────────────────────────────
  const StructureItem = ({ type, name, sourceInfo }: { type: string, name: string, sourceInfo?: SourceInfo }) => {
    const isDisabled = type !== 'parser' && executionChain.length === 0;
    const isLoading = verifyingNode === name;
    const isJumpable = !!sourceInfo;

    return (
      <div
        onClick={() => {
          if (sourceInfo) jumpToSource(sourceInfo);
        }}
        style={{
          background: 'var(--bg-surface)', padding: '0.8rem 1rem', borderRadius: '6px',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          opacity: isDisabled ? 0.6 : 1,
          cursor: isJumpable ? 'pointer' : 'default',
          transition: 'background 0.15s ease',
        }}
      >
        <div
          style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flex: 1, minWidth: 0 }}
        >
          <h4 style={{ margin: 0, color: 'var(--text-main)', fontSize: '0.85rem' }}>{name}</h4>
          {sourceInfo && (
            <span
              title={`Jump to line ${sourceInfo.line}`}
              style={{
                background: 'rgba(59, 130, 246, 0.1)',
                border: '1px solid rgba(59, 130, 246, 0.4)',
                color: 'var(--accent)',
                borderRadius: '4px',
                padding: '0.2rem',
                display: 'flex',
                alignItems: 'center',
                flexShrink: 0,
              }}
            >
              <LocateFixed size={12} />
            </span>
          )}
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation();
            handleVerifyNode(type, name);
          }}
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
            onMount={handleEditorDidMount}
            onChange={(val) => onChangeCode(val || '')}
            options={{ minimap: { enabled: false }, fontSize: 13, padding: { top: 16 } }}
          />
        )}
      </div>

      <div className="panel-header" style={{ borderTop: '1px solid var(--border)', borderBottom: '1px solid var(--border)', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <Settings2 size={18} /> Compiled Structures
        </div>

        {/* Loaded Stage: two-line layout (title + horizontal scroll path) */}
        <div ref={stageMenuRef} style={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'stretch', gap: '0.25rem', background: 'var(--bg-surface)', padding: '0.28rem 0.45rem 0.35rem 0.45rem', borderRadius: '6px', border: '1px solid var(--border)', width: '540px', maxWidth: '540px', minWidth: '320px' }}>
          <span style={{ fontSize: '0.6rem', letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--text-muted)', whiteSpace: 'nowrap', alignSelf: 'flex-start' }}>
            Loaded Stage
          </span>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', minWidth: 0 }}>
            <div ref={stagePathScrollRef} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', whiteSpace: 'nowrap', overflowX: 'auto', overflowY: 'hidden', paddingBottom: '0.08rem', flex: 1, minWidth: 0 }}>
              {currentStageChain.length === 0 ? (
                <div style={{ background: 'var(--bg-dark)', color: 'var(--text-muted)', padding: '0.2rem 0.58rem', borderRadius: '12px', border: '1px solid var(--border)', fontSize: '0.72rem', fontFamily: 'monospace', flexShrink: 0 }}>
                  None
                </div>
              ) : (
                currentStageChain.map((step, idx) => {
                  const prefixStageIndex = getPrefixStageIndex(idx + 1);
                  const isCurrent = idx === currentStageChain.length - 1;
                  return (
                    <div key={`${step}-${idx}`} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', flexShrink: 0 }}>
                      <button
                        onClick={() => onSelectStage(prefixStageIndex)}
                        disabled={!!verifyingNode}
                        style={{
                          background: 'var(--bg-dark)',
                          color: isCurrent ? 'var(--accent)' : 'var(--text-main)',
                          border: isCurrent ? '1px solid var(--accent)' : '1px solid var(--border)',
                          cursor: verifyingNode ? 'not-allowed' : 'pointer',
                          borderRadius: '12px',
                          padding: '0.2rem 0.65rem',
                          fontSize: '0.72rem',
                          fontFamily: 'monospace',
                          opacity: verifyingNode ? 0.7 : 1,
                          flexShrink: 0,
                        }}
                        title={`Go to stage: ${currentStageChain.slice(0, idx + 1).join(' -> ')}`}
                      >
                        {step}
                      </button>
                      {idx < currentStageChain.length - 1 && <ArrowRight size={12} color="var(--text-muted)" />}
                    </div>
                  );
                })
              )}
            </div>

            <button
              onClick={() => !verifyingNode && setIsStageMenuOpen((v) => !v)}
              disabled={!!verifyingNode}
              style={{
                background: 'transparent',
                border: 'none',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--text-muted)',
                cursor: verifyingNode ? 'not-allowed' : 'pointer',
                opacity: verifyingNode ? 0.7 : 1,
                padding: '0 0.1rem',
                flexShrink: 0,
              }}
              title="Open stage menu"
            >
              <ChevronDown size={14} />
            </button>
          </div>

          {isStageMenuOpen && (
            <div style={{ position: 'absolute', right: 0, top: 'calc(100% + 0.35rem)', background: 'var(--bg-panel)', border: '1px solid var(--border)', borderRadius: '6px', minWidth: '320px', maxWidth: '520px', maxHeight: '260px', overflowY: 'auto', zIndex: 30, boxShadow: '0 8px 24px rgba(0,0,0,0.35)' }}>
              {stageHistory.map((stage, idx) => {
                const label = idx === 0 ? 'None' : stage.chain.join(' -> ');
                const selected = idx === currentStageIndex;
                return (
                  <button
                    key={idx}
                    onClick={() => {
                      onSelectStage(idx);
                      setIsStageMenuOpen(false);
                    }}
                    style={{
                      width: '100%',
                      textAlign: 'left',
                      background: selected ? 'rgba(56,189,248,0.12)' : 'transparent',
                      color: selected ? 'var(--accent)' : 'var(--text-main)',
                      border: 'none',
                      borderBottom: idx < stageHistory.length - 1 ? '1px solid rgba(255,255,255,0.06)' : 'none',
                      padding: '0.5rem 0.7rem',
                      cursor: 'pointer',
                      fontSize: '0.74rem',
                      fontFamily: 'monospace',
                    }}
                    title={label}
                  >
                    {label}
                  </button>
                );
              })}
              {stageHistory.length > 1 && (
                <button
                  onClick={() => {
                    onSelectStage(0);
                    setIsStageMenuOpen(false);
                  }}
                  style={{
                    width: '100%',
                    textAlign: 'left',
                    background: 'rgba(239,68,68,0.08)',
                    color: '#fca5a5',
                    border: 'none',
                    borderTop: '1px solid rgba(239,68,68,0.2)',
                    padding: '0.5rem 0.7rem',
                    cursor: 'pointer',
                    fontSize: '0.74rem',
                    fontFamily: 'monospace',
                  }}
                >
                  Load None
                </button>
              )}
            </div>
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
                    <StructureItem key={idx} type="parser" name={p.name} sourceInfo={p.source_info} />
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
                    <StructureItem key={idx} type="table" name={table.name} sourceInfo={table.source_info} />
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
                    <StructureItem key={idx} type="deparser" name={d.name} sourceInfo={d.source_info} />
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
