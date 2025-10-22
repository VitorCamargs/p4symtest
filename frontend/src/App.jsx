import React, { useState, useEffect } from 'react';
import {
  Play, FileCode, CheckCircle, XCircle, AlertCircle, ChevronRight,
  Upload, Network, Eye, LogOut, Layers, // Ícones existentes
  ListFilter // Ícone novo para o seletor de snapshot
} from 'lucide-react';

const P4SymTestInterface = () => {
  // Estados existentes...
  const [fsmData, setFsmData] = useState(null);
  const [topology, setTopology] = useState(null);
  const [runtimeConfig, setRuntimeConfig] = useState(null);
  const [reachabilityData, setReachabilityData] = useState(null);
  const [selectedComponent, setSelectedComponent] = useState(null);
  const [selectedSwitch, setSelectedSwitch] = useState('s1'); // TODO: Permitir seleção de switch
  const [verificationResults, setVerificationResults] = useState([]);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisHistory, setAnalysisHistory] = useState([]);
  const [showParserGraph, setShowParserGraph] = useState(false);
  const [parserGraphSVG, setParserGraphSVG] = useState(null);
  const [apiBaseUrl] = useState('http://localhost:5000/api');

  // Estados para seleção de snapshot
  const defaultSnapshot = 'parser_states.json';
  const [availableSnapshots, setAvailableSnapshots] = useState([defaultSnapshot]);
  const [selectedSnapshot, setSelectedSnapshot] = useState(defaultSnapshot);

  // Efeito para buscar snapshots disponíveis no backend ao montar
  useEffect(() => {
    const fetchSnapshots = async () => {
      try {
        const response = await fetch(`${apiBaseUrl}/info/snapshots`);
        const data = await response.json();
        if (response.ok && data.snapshots) {
           // Garante que o default esteja presente e remove duplicatas
           const updatedSnapshots = Array.from(new Set([defaultSnapshot, ...data.snapshots]));
           // Ordena: parser primeiro, depois alfabeticamente
           updatedSnapshots.sort((a, b) => {
               if (a === defaultSnapshot) return -1;
               if (b === defaultSnapshot) return 1;
               return a.localeCompare(b);
           });
           setAvailableSnapshots(updatedSnapshots);
           // Se o snapshot selecionado não estiver mais na lista (ex: após novo P4), reseta para default
           if (!updatedSnapshots.includes(selectedSnapshot)) {
               setSelectedSnapshot(defaultSnapshot);
           }
        } else {
           console.warn("Não foi possível buscar snapshots do backend, usando default.");
           setAvailableSnapshots([defaultSnapshot]);
           setSelectedSnapshot(defaultSnapshot);
        }
      } catch (error) {
        console.error("Erro ao buscar snapshots:", error);
        setAvailableSnapshots([defaultSnapshot]); // Fallback para o default
        setSelectedSnapshot(defaultSnapshot);
      }
    };
    fetchSnapshots();
    // Executa apenas uma vez ao montar o componente
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBaseUrl]);


  useEffect(() => {
    if (fsmData) {
      console.log('FSM Data carregado:', fsmData);
      // Ao carregar FSM novo, reseta snapshots disponíveis mantendo apenas o default
      // e reseta a seleção para o default
      setAvailableSnapshots([defaultSnapshot]);
      setSelectedSnapshot(defaultSnapshot);
    }
  }, [fsmData]); // Depende apenas de fsmData

  useEffect(() => {
    if (!fsmData) return;
    // Busca alcançabilidade apenas quando fsmData muda
    const fetchReachability = async () => {
      try {
        const response = await fetch(`${apiBaseUrl}/analyze/reachability`, { method: 'POST' });
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fsmData]); // Depende apenas de fsmData

  // Extrai componentes do FSM
  const extractComponents = () => {
    if (!fsmData) return { parser: null, ingressTables: [], egress: null, deparser: null };

    const components = { parser: null, ingressTables: [], egress: null, deparser: null };
    const parser = fsmData.parsers?.[0];
    if (parser) components.parser = { name: parser.name || 'Parser', states: parser.parse_states?.length || 0 };

    const ingress = fsmData.pipelines?.find(p => p.name === 'ingress');
    if (ingress?.tables) {
      components.ingressTables = ingress.tables.map(t => {
        let reachability = "Calculando...";
        let reachabilityConditions = [];
        if (reachabilityData && reachabilityData[t.name]) {
          const conditions = reachabilityData[t.name].conditions;
          reachabilityConditions = conditions;
          if (conditions.length === 1 && conditions[0] === 'Incondicional') reachability = "Sempre alcançável";
          else if (conditions.length === 1 && conditions[0].startsWith('INALCANÇÁVEL')) reachability = "Nunca alcançável";
          else reachability = `${conditions.length} condição(ões)`;
        } else if (fsmData && !reachabilityData) { // Se FSM carregado mas reachability não
           reachability = "Verificando...";
        } else if (fsmData && reachabilityData) { // Se FSM e reachability carregados, mas sem info para esta tabela
            reachability = "Não analisado"; // Ou poderia ser "Inalcançável (implícito)"
        }
        return { name: t.name, reachability, reachabilityConditions };
      });
    }

    const egress = fsmData.pipelines?.find(p => p.name === 'egress');
    if (egress) components.egress = { name: egress.name || 'Egress', tables: egress.tables?.length || 0 };

    const deparser = fsmData.deparsers?.[0];
    if (deparser) components.deparser = { name: deparser.name || 'Deparser', order: deparser.order || [] };

    return components;
  };

  const components = extractComponents();

  // Gera SVG do grafo do parser
  const generateParserGraph = () => {
    // Mantém o SVG estático por enquanto
    const svg = `
      <svg width="600" height="400" xmlns="http://www.w3.org/2000/svg"> <circle cx="100" cy="50" r="30" fill="#E0E7FF" stroke="#4F46E5" stroke-width="2"/> <text x="100" y="55" text-anchor="middle" font-size="12" font-weight="bold">start</text> <circle cx="300" cy="50" r="40" fill="#DBEAFE" stroke="#2563EB" stroke-width="2"/> <text x="300" y="50" text-anchor="middle" font-size="11">parse_</text> <text x="300" y="63" text-anchor="middle" font-size="11">ethernet</text> <circle cx="200" cy="200" r="40" fill="#DBEAFE" stroke="#2563EB" stroke-width="2"/> <text x="200" y="200" text-anchor="middle" font-size="11">parse_ipv4</text> <circle cx="400" cy="200" r="40" fill="#DBEAFE" stroke="#2563EB" stroke-width="2"/> <text x="400" y="200" text-anchor="middle" font-size="11">parse_</text> <text x="400" y="213" text-anchor="middle" font-size="11">myTunnel</text> <circle cx="300" cy="350" r="35" fill="#D1FAE5" stroke="#10B981" stroke-width="2"/> <text x="300" y="355" text-anchor="middle" font-size="12" font-weight="bold">accept</text> <defs> <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto"> <polygon points="0 0, 10 3.5, 0 7" fill="#4B5563" /> </marker> </defs> <line x1="130" y1="50" x2="260" y2="50" stroke="#4B5563" stroke-width="2" marker-end="url(#arrowhead)"/> <text x="195" y="45" font-size="10" fill="#6B7280">start</text> <line x1="280" y1="85" x2="220" y2="165" stroke="#4B5563" stroke-width="2" marker-end="url(#arrowhead)"/> <text x="220" y="120" font-size="10" fill="#6B7280">0x0800</text> <line x1="320" y1="85" x2="380" y2="165" stroke="#4B5563" stroke-width="2" marker-end="url(#arrowhead)"/> <text x="360" y="120" font-size="10" fill="#6B7280">0x1212</text> <line x1="200" y1="240" x2="270" y2="320" stroke="#4B5563" stroke-width="2" marker-end="url(#arrowhead)"/> <line x1="400" y1="240" x2="330" y2="320" stroke="#4B5563" stroke-width="2" marker-end="url(#arrowhead)"/> </svg>
    `;
    setParserGraphSVG(svg);
  };

  // Função de análise para usar selectedSnapshot
  const analyzeComponent = async (componentType, componentName, tableInfo) => {
    setIsAnalyzing(true);
    setSelectedComponent({ type: componentType, name: componentName });
    setVerificationResults([]);

    try {
      let results = [];
      const currentInputSnapshot = selectedSnapshot; // Usa o snapshot selecionado no estado

      // --- ANÁLISE DO PARSER ---
      if (componentType === 'parser') {
        const response = await fetch(`${apiBaseUrl}/analyze/parser`, { method: 'POST' });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Erro na análise do parser');
         const states = data.states || [];
        results.push({
          id: 1, status: 'success', summary: 'Análise Simbólica do Parser',
          message: `${states.length} caminhos simbólicos viáveis identificados.`,
          details: states.map((s, idx) => `Caminho ${idx + 1}: ${s.description}`)
        });
        if (data.parser_info) {
          results.push({
            id: 2, status: 'info', summary: 'Estrutura do Parser',
            details: data.parser_info.states.map(s => `${s.name}: ${s.operations} op, ${s.transitions} trans`),
            message: 'Estados do parser mapeados.'
          });
        }
        // Adiciona o arquivo de saída (parser_states.json) aos snapshots, garantindo que esteja lá
        if (data.output_file && !availableSnapshots.includes(data.output_file)) {
            setAvailableSnapshots(prev => Array.from(new Set([data.output_file, ...prev])));
        }
        generateParserGraph();

      // --- ANÁLISE DE TABELA (INGRESS) ---
      } else if (componentType === 'table') {
        // Card de alcançabilidade
        if (tableInfo?.reachabilityConditions?.length > 0) {
          const conditions = tableInfo.reachabilityConditions;
          if (conditions[0] === 'Incondicional') results.push({ id: 0, status: 'success', title: 'Alcançabilidade no Pipeline', message: 'Esta tabela é SEMPRE alcançável.', reachabilityCheck: true });
          else if (conditions[0].startsWith('INALCANÇÁVEL')) {
             results.push({ id: 0, status: 'error', title: 'Alcançabilidade no Pipeline', message: `Esta tabela NUNCA pode ser alcançada (${conditions[0].split('(')[1]?.replace(')', '') || 'Motivo desconhecido'}). Análise da tabela não executada.`, reachabilityCheck: true });
             setVerificationResults(results); setIsAnalyzing(false); return; // Interrompe se inalcançável
          } else results.push({ id: 0, status: 'info', title: 'Condições de Alcançabilidade do Pipeline', constraints: conditions, message: 'Alcançável SE as seguintes condições do pipeline forem verdadeiras:', reachabilityCheck: true });
        } else if (fsmData && reachabilityData) results.push({ id: 0, status: 'warning', title: 'Alcançabilidade no Pipeline', message: 'Não foi possível determinar a alcançabilidade desta tabela no pipeline (sem dados específicos).', reachabilityCheck: true });
        else if (fsmData) results.push({ id: 0, status: 'info', title: 'Alcançabilidade no Pipeline', message: 'Verificando alcançabilidade...', reachabilityCheck: true });


        // Chama backend usando o snapshot selecionado
        const response = await fetch(`${apiBaseUrl}/analyze/table`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            table_name: componentName,
            switch_id: selectedSwitch,
            input_states: currentInputSnapshot // <-- USA O SNAPSHOT SELECIONADO
          })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(`${data.error || 'Erro desconhecido'}\n${data.details || ''}`);

        // Processamento dos resultados da tabela (stdout summary)
        const summaryResults = data.results_summary || [];
        let resultId = results.length; // Continua IDs a partir do card de alcançabilidade
        for (const summary of summaryResults) {
             results.push({
               id: resultId++,
               // Define status baseado no outcome
               status: summary.outcome === 'Alcançável' ? 'info' : summary.outcome.includes('Drop') ? 'warning' : 'error',
               title: `Resultado para Estado #${summary.state_id}`,
               // Melhora a mensagem de resumo
               message: `Estado de Entrada: ${summary.description}. Resultado: ${summary.outcome}. Detalhes: ${summary.details.join('; ') || (summary.outcome === 'Inalcançável' ? 'Condições contraditórias.' : 'N/A')}`,
               // Mostra a descrição do estado apenas se for inalcançável
               constraints: summary.outcome === 'Inalcançável' ? [summary.description] : []
             });
        }
         // Mensagem genérica se nenhum resultado detalhado foi encontrado
        if (summaryResults.length === 0 && results.length > 0 && results[0].reachabilityCheck && !results[0].message.includes("NUNCA")) {
             results.push({ id: resultId++, status: 'info', message: 'Nenhum comportamento específico (forward/drop) foi identificado para os estados de entrada alcançáveis.' });
        } else if (summaryResults.length === 0 && results.length === 0) {
            results.push({ id: resultId++, status: 'info', message: 'Nenhuma análise detalhada foi retornada.' });
        }

        // Adiciona o arquivo de saída aos snapshots disponíveis
        if (data.output_file && !availableSnapshots.includes(data.output_file)) {
          // Adiciona e reordena
           setAvailableSnapshots(prev => {
                const newSnapshots = Array.from(new Set([...prev, data.output_file]));
                newSnapshots.sort((a, b) => {
                   if (a === defaultSnapshot) return -1;
                   if (b === defaultSnapshot) return 1;
                   return a.localeCompare(b);
                });
                return newSnapshots;
           });
        }

      // --- ANÁLISE DO EGRESS (Placeholder) ---
      } else if (componentType === 'egress') {
        const egressInfo = components.egress;
        results.push({
          id: 1, status: 'info', summary: 'Análise do Egress',
          message: `Análise para '${componentName}' (${egressInfo?.tables || 0} tabelas) usando '${currentInputSnapshot}' ainda não implementada.`,
          details: []
        });

      // --- ANÁLISE DO DEPARSER ---
      } else if (componentType === 'deparser') {
        // Chama backend usando o snapshot selecionado
        const response = await fetch(`${apiBaseUrl}/analyze/deparser`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ input_states: currentInputSnapshot }) // <-- USA O SNAPSHOT SELECIONADO
        });
        const data = await response.json();
        if (!response.ok) throw new Error(`Erro na análise do Deparser: ${data.error}\n${data.details || ''}`);

        const staticInfo = data.static_info || {};
        const analysisResults = data.analysis_results || [];
        let resultId = 1;

        // Card geral
        results.push({
          id: resultId++, status: 'info', summary: `Deparser: ${staticInfo.name || componentName}`,
          message: `Análise baseada no snapshot: '${currentInputSnapshot}'. Ordem de emissão P4:`,
          details: staticInfo.order ? [staticInfo.order.join(' -> ')] : ['Não definida']
        });

        // Cards por estado de entrada
        for (const stateResult of analysisResults) {
           // Pula estados insatisfatíveis, mas informa
           if (stateResult.satisfiable === false) {
                results.push({
                    id: resultId++, status: 'warning',
                    title: `Estado de Entrada #${stateResult.input_state_index} Ignorado`,
                    message: `Estado de Entrada Original: ${stateResult.input_state}. Este estado é insatisfatível (condições contraditórias, possivelmente devido à condição de não-descarte) e foi ignorado nesta análise do deparser.`,
                    // Mostra a condição de não-descarte se foi extraída, para contexto
                    nonDropConditionSmt: stateResult.non_drop_condition_smt
                });
                continue;
           }

          const emissionDetails = stateResult.emission_status.map(item => {
            let statusText = '';
            switch (item.status) {
              case 'Sempre': statusText = '✅ Sempre Emitido'; break;
              case 'Nunca': statusText = '❌ Nunca Emitido'; break;
              case 'Condicional': statusText = '⚠️ Emitido Condicionalmente'; break;
              default: statusText = item.status;
            }
            return `${item.header}: ${statusText}`;
          });

          // Verifica se o snapshot de entrada indica que veio de uma tabela
          const isFromTable = currentInputSnapshot !== defaultSnapshot;
          const stateMessage = `Analisando estado de entrada: ${stateResult.input_state}.`;

          results.push({
            id: resultId++, status: 'info',
            title: `Análise para Estado de Entrada #${stateResult.input_state_index}`,
            message: stateMessage,
            details: emissionDetails,
            // Adiciona a condição de não-descarte se veio de uma tabela E foi retornada
            nonDropConditionSmt: isFromTable ? stateResult.non_drop_condition_smt : null
          });
        }
        if (analysisResults.length === 0 && !results.some(r => r.status === 'warning')) {
             // Adiciona mensagem apenas se não houver resultados nem avisos de estado insatisfatório
             results.push({ id: resultId++, status: 'info', message: 'Nenhum estado de entrada válido foi encontrado no snapshot para análise pelo deparser.' });
        }
      }

      setVerificationResults(results);
      // Adiciona ao início do histórico, limitado a 10 entradas
      setAnalysisHistory(prev => [{ timestamp: new Date().toLocaleTimeString(), component: `${componentType}: ${componentName} (Input: ${currentInputSnapshot})`, resultsCount: results.length }, ...prev].slice(0, 10));

    } catch (error) {
      setVerificationResults([{ id: 'error', status: 'error', summary: 'Erro na Análise', message: error.message }]);
      console.error("Erro detalhado:", error);
    } finally {
      setIsAnalyzing(false);
    }
  };

  // Upload de arquivos
  const handleFileUpload = async (fileType, event) => {
    const file = event.target.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    try {
      let endpoint = '';
      if (fileType === 'p4') {
        endpoint = `${apiBaseUrl}/upload/p4`;
        const response = await fetch(endpoint, { method: 'POST', body: formData });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Erro na compilação P4');
        setFsmData(data.fsm_data);
        alert('Código P4 compilado e FSM carregado!');
        // Resetar estados relacionados ao FSM anterior
        setReachabilityData(null); setVerificationResults([]); setSelectedComponent(null);
        // O useEffect de fsmData cuidará de resetar snapshots
      } else if (fileType === 'json') {
        const reader = new FileReader();
        reader.onload = async (e) => {
          const content = e.target.result;
          try {
            const jsonData = JSON.parse(content);
            let jsonType = 'unknown'; // Tenta inferir o tipo
            if (jsonData.parsers || jsonData.pipelines) jsonType = 'fsm';
            // Verifica se é um array e o primeiro elemento tem a estrutura de estado
            else if (Array.isArray(jsonData) && jsonData.length > 0 && jsonData[0]?.z3_constraints_smt2 !== undefined) jsonType = 'state_file';
            else if (jsonData.switches || jsonData.hosts) jsonType = 'topology';
            else if (typeof jsonData === 'object' && Object.keys(jsonData).some(k => k.startsWith('s'))) jsonType = 'runtime_config';

            // Envia para o backend salvar e retornar o nome/tipo
            const jsonFormData = new FormData();
            jsonFormData.append('file', file); jsonFormData.append('type', jsonType); // Envia o tipo inferido
            endpoint = `${apiBaseUrl}/upload/json`;
            const response = await fetch(endpoint, { method: 'POST', body: jsonFormData });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || `Erro ao carregar JSON ${jsonType}`);

            // Atualiza estado local baseado no tipo confirmado pelo backend ou inferido
            const confirmedType = data.type || jsonType;
            const savedFilename = data.filename || file.name;

            if (confirmedType === 'fsm') {
                 setFsmData(jsonData);
                 setReachabilityData(null); setVerificationResults([]); setSelectedComponent(null);
                 // O useEffect de fsmData cuidará de resetar snapshots
            }
            // Se for um arquivo de estado (parser ou tabela), adiciona à lista de snapshots
            if (confirmedType === 'state_file' || savedFilename.endsWith('_output.json') || savedFilename === 'parser_states.json') {
                if (!availableSnapshots.includes(savedFilename)) {
                     setAvailableSnapshots(prev => {
                          const newSnapshots = Array.from(new Set([...prev, savedFilename]));
                           newSnapshots.sort((a, b) => { // Re-ordena
                               if (a === defaultSnapshot) return -1; if (b === defaultSnapshot) return 1; return a.localeCompare(b);
                           });
                          return newSnapshots;
                     });
                }
            }
            if (confirmedType === 'topology') setTopology(jsonData);
            if (confirmedType === 'runtime_config') setRuntimeConfig(jsonData);

            alert(`Arquivo ${confirmedType} ('${savedFilename}') carregado!`);
          } catch (err) { alert('Erro ao processar JSON: ' + err.message); }
        };
        reader.readAsText(file);
      }
    } catch (error) { alert('Erro no upload: ' + error.message); } finally { event.target.value = null; } // Limpa input
  };

  // --- COMPONENTES DE UI ---

  // Card de Componente
  const ComponentCard = ({ type, name, icon, details, onClick }) => (
    <button onClick={onClick} className={`w-full p-3 text-left rounded-lg border-2 transition-all hover:shadow-md ${ selectedComponent?.name === name ? 'border-blue-500 bg-blue-50 shadow-md ring-1 ring-blue-500' : 'border-gray-200 hover:border-blue-400 hover:bg-blue-50' }`} disabled={!fsmData && type !== 'parser'}>
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-3 min-w-0"> {icon} <div className="flex-1 min-w-0"> <span className="font-mono text-sm block truncate font-semibold">{name}</span> {details && <span className="text-xs text-gray-500 mt-0.5 block truncate">{details}</span>} </div> </div>
        <ChevronRight className="w-4 h-4 text-gray-400 flex-shrink-0 ml-2" />
      </div>
    </button>
  );

  // Card de Resultado
  const ResultCard = ({ result }) => {
    const statusConfig = { success: { icon: CheckCircle, color: 'text-green-600', bg: 'bg-green-50', border: 'border-green-200' }, warning: { icon: AlertCircle, color: 'text-yellow-600', bg: 'bg-yellow-50', border: 'border-yellow-200' }, error: { icon: XCircle, color: 'text-red-600', bg: 'bg-red-50', border: 'border-red-200' }, info: { icon: AlertCircle, color: 'text-blue-600', bg: 'bg-blue-50', border: 'border-blue-200' } };
    const config = statusConfig[result.status] || statusConfig.info; // Default para info
    const Icon = config.icon;
    return (
      <div className={`p-4 rounded-lg border-2 ${config.border} ${config.bg}`}>
         <div className="flex items-start space-x-3">
             <Icon className={`w-5 h-5 ${config.color} flex-shrink-0 mt-0.5`} />
             <div className="flex-1 min-w-0">
                 {/* Título e Ação */}
                 <div className="flex items-center justify-between mb-1">
                     <h4 className="font-semibold text-sm text-gray-900 truncate">{result.title || result.summary || 'Resultado'}</h4>
                     {result.action && <span className="text-xs font-mono bg-white px-2 py-0.5 rounded border border-gray-300 ml-2 flex-shrink-0">{result.action}</span>}
                 </div>
                 {/* Mensagem Principal */}
                 <p className="text-sm text-gray-700 mb-2">{result.message}</p>
                 {/* Condição de Não-Descarte (para resultados do deparser) */}
                 {result.nonDropConditionSmt && (
                    <div className="mt-2 mb-3 p-3 bg-white border border-gray-200 rounded">
                        <p className="text-xs font-semibold text-gray-700 mb-1">Condição de Não-Descarte (SMT-LIB):</p>
                        <code className="block text-xs bg-gray-800 text-gray-200 p-2 rounded whitespace-pre-wrap break-all font-mono shadow-inner">
                         {result.nonDropConditionSmt}
                        </code>
                        <p className="text-xs text-gray-500 mt-1.5">Define os pacotes (do snapshot de entrada) que não foram descartados e são considerados aqui.</p>
                    </div>
                 )}
                 {/* Detalhes (lista) */}
                 {result.details?.length > 0 && <div className="mt-2 space-y-1"> {result.details.map((detail, idx) => <div key={idx} className="text-xs bg-white px-3 py-1.5 rounded border border-gray-200 break-words">{detail}</div>)} </div>}
                 {/* Restrições */}
                 {result.constraints?.length > 0 && <div className="mt-2"> <p className="text-xs font-semibold text-gray-600 mb-1">{result.reachabilityCheck ? 'Restrições de Alcançabilidade (Pipeline):' : 'Restrições Simbólicas (Estado):'}</p> <div className="space-y-1"> {result.constraints.map((constraint, idx) => <code key={idx} className="block text-xs bg-white p-2 rounded border border-gray-200 whitespace-pre-wrap break-all font-mono">{constraint}</code>)} </div> </div>}
             </div>
         </div>
      </div>
    );
  };

  // --- RENDERIZAÇÃO PRINCIPAL ---
  return (
    <div className="min-h-screen bg-gray-100">
      {/* Cabeçalho */}
      <div className="bg-gradient-to-r from-blue-700 to-indigo-800 text-white p-6 shadow-lg sticky top-0 z-10">
        <div className="max-w-7xl mx-auto">
          <h1 className="text-3xl font-bold mb-1">P4SymTest</h1>
          <p className="text-indigo-100">Framework para Verificação Modular de Programas P4</p>
        </div>
      </div>

      <div className="max-w-7xl mx-auto p-4 md:p-6">
        {/* Seção de Upload */}
        <div className="bg-white rounded-lg shadow p-5 mb-6">
          <h2 className="text-lg font-semibold mb-4 flex items-center text-gray-800"> <Upload className="w-5 h-5 mr-2 text-indigo-600" /> Carregar Arquivos </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Inputs de Upload */}
            {[ {label: 'Código P4 (*.p4)', type: 'p4', accept: '.p4'},
               {label: 'FSM (*.json)', type: 'json', accept: '.json'},
               {label: 'Topologia (*.json)', type: 'json', accept: '.json'},
               {label: 'Runtime Cfg (*.json)', type: 'json', accept: '.json'}
             ].map((input, idx) => (
              <div key={idx}>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">{input.label}</label>
                <input type="file" accept={input.accept} onChange={(e) => handleFileUpload(input.type, e)} className="block w-full text-sm text-gray-500 file:mr-3 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-sm file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100 cursor-pointer" />
              </div>
            ))}
          </div>
           {!fsmData && <p className="text-xs text-yellow-600 mt-3">Carregue um arquivo P4 ou FSM JSON para habilitar a análise.</p>}
        </div>

        {/* Layout Principal */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Coluna Esquerda: Snapshot + Componentes */}
          <div className="lg:col-span-1 space-y-5 lg:sticky lg:top-28 self-start"> {/* Sticky para desktop */}
            {/* Bloco de Seleção de Snapshot */}
            <div className="bg-white rounded-lg shadow p-5">
              <h2 className="text-lg font-semibold mb-3 flex items-center text-gray-800">
                 <ListFilter className="w-5 h-5 mr-2 text-indigo-600" />
                 Snapshot de Entrada
              </h2>
              <select
                value={selectedSnapshot}
                onChange={(e) => setSelectedSnapshot(e.target.value)}
                className="w-full p-2 border border-gray-300 rounded bg-white text-sm focus:ring-indigo-500 focus:border-indigo-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
                disabled={!fsmData || isAnalyzing || availableSnapshots.length <= 1}
              >
                {availableSnapshots.map(snapshotFile => {
                   // Formata o nome para exibição
                   let displayName = snapshotFile;
                   if (snapshotFile === defaultSnapshot) displayName = 'Saída do Parser';
                   else if (snapshotFile.includes('_from_')) {
                       // Tenta extrair nome da tabela de forma mais robusta
                       const parts = snapshotFile.split('_from_');
                       const tableNameRaw = parts[0].split('_').slice(1).join('.'); // Reconstitui nome da tabela
                       displayName = `Saída Tabela (${tableNameRaw || '?'})`;
                   } else {
                       // Fallback para nomes não esperados (remove extensões)
                       displayName = snapshotFile.replace('_output.json', '').replace('.json', '');
                   }
                   return ( <option key={snapshotFile} value={snapshotFile}> {displayName} </option> );
                })}
              </select>
               <p className="text-xs text-gray-500 mt-2">Selecione os estados simbólicos de entrada para a próxima análise.</p>
            </div>

            {/* Bloco de Componentes do Programa */}
            <div className="bg-white rounded-lg shadow p-5">
              <h2 className="text-lg font-semibold mb-4 text-gray-800">Componentes do Programa</h2>
              {/* Card do Parser */}
              {components.parser && ( <div className="mb-4"> <h3 className="text-sm font-semibold text-gray-600 mb-2">Parser</h3> <ComponentCard type="parser" name={components.parser.name} icon={<div className="w-8 h-8 bg-purple-100 rounded-lg flex items-center justify-center"><Network className="w-5 h-5 text-purple-600" /></div>} details={`${components.parser.states} estados`} onClick={() => analyzeComponent('parser', components.parser.name)} /> {parserGraphSVG && <button onClick={() => setShowParserGraph(!showParserGraph)} className="w-full mt-2 p-2 text-sm text-purple-700 bg-purple-50 rounded hover:bg-purple-100 transition-all flex items-center justify-center border border-purple-200"> <Eye className="w-4 h-4 mr-1.5" /> {showParserGraph ? 'Ocultar Grafo' : 'Visualizar Grafo'} </button>} {showParserGraph && parserGraphSVG && <div className="mt-3 p-3 bg-gray-50 rounded border border-gray-200 overflow-x-auto"> <div dangerouslySetInnerHTML={{ __html: parserGraphSVG }} /> </div>} </div> )}
              {/* Card das Tabelas de Ingress */}
              <div className="mb-4"> <h3 className="text-sm font-semibold text-gray-600 mb-2">Pipeline de Ingress</h3> <div className="space-y-2"> {components.ingressTables.map(table => <ComponentCard key={table.name} type="table" name={table.name} icon={<div className="w-8 h-8 bg-blue-100 rounded-lg flex items-center justify-center"><FileCode className="w-5 h-5 text-blue-600" /></div>} details={table.reachability} onClick={() => analyzeComponent('table', table.name, table)} />)} {components.ingressTables.length === 0 && fsmData && <p className="text-xs text-gray-400 p-2 text-center">Nenhuma tabela de ingress.</p>} </div> </div>
              {/* Card do Pipeline de Egress */}
              {components.egress && ( <div className="mb-4"> <h3 className="text-sm font-semibold text-gray-600 mb-2">Pipeline de Egress</h3> <ComponentCard type="egress" name={components.egress.name} icon={<div className="w-8 h-8 bg-green-100 rounded-lg flex items-center justify-center"><LogOut className="w-5 h-5 text-green-600" /></div>} details={`${components.egress.tables} tabelas`} onClick={() => analyzeComponent('egress', components.egress.name)} /> </div> )}
              {/* Card do Deparser */}
              {components.deparser && ( <div className="mb-4"> <h3 className="text-sm font-semibold text-gray-600 mb-2">Deparser</h3> <ComponentCard type="deparser" name={components.deparser.name} icon={<div className="w-8 h-8 bg-gray-100 rounded-lg flex items-center justify-center"><Layers className="w-5 h-5 text-gray-600" /></div>} details={`Ordem: ${components.deparser.order.slice(0, 2).join(' -> ')}...`} onClick={() => analyzeComponent('deparser', components.deparser.name)} /> </div> )}
               {!fsmData && <p className="text-xs text-gray-500 text-center py-4">Carregue um FSM para ver os componentes.</p>}
            </div>
          </div>

          {/* Coluna Direita: Resultados */}
          <div className="lg:col-span-2">
            <div className="bg-white rounded-lg shadow p-5 min-h-[400px]">
              {/* Cabeçalho */}
              <div className="flex items-center justify-between mb-4 pb-4 border-b border-gray-200"> <h2 className="text-lg font-semibold flex items-center text-gray-800"> <Play className="w-5 h-5 mr-2 text-indigo-600" /> Resultados da Verificação </h2> {selectedComponent && <span className="text-sm text-gray-500 font-mono bg-gray-100 px-2 py-0.5 rounded"> {selectedComponent.type}: {selectedComponent.name} </span>} </div>
              {/* Conteúdo: Loading, Resultados ou Mensagem Inicial */}
              {isAnalyzing ? ( <div className="flex flex-col items-center justify-center py-16"> <div className="animate-spin rounded-full h-10 w-10 border-t-2 border-b-2 border-indigo-500 mb-3"></div> <p className="text-gray-600">Analisando...</p> </div> ) : verificationResults.length > 0 ? ( <div className="space-y-4 max-h-[70vh] overflow-y-auto pr-2"> {verificationResults.map(result => <ResultCard key={`${result.id}-${result.title}-${result.message.substring(0,10)}`} result={result} />)} </div> ) : ( <div className="text-center py-16 text-gray-500"> <AlertCircle className="w-10 h-10 mx-auto mb-2 text-gray-400" /> <p>Selecione um componente para iniciar a verificação.</p> {!fsmData && <p className="text-xs mt-1">Primeiro, carregue um arquivo P4 ou FSM.</p>} </div> )}
              {/* Histórico */}
              {analysisHistory.length > 0 && ( <div className="mt-6 pt-5 border-t border-gray-200"> <h3 className="text-sm font-semibold text-gray-700 mb-2">Histórico Recente</h3> <div className="space-y-1.5 max-h-40 overflow-y-auto"> {analysisHistory.slice(0, 5).map((entry, idx) => ( <div key={idx} className="flex items-center justify-between text-xs p-2 bg-gray-50 rounded border border-gray-100"> <span className="font-mono truncate mr-2">{entry.component}</span> <div className="flex items-center space-x-2 flex-shrink-0"> <span className="text-gray-400">{entry.timestamp}</span> <span className="bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded text-xs"> {entry.resultsCount} {entry.resultsCount === 1 ? 'resultado' : 'resultados'} </span> </div> </div> ))} </div> </div> )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default P4SymTestInterface;