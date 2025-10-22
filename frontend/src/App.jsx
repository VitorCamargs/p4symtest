import React, { useState, useEffect } from 'react';
import { Play, FileCode, CheckCircle, XCircle, AlertCircle, ChevronRight, Upload, Network, Eye } from 'lucide-react';

const P4SymTestInterface = () => {
  const [p4Code, setP4Code] = useState('');
  const [fsmData, setFsmData] = useState(null);
  const [parserStates, setParserStates] = useState(null);
  const [topology, setTopology] = useState(null);
  const [runtimeConfig, setRuntimeConfig] = useState(null);
  const [reachabilityData, setReachabilityData] = useState(null); 
  const [selectedComponent, setSelectedComponent] = useState(null);
  const [selectedSwitch, setSelectedSwitch] = useState('s1');
  const [verificationResults, setVerificationResults] = useState([]);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisHistory, setAnalysisHistory] = useState([]);
  const [showParserGraph, setShowParserGraph] = useState(false);
  const [parserGraphSVG, setParserGraphSVG] = useState(null);
  const [apiBaseUrl] = useState('http://localhost:5000/api');

  useEffect(() => {
    if (fsmData) {
      console.log('FSM Data carregado:', fsmData);
    }
  }, [fsmData]);

  useEffect(() => {
    if (!fsmData) return;

    const fetchReachability = async () => {
      try {
        const response = await fetch(`${apiBaseUrl}/analyze/reachability`, {
          method: 'POST'
        });
        const data = await response.json();
        
        if (response.ok) {
          setReachabilityData(data.reachability);
          console.log('Dados de alcançabilidade carregados:', data.reachability);
        } else {
          console.error('Erro ao buscar alcançabilidade:', data.error);
        }
      } catch (error) {
        console.error('Erro no fetch de alcançabilidade:', error);
      }
    };
    
    fetchReachability();
  }, [fsmData, apiBaseUrl]);

  const extractComponents = () => {
    if (!fsmData) {
      return {
        parser: null,
        tables: []
      };
    }
    
    console.log('Extraindo componentes do FSM:', fsmData);
    
    const components = { 
      parser: null, 
      tables: []
    };
    
    const parser = fsmData.parsers?.[0];

    if (parser) {
      components.parser = {
        name: parser.name || 'Parser',
        states: parser.parse_states ? parser.parse_states.length : 0
      };
      console.log('Parser encontrado:', components.parser);
    }
    
    const ingress = (fsmData.pipelines ?? []).find(p => p.name === 'ingress');
    
    if (ingress && ingress.tables) {
      components.tables = ingress.tables.map(t => {
        let reachability = "Carregando...";
        let reachabilityConditions = [];
        
        if (reachabilityData && reachabilityData[t.name]) {
          const conditions = reachabilityData[t.name].conditions;
          reachabilityConditions = conditions;
          
          if (conditions.length === 1 && conditions[0] === 'Incondicional') {
            reachability = "Sempre alcançável";
          } else if (conditions.length === 1 && conditions[0] === 'INALCANÇÁVEL') {
            reachability = "Nunca alcançável";
          } else {
            reachability = `${conditions.length} condição(ões)`;
          }
        }
        
        return {
          name: t.name,
          reachability: reachability,
          reachabilityConditions: reachabilityConditions
        };
      });
    }
    
    console.log('Componentes extraídos:', components);
    return components;
  };

  const components = extractComponents();

  const generateParserGraph = () => {
    const svg = `
      <svg width="600" height="400" xmlns="http://www.w3.org/2000/svg">
        <circle cx="100" cy="50" r="30" fill="#E0E7FF" stroke="#4F46E5" stroke-width="2"/>
        <text x="100" y="55" text-anchor="middle" font-size="12" font-weight="bold">start</text>
        
        <circle cx="300" cy="50" r="40" fill="#DBEAFE" stroke="#2563EB" stroke-width="2"/>
        <text x="300" y="50" text-anchor="middle" font-size="11">parse_</text>
        <text x="300" y="63" text-anchor="middle" font-size="11">ethernet</text>
        
        <circle cx="200" cy="200" r="40" fill="#DBEAFE" stroke="#2563EB" stroke-width="2"/>
        <text x="200" y="200" text-anchor="middle" font-size="11">parse_ipv4</text>
        
        <circle cx="400" cy="200" r="40" fill="#DBEAFE" stroke="#2563EB" stroke-width="2"/>
        <text x="400" y="200" text-anchor="middle" font-size="11">parse_</text>
        <text x="400" y="213" text-anchor="middle" font-size="11">myTunnel</text>
        
        <circle cx="300" cy="350" r="35" fill="#D1FAE5" stroke="#10B981" stroke-width="2"/>
        <text x="300" y="355" text-anchor="middle" font-size="12" font-weight="bold">accept</text>
        
        <defs>
          <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#4B5563" />
          </marker>
        </defs>
        
        <line x1="130" y1="50" x2="260" y2="50" stroke="#4B5563" stroke-width="2" marker-end="url(#arrowhead)"/>
        <text x="195" y="45" font-size="10" fill="#6B7280">start</text>
        
        <line x1="280" y1="85" x2="220" y2="165" stroke="#4B5563" stroke-width="2" marker-end="url(#arrowhead)"/>
        <text x="220" y="120" font-size="10" fill="#6B7280">0x0800</text>
        
        <line x1="320" y1="85" x2="380" y2="165" stroke="#4B5563" stroke-width="2" marker-end="url(#arrowhead)"/>
        <text x="360" y="120" font-size="10" fill="#6B7280">0x1212</text>
        
        <line x1="200" y1="240" x2="270" y2="320" stroke="#4B5563" stroke-width="2" marker-end="url(#arrowhead)"/>
        
        <line x1="400" y1="240" x2="330" y2="320" stroke="#4B5563" stroke-width="2" marker-end="url(#arrowhead)"/>
      </svg>
    `;
    setParserGraphSVG(svg);
  };

  const analyzeComponent = async (componentType, componentName, tableInfo) => {
    setIsAnalyzing(true);
    setSelectedComponent({ type: componentType, name: componentName });
    
    try {
      let results = [];
      
      if (componentType === 'parser') {
        const response = await fetch(`${apiBaseUrl}/analyze/parser`, {
          method: 'POST'
        });
        
        const data = await response.json();
        
        if (!response.ok) {
          alert(`Erro: ${data.error}\n${data.details || ''}`);
          setIsAnalyzing(false);
          return;
        }
        
        const states = data.states || [];
        results.push({
          id: 1,
          status: 'success',
          summary: 'Análise Simbólica do Parser',
          message: `${states.length} caminhos simbólicos viáveis identificados`,
          details: states.map((s, idx) => 
            `Caminho ${idx + 1}: ${s.description}`
          )
        });
        
        if (data.parser_info) {
          results.push({
            id: 2,
            status: 'info',
            summary: 'Estrutura do Parser',
            details: data.parser_info.states.map(s => 
              `${s.name}: ${s.operations} operações, ${s.transitions} transições`
            ),
            message: 'Estados do parser mapeados'
          });
        }
        
        generateParserGraph();
        
      } else if (componentType === 'table') {
        // Adiciona card de condições de alcançabilidade se existir
        if (tableInfo && tableInfo.reachabilityConditions && tableInfo.reachabilityConditions.length > 0) {
          const conditions = tableInfo.reachabilityConditions;
          
          if (conditions[0] === 'Incondicional') {
            results.push({
              id: 0,
              status: 'success',
              title: 'Alcançabilidade',
              message: 'Esta tabela é SEMPRE alcançável (sem condições)',
              reachabilityCheck: true
            });
          } else if (conditions[0] === 'INALCANÇÁVEL') {
            results.push({
              id: 0,
              status: 'error',
              title: 'Alcançabilidade',
              message: 'Esta tabela NUNCA pode ser alcançada no pipeline',
              reachabilityCheck: true
            });
          } else {
            results.push({
              id: 0,
              status: 'info',
              title: 'Condições de Alcançabilidade do Pipeline',
              constraints: conditions,
              message: 'Esta tabela só é alcançável quando as seguintes condições são verdadeiras:',
              reachabilityCheck: true
            });
          }
        }
        
        const response = await fetch(`${apiBaseUrl}/analyze/table`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            table_name: componentName,
            switch_id: selectedSwitch,
            input_states: 'parser_states.json'
          })
        });
        
        const data = await response.json();
        
        if (!response.ok) {
          alert(`Erro: ${data.error}\n${data.details || ''}`);
          setIsAnalyzing(false);
          return;
        }
        
        const tableResults = data.results || [];
        let resultId = 1;
        
        for (const stateResult of tableResults) {
          if (stateResult.reachability_check === 'unreachable') {
            results.push({
              id: resultId++,
              status: 'warning',
              title: `Estado ${stateResult.state_id}`,
              message: 'Inalcançável - pacote nunca chegará a esta tabela',
              constraints: [stateResult.description]
            });
          } else {            
            for (const fwd of stateResult.forwarding_results || []) {
              results.push({
                id: resultId++,
                status: 'success',
                title: `Estado ${stateResult.state_id}: Para ${fwd.target}`,
                action: 'forward',
                message: `Encaminhado para porta ${fwd.port}`,
                reachable: true
              });
            }
        
            for (const drop of stateResult.drops || []) {
              results.push({
                id: resultId++,
                status: 'warning',
                title: `Estado ${stateResult.state_id}: Para ${drop.target}`,
                action: 'drop',
                message: 'Pacote descartado',
                reachable: true
              });
            }
          }
        }
        
        if (results.length === 0 || (results.length === 1 && results[0].reachabilityCheck)) {
          results.push({
            id: resultId++,
            status: 'info',
            message: 'Nenhum resultado específico encontrado para esta tabela'
          });
        }
      }
      
      setVerificationResults(results);
      setAnalysisHistory(prev => [...prev, {
        timestamp: new Date().toLocaleTimeString(),
        component: `${componentType}: ${componentName}`,
        resultsCount: results.length
      }]);
      
    } catch (error) {
      alert('Erro na análise: ' + error.message);
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleFileUpload = async (fileType, event) => {
    const file = event.target.files[0];
    if (!file) return;
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      let endpoint = '';
      
      if (fileType === 'p4') {
        endpoint = `${apiBaseUrl}/upload/p4`;
        const response = await fetch(endpoint, {
          method: 'POST',
          body: formData
        });
        
        const data = await response.json();
        if (response.ok) {
          setFsmData(data.fsm_data);
          alert('Código P4 compilado com sucesso!');
        } else {
          alert(`Erro: ${data.error}\n${data.details || ''}`);
        }
      } else if (fileType === 'json') {
        const reader = new FileReader();
        reader.onload = async (e) => {
          const content = e.target.result;
          try {
            const jsonData = JSON.parse(content);
            let jsonType = 'unknown';
            
            if (jsonData.parsers || jsonData.pipelines) {
              jsonType = 'fsm';
              setFsmData(jsonData);
            } else if (jsonData[0] && jsonData[0].z3_constraints_smt2) {
              jsonType = 'parser_states';
              setParserStates(jsonData);
            } else if (jsonData.switches || jsonData.hosts) {
              jsonType = 'topology';
              setTopology(jsonData);
            } else {
              jsonType = 'runtime_config';
              setRuntimeConfig(jsonData);
            }
            
            const jsonFormData = new FormData();
            jsonFormData.append('file', file);
            jsonFormData.append('type', jsonType);
            endpoint = `${apiBaseUrl}/upload/json`;
            
            const response = await fetch(endpoint, {
              method: 'POST',
              body: jsonFormData
            });
            
            const data = await response.json();
            if (response.ok) {
              alert(`Arquivo ${jsonType} carregado com sucesso!`);
            }
          } catch (err) {
            alert('Erro ao processar JSON: ' + err.message);
          }
        };
        reader.readAsText(file);
      }
    } catch (error) {
      alert('Erro ao fazer upload: ' + error.message);
    }
  };

  const ComponentCard = ({ type, name, icon, tableInfo }) => {
    return (
      <button
        onClick={() => analyzeComponent(type, name, tableInfo)}
        className={`w-full p-3 text-left rounded-lg border-2 transition-all hover:border-blue-500 hover:bg-blue-50 ${
          selectedComponent && selectedComponent.name === name ? 'border-blue-500 bg-blue-50' : 'border-gray-200'
        }`}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            {icon}
            <div className="flex-1">
              <span className="font-mono text-sm block">{name}</span>
              {tableInfo && tableInfo.reachability && (
                <span className="text-xs text-gray-500 mt-1 block">
                  {tableInfo.reachability}
                </span>
              )}
            </div>
          </div>
          <ChevronRight className="w-4 h-4 text-gray-400" />
        </div>
      </button>
    );
  };

  const ResultCard = ({ result }) => {
    const statusConfig = {
      success: { icon: CheckCircle, color: 'text-green-600', bg: 'bg-green-50', border: 'border-green-200' },
      warning: { icon: AlertCircle, color: 'text-yellow-600', bg: 'bg-yellow-50', border: 'border-yellow-200' },
      error: { icon: XCircle, color: 'text-red-600', bg: 'bg-red-50', border: 'border-red-200' },
      info: { icon: AlertCircle, color: 'text-blue-600', bg: 'bg-blue-50', border: 'border-blue-200' }
    };
    
    const config = statusConfig[result.status];
    const Icon = config.icon;
    
    return (
      <div className={`p-4 rounded-lg border-2 ${config.border} ${config.bg}`}>
        <div className="flex items-start space-x-3">
          <Icon className={`w-5 h-5 ${config.color} flex-shrink-0 mt-0.5`} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between mb-2">
              <h4 className="font-semibold text-sm text-gray-900">
                {result.title || result.path || result.entry || result.condition || result.summary || 'Resultado'}
              </h4>
              {result.action && (
                <span className="text-xs font-mono bg-white px-2 py-1 rounded border border-gray-300">
                  {result.action}
                </span>
              )}
            </div>
            
            <p className="text-sm text-gray-700 mb-2">{result.message}</p>
            
            {result.details && (
              <div className="mt-2 space-y-1">
                {result.details.map((detail, idx) => (
                  <div key={idx} className="text-xs bg-white px-3 py-1.5 rounded border border-gray-200">
                    {detail}
                  </div>
                ))}
              </div>
            )}
            
            {result.constraints && result.constraints.length > 0 && (
              <div className="mt-2">
                <p className="text-xs font-semibold text-gray-600 mb-1">
                  {result.reachabilityCheck ? 'Restrições de Alcançabilidade:' : 'Restrições Simbólicas:'}
                </p>
                <div className="space-y-1">
                  {result.constraints.map((constraint, idx) => (
                    <code key={idx} className="block text-xs bg-white px-2 py-1 rounded border border-gray-200 break-words">
                      {constraint}
                    </code>
                  ))}
                </div>
              </div>
            )}
            
            {result.headers && (
              <div className="mt-2">
                <p className="text-xs font-semibold text-gray-600 mb-1">Headers presentes:</p>
                <div className="flex flex-wrap gap-1">
                  {result.headers.map((header, idx) => (
                    <span key={idx} className="text-xs bg-white px-2 py-0.5 rounded border border-gray-200">
                      {header}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-gradient-to-r from-blue-600 to-blue-800 text-white p-6 shadow-lg">
        <div className="max-w-7xl mx-auto">
          <h1 className="text-3xl font-bold mb-2">P4SymTest</h1>
          <p className="text-blue-100">Framework para Verificação Modular de Programas P4</p>
        </div>
      </div>

      <div className="max-w-7xl mx-auto p-6">
        <div className="bg-white rounded-lg shadow-md p-6 mb-6">
          <h2 className="text-lg font-bold mb-4 flex items-center">
            <Upload className="w-5 h-5 mr-2" />
            Carregar Arquivos
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Código P4</label>
              <input
                type="file"
                accept=".p4"
                onChange={(e) => handleFileUpload('p4', e)}
                className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">FSM JSON</label>
              <input
                type="file"
                accept=".json"
                onChange={(e) => handleFileUpload('json', e)}
                className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Topology JSON</label>
              <input
                type="file"
                accept=".json"
                onChange={(e) => handleFileUpload('json', e)}
                className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Runtime Config</label>
              <input
                type="file"
                accept=".json"
                onChange={(e) => handleFileUpload('json', e)}
                className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
              />
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-1 space-y-6">
            <div className="bg-white rounded-lg shadow-md p-6">
              <h2 className="text-lg font-bold mb-4">Componentes do Programa</h2>
              
              {components.parser && (
                <div className="mb-4">
                  <h3 className="text-sm font-semibold text-gray-700 mb-2">Parser</h3>
                  <button
                    onClick={() => analyzeComponent('parser', components.parser.name)}
                    className={`w-full p-4 text-left rounded-lg border-2 transition-all hover:border-purple-500 hover:bg-purple-50 ${
                      selectedComponent && selectedComponent.name === components.parser.name ? 'border-purple-500 bg-purple-50' : 'border-gray-200'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-3">
                        <div className="w-10 h-10 bg-purple-500 rounded-lg flex items-center justify-center">
                          <Network className="w-6 h-6 text-white" />
                        </div>
                        <div>
                          <div className="font-mono text-sm font-semibold">{components.parser.name}</div>
                          <div className="text-xs text-gray-500 mt-0.5">
                            {components.parser.states} estados • Análise simbólica completa
                          </div>
                        </div>
                      </div>
                      <ChevronRight className="w-5 h-5 text-gray-400" />
                    </div>
                  </button>
                  
                  {parserGraphSVG && (
                    <button
                      onClick={() => setShowParserGraph(!showParserGraph)}
                      className="w-full mt-2 p-2 text-sm text-purple-700 bg-purple-50 rounded-lg border border-purple-200 hover:bg-purple-100 transition-all flex items-center justify-center"
                    >
                      <Eye className="w-4 h-4 mr-2" />
                      {showParserGraph ? 'Ocultar' : 'Visualizar'} Grafo FSM
                    </button>
                  )}
                  
                  {showParserGraph && parserGraphSVG && (
                    <div className="mt-3 p-4 bg-gray-50 rounded-lg border border-gray-200">
                      <div className="overflow-x-auto">
                        <div dangerouslySetInnerHTML={{ __html: parserGraphSVG }} />
                      </div>
                    </div>
                  )}
                </div>
              )}

              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-2">Match-Action Tables</h3>
                <div className="space-y-2">
                  {components.tables.map(table => (
                    <ComponentCard 
                      key={table.name}
                      type="table"
                      name={table.name}
                      tableInfo={table}
                      icon={<div className="w-3 h-3 bg-blue-500 rounded-full" />}
                    />
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="lg:col-span-2">
            <div className="bg-white rounded-lg shadow-md p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-bold flex items-center">
                  <Play className="w-5 h-5 mr-2" />
                  Resultados da Verificação
                </h2>
                {selectedComponent && (
                  <span className="text-sm text-gray-600 font-mono">
                    {selectedComponent.type}: {selectedComponent.name}
                  </span>
                )}
              </div>

              {isAnalyzing ? (
                <div className="flex flex-col items-center justify-center py-12">
                  <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mb-4"></div>
                  <p className="text-gray-600">Analisando componente...</p>
                </div>
              ) : verificationResults.length > 0 ? (
                <div className="space-y-4">
                  {verificationResults.map(result => (
                    <ResultCard key={result.id} result={result} />
                  ))}
                </div>
              ) : (
                <div className="text-center py-12 text-gray-500">
                  <AlertCircle className="w-12 h-12 mx-auto mb-3 text-gray-400" />
                  <p>Selecione um componente para iniciar a verificação</p>
                </div>
              )}

              {analysisHistory.length > 0 && (
                <div className="mt-6 pt-6 border-t border-gray-200">
                  <h3 className="text-sm font-semibold text-gray-700 mb-3">Histórico de Análises</h3>
                  <div className="space-y-2">
                    {analysisHistory.slice(-5).reverse().map((entry, idx) => (
                      <div key={idx} className="flex items-center justify-between text-sm p-2 bg-gray-50 rounded">
                        <span className="font-mono text-xs">{entry.component}</span>
                        <div className="flex items-center space-x-2">
                          <span className="text-gray-500 text-xs">{entry.timestamp}</span>
                          <span className="bg-blue-100 text-blue-700 px-2 py-0.5 rounded text-xs">
                            {entry.resultsCount} resultados
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default P4SymTestInterface;