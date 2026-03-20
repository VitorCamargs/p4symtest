import { useState, useEffect, useCallback } from 'react';
import LeftPanel from './components/LeftPanel';
import CenterPanel from './components/CenterPanel';
import RightPanel from './components/RightPanel';
import './App.css';

function App() {
  const [activeVerification, setActiveVerification] = useState<{ type: string, name: string } | null>(null);
  const [executionChain, setExecutionChain] = useState<string[]>([]);

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

  // Tracks the output_file from the last API response so the next analysis
  // can use it as input_states.
  const [lastOutputFile, setLastOutputFile] = useState<string | null>(null);

  // The raw API response for the active verification (paths, states, etc.)
  const [verificationResult, setVerificationResult] = useState<any>(null);

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
    setActiveVerification({ type, name });
    setLastOutputFile(outputFile);
    setVerificationResult(result);
  };

  // Reset the whole chain when the user clears it.
  const handleClearChain = () => {
    setExecutionChain([]);
    setLastOutputFile(null);
    setVerificationResult(null);
    setActiveVerification(null);
    // compiledData is kept — user can still see structures after clearing chain
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
          setExecutionChain={setExecutionChain}
          lastOutputFile={lastOutputFile}
          onClearChain={handleClearChain}
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
          compiledData={compiledData}
        />
      </div>
    </div>
  );
}

export default App;
