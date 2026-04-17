import { useState, useEffect, useCallback } from 'react';
import LeftPanel from './components/LeftPanel';
import CenterPanel from './components/CenterPanel';
import RightPanel from './components/RightPanel';
import type { TopologyConfig } from './components/NetworkConfigModal';
import './App.css';

type VerificationTarget = { type: string; name: string } | null;

type StageSnapshot = {
  chain: string[];
  outputFile: string | null;
  verification: VerificationTarget;
  result: any;
  parentIndex: number | null;
};

const EMPTY_STAGE: StageSnapshot = {
  chain: [],
  outputFile: null,
  verification: null,
  result: null,
  parentIndex: null,
};

function App() {
  const [networkConfig, setNetworkConfig] = useState<TopologyConfig | null>(null);

  // Full FSM data from last compile (needed by RightPanel for conditionals lookup)
  const [compiledData, setCompiledData] = useState<any>(null);

  // ---- File State ----
  const [files, setFiles] = useState<{name: string, content: string}[]>([]);
  const [activeFileName, setActiveFileName] = useState<string | null>(null);

  const handleCreateFile = (name: string) => {
    if (!name.endsWith('.p4')) name += '.p4';
    if (!files.some(f => f.name === name)) {
      setFiles(prev => [...prev, { name, content: '' }]);
    }
    setActiveFileName(name);
  };

  const handleUploadFile = (name: string, content: string) => {
    setFiles(prev => {
      const idx = prev.findIndex(f => f.name === name);
      if (idx !== -1) {
         const newFiles = [...prev];
         newFiles[idx] = { name, content };
         return newFiles;
      }
      return [...prev, { name, content }];
    });
    setActiveFileName(name);
  };

  const handleChangeCode = (newCode: string) => {
    if (!activeFileName) return;
    setFiles(prev => prev.map(f => f.name === activeFileName ? { ...f, content: newCode } : f));
  };

  const activeCode = files.find(f => f.name === activeFileName)?.content || '';

  // Stage history: each successful verify creates a new selectable snapshot.
  const [stageHistory, setStageHistory] = useState<StageSnapshot[]>([EMPTY_STAGE]);
  const [currentStageIndex, setCurrentStageIndex] = useState(0);

  const currentStage = stageHistory[currentStageIndex] ?? EMPTY_STAGE;
  const executionChain = currentStage.chain;
  const lastOutputFile = currentStage.outputFile;
  const activeVerification = currentStage.verification;
  const verificationResult = currentStage.result;
  const parentVerificationResult =
    currentStage.parentIndex !== null && currentStage.parentIndex >= 0 && currentStage.parentIndex < stageHistory.length
      ? stageHistory[currentStage.parentIndex]?.result ?? null
      : null;

  // Left panel is toggled between 15vw and 60px
  const [isLeftCollapsed, setIsLeftCollapsed] = useState(false);

  // Right panel resizer
  const [rightWidth, setRightWidth] = useState(window.innerWidth * 0.25);
  const [isDragging, setIsDragging] = useState(false);

  const MIN_RIGHT_WIDTH = 250;
  const MAX_RIGHT_WIDTH = window.innerWidth * 0.6;

  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isDragging) return;

    let newWidth = window.innerWidth - e.clientX;

    if (newWidth < MIN_RIGHT_WIDTH) newWidth = MIN_RIGHT_WIDTH;
    if (newWidth > MAX_RIGHT_WIDTH) newWidth = MAX_RIGHT_WIDTH;

    setRightWidth(newWidth);
  }, [isDragging, MAX_RIGHT_WIDTH]);

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  useEffect(() => {
    if (isDragging) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    } else {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'default';
      document.body.style.userSelect = '';
    }
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging, handleMouseMove, handleMouseUp]);

  // Called by CenterPanel after a successful analysis API call.
  const handleVerificationComplete = (
    type: string,
    name: string,
    outputFile: string,
    result: any
  ) => {
    const shortName = name.split('.').pop() || name;
    const stepLabel = type === 'parser'
      ? 'Parser'
      : type === 'deparser'
        ? 'Deparser'
        : shortName;

    const baseStage = stageHistory[currentStageIndex] ?? EMPTY_STAGE;
    const nextChain = type === 'parser' ? [stepLabel] : [...baseStage.chain, stepLabel];
    const nextStage: StageSnapshot = {
      chain: nextChain,
      outputFile,
      verification: { type, name },
      result,
      parentIndex: currentStageIndex,
    };

    // Keep full history across branches: never discard prior stages when
    // verifying from an earlier point in the chain.
    setStageHistory((prev) => {
      const next = [...prev, nextStage];
      setCurrentStageIndex(next.length - 1);
      return next;
    });
  };

  // Reset the whole chain when the user clears it.
  const handleClearChain = () => {
    setStageHistory([EMPTY_STAGE]);
    setCurrentStageIndex(0);
    // compiledData is kept — user can still see structures after clearing chain
  };

  const handleSelectStage = (index: number) => {
    if (index < 0 || index >= stageHistory.length) return;
    setCurrentStageIndex(index);
  };

  return (
    <div className="app-container" style={{ display: 'flex', width: '100vw', height: '100vh', overflow: 'hidden' }}>
      <div
        className="left-panel"
        style={{ width: isLeftCollapsed ? '60px' : '15vw', transition: 'width 0.2s ease-out', flexShrink: 0 }}
      >
        <LeftPanel 
          isCollapsed={isLeftCollapsed} 
          onToggle={() => setIsLeftCollapsed(!isLeftCollapsed)}
          files={files.map(f => f.name)}
          activeFileName={activeFileName}
          onCreateFile={handleCreateFile}
          onUploadFile={handleUploadFile}
          onSelectFile={setActiveFileName}
          tableSchemas={compiledData?.table_schemas ?? []}
          onConfigChange={setNetworkConfig}
        />
      </div>

      <div className="center-panel" style={{ flex: 1, minWidth: 0 }}>
        <CenterPanel
          code={activeCode}
          onChangeCode={handleChangeCode}
          hasActiveFile={!!activeFileName}
          onVerificationComplete={handleVerificationComplete}
          onCompileComplete={setCompiledData}
          executionChain={executionChain}
          stageHistory={stageHistory}
          currentStageIndex={currentStageIndex}
          onSelectStage={handleSelectStage}
          lastOutputFile={lastOutputFile}
          onClearChain={handleClearChain}
          networkConfig={networkConfig}
        />
      </div>

      <div
        onMouseDown={handleMouseDown}
        style={{
          width: '8px',
          backgroundColor: isDragging ? 'var(--accent)' : '#333',
          cursor: 'col-resize',
          zIndex: 50,
          transition: 'background-color 0.2s',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center'
        }}
        onMouseEnter={(e) => {
          if (!isDragging) e.currentTarget.style.backgroundColor = 'var(--accent)';
        }}
        onMouseLeave={(e) => {
          if (!isDragging) e.currentTarget.style.backgroundColor = '#333';
        }}
      >
        {/* Subtle visual grip lines */}
        <div style={{ height: '30px', width: '2px', backgroundColor: 'rgba(255,255,255,0.3)', borderRadius: '2px' }} />
      </div>

      <div
        className="right-panel"
        style={{ width: `${rightWidth}px`, flexShrink: 0 }}
      >
        <RightPanel
          activeVerification={activeVerification}
          verificationResult={verificationResult}
          parentVerificationResult={parentVerificationResult}
          compiledData={compiledData}
        />
      </div>
    </div>
  );
}

export default App;
