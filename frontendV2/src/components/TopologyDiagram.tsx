import { useCallback } from 'react';
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  addEdge,
  Handle,
  Position,
} from '@xyflow/react';
import type { Connection, Edge, Node } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Plus } from 'lucide-react';

export type TopologyNode = Node;
export type TopologyEdge = Edge;

// -- Custom Node Components with Tooltips --
function CustomHostNode({ data }: { data: any }) {
  return (
    <div title={`Node Type: Host\nIP: ${data.ip ?? 'N/A'}\nMAC: ${data.mac ?? 'N/A'}`} style={{ padding: '8px 12px', background: '#222', color: 'white', borderRadius: '4px', border: '1px solid #555', fontSize: '0.8rem', textAlign: 'center', minWidth: '120px' }}>
      <Handle type="target" position={Position.Top} style={{ background: '#555' }} />
      <strong>{data.label}</strong>
      <div style={{ fontSize: '0.65rem', color: '#999', marginTop: '2px' }}>{data.ip}</div>
      <Handle type="source" position={Position.Bottom} style={{ background: '#555' }} />
    </div>
  );
}

function CustomSwitchNode({ data }: { data: any }) {
  return (
    <div title={`Node Type: Switch\nIP: ${data.ip ?? 'N/A'}\nMAC: ${data.mac ?? 'N/A'}`} style={{ padding: '8px 12px', background: 'var(--bg-panel)', color: 'white', borderRadius: '4px', border: '2px solid var(--accent)', fontSize: '0.8rem', textAlign: 'center', minWidth: '100px' }}>
      <Handle type="target" position={Position.Top} style={{ background: 'var(--accent)' }} />
      <strong>{data.label}</strong>
      <div style={{ fontSize: '0.65rem', color: 'var(--accent)', marginTop: '2px' }}>{data.mac}</div>
      <Handle type="source" position={Position.Bottom} style={{ background: 'var(--accent)' }} />
    </div>
  );
}

const nodeTypes = {
  customHost: CustomHostNode,
  customSwitch: CustomSwitchNode,
};

const defaultNodes: TopologyNode[] = [
  { id: 'h1', position: { x: 50, y: 150 }, data: { label: 'Host 1', ip: '10.0.1.10', mac: '00:00:00:00:01:00' }, type: 'customHost' },
  { id: 's1', position: { x: 250, y: 150 }, data: { label: 'Switch 1', ip: '192.168.1.1', mac: '00:aa:bb:cc:dd:01' }, type: 'customSwitch' },
  { id: 's2', position: { x: 450, y: 150 }, data: { label: 'Switch 2', ip: '192.168.1.2', mac: '00:aa:bb:cc:dd:02' }, type: 'customSwitch' },
  { id: 'h2', position: { x: 650, y: 150 }, data: { label: 'Host 2', ip: '10.0.2.10', mac: '00:00:00:00:02:00' }, type: 'customHost' },
];

const defaultEdges: TopologyEdge[] = [
  { id: 'e-h1-s1', source: 'h1', target: 's1', animated: true, style: { stroke: 'var(--accent)' } },
  { id: 'e-s1-s2', source: 's1', target: 's2', animated: false, style: { stroke: '#ffffff' } },
  { id: 'e-s2-h2', source: 's2', target: 'h2', animated: true, style: { stroke: 'var(--accent)' } },
];

interface TopologyDiagramProps {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  onNodesChange: (nodes: TopologyNode[]) => void;
  onEdgesChange: (edges: TopologyEdge[]) => void;
}

export default function TopologyDiagram({ nodes, edges, onNodesChange, onEdgesChange }: TopologyDiagramProps) {
  const [internalNodes, setInternalNodes, onInternalNodesChange] = useNodesState(nodes.length ? nodes : defaultNodes);
  const [internalEdges, setInternalEdges, onInternalEdgesChange] = useEdgesState(edges.length ? edges : defaultEdges);

  // Sync internal changes to parent
  const handleNodesChange = useCallback((changes: any) => {
    onInternalNodesChange(changes);
    setTimeout(() => onNodesChange(internalNodes), 0);
  }, [internalNodes, onInternalNodesChange, onNodesChange]);

  const handleEdgesChange = useCallback((changes: any) => {
    onInternalEdgesChange(changes);
    setTimeout(() => onEdgesChange(internalEdges), 0);
  }, [internalEdges, onInternalEdgesChange, onEdgesChange]);

  const onConnect = useCallback((params: Connection | Edge) => {
    // If it's a connection between a host and a switch, make it animated and blue
    const isHostConnection = params.source?.startsWith('h') || params.target?.startsWith('h');
    const newParams = {
      ...params,
      animated: isHostConnection,
      style: { stroke: isHostConnection ? 'var(--accent)' : '#ffffff' },
    };
    const newEdges = addEdge(newParams, internalEdges);
    setInternalEdges(newEdges);
    onEdgesChange(newEdges);
  }, [internalEdges, setInternalEdges, onEdgesChange]);

  const addSwitch = () => {
    const swCount = internalNodes.filter(n => n.id.startsWith('s')).length;
    const sId = `s${swCount + 1}`;
    const newNode: TopologyNode = {
      id: sId,
      position: { x: 350, y: 250 },
      data: { label: `Switch ${swCount + 1}`, ip: `192.168.1.${swCount + 1}`, mac: `00:aa:bb:cc:dd:0${swCount + 1}` },
      type: 'customSwitch'
    };
    const newNodes = [...internalNodes, newNode];
    setInternalNodes(newNodes);
    onNodesChange(newNodes);
  };

  const addHost = () => {
    const hCount = internalNodes.filter(n => n.id.startsWith('h')).length;
    const hId = `h${hCount + 1}`;
    const newNode: TopologyNode = {
      id: hId,
      position: { x: 350, y: 50 },
      data: { label: `Host ${hCount + 1}`, ip: `10.0.${hCount + 1}.10`, mac: `00:00:00:00:0${hCount + 1}:00` },
      type: 'customHost'
    };
    const newNodes = [...internalNodes, newNode];
    setInternalNodes(newNodes);
    onNodesChange(newNodes);
  };

  return (
    <div style={{ position: 'relative', width: '100%', height: '45vh', minHeight: '350px', flexShrink: 0, background: 'var(--bg-dark)', borderRadius: '8px', border: '1px solid var(--border)' }}>
      <div style={{ position: 'absolute', top: 10, left: 10, zIndex: 10, display: 'flex', gap: '0.5rem' }}>
        <button onClick={addSwitch} style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', background: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-main)', padding: '0.3rem 0.6rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem' }}>
          <Plus size={14} /> Add Switch
        </button>
        <button onClick={addHost} style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', background: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-main)', padding: '0.3rem 0.6rem', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem' }}>
          <Plus size={14} /> Add Host
        </button>
      </div>

      <ReactFlow
        nodes={internalNodes}
        edges={internalEdges}
        nodeTypes={nodeTypes}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={onConnect}
        colorMode="dark"
        fitView
      >
        <Controls />
        <MiniMap nodeStrokeColor="#fff" nodeColor="var(--bg-panel)" maskColor="rgba(0,0,0,0.3)" />
        <Background gap={16} size={1} />
      </ReactFlow>
    </div>
  );
}

export { defaultEdges, defaultNodes };
