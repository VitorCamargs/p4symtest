import type { Node, Edge } from '@xyflow/react';
import type { SwitchTableConfig } from '../components/NetworkConfigModal';
import type { TableSchema } from './api';

/**
 * Dynamic auto-population driven entirely by the TableSchema from the P4 program.
 *
 * For every table declared in the schema, we generate a plausible default entry
 * based on the topology (who is connected, which hosts/switches neighbors exist).
 *
 * Field value heuristics:
 *  - Fields containing "addr" or "ip"              → host/subnet IP based on topology
 *  - Fields containing "port" or "spec"            → integer port based on edge index
 *  - Fields containing "mac" or "smac" or "dmac"  → derived MAC from node identity
 *  - Fields containing "id" or "tunnel"            → numeric index
 *  - All others                                    → '0' / '0.0.0.0' / 0 as appropriate
 */

function isSymbolicToken(v: string): boolean {
  const t = v.trim().toLowerCase();
  return t === '' || t === 'symbolic' || t === 'sym' || t === '__symbolic__' || t === '*' || t === 'auto' || t === 'default';
}

function isIpv4(v: string): boolean {
  const m = v.trim().match(/^(\d{1,3})(\.\d{1,3}){3}$/);
  if (!m) return false;
  return v.trim().split('.').every((p) => {
    const n = Number(p);
    return Number.isFinite(n) && n >= 0 && n <= 255;
  });
}

function inferTernaryMask(fieldName: string, value: string): string {
  const f = fieldName.toLowerCase();
  const raw = value.trim();

  if (isSymbolicToken(raw)) return '0.0.0.0';
  if (isIpv4(raw)) {
    if ((f.includes('dstaddr') || f.includes('dst_addr')) && raw.endsWith('.0')) return '255.255.255.0';
    return '255.255.255.255';
  }
  if (f.includes('mac')) return 'ff:ff:ff:ff:ff:ff';
  return '0xffffffff';
}

function guessValue(fieldName: string, context: {
  portNo: string;
  hostIp: string;
  hostMac: string;
  peerIp: string;
  peerMac: string;
  swMac: string;
  peerId: string;
  swId: string;
  isHost: boolean;
  matchType: string;
}, options?: {
  bitwidth?: number;
  isActionParam?: boolean;
}): string {
  const f = fieldName.toLowerCase();
  const bitwidth = options?.bitwidth;

  // Width-aware fast path for action params (avoids dstAddr IPv4/MAC ambiguity).
  if (options?.isActionParam && bitwidth === 48) {
    if (f.includes('src') || f.includes('smac')) return context.swMac;
    return context.peerMac;
  }
  if (options?.isActionParam && bitwidth === 32 && (f.includes('ip') || f.includes('addr'))) {
    if (f.includes('src')) return '0.0.0.0';
    return context.isHost ? context.hostIp : context.peerIp;
  }
  if (options?.isActionParam && bitwidth === 9 && (f.includes('port') || f.includes('spec'))) {
    return context.portNo;
  }

  // IPs / addresses
  if (f.includes('dstaddr') || f.includes('dst_addr') || f.includes('dst_ip')) {
    return context.isHost ? context.hostIp : context.peerIp;
  }
  if (f.includes('srcaddr') || f.includes('src_addr') || f.includes('src_ip')) {
    return '0.0.0.0';
  }
  if (f.includes('addr') || f.includes('ip')) {
    return context.isHost ? context.hostIp : context.peerIp;
  }

  // MACs
  if (f.includes('smac') || f.includes('src_mac')) return context.swMac;
  if (f.includes('dmac') || f.includes('dst_mac') || f.includes('dstaddr') && f.includes('mac')) return context.peerMac;
  if (f.includes('mac')) return context.peerMac;

  // Ports / egress_spec
  if (f.includes('egress_port') || f.includes('egress_spec') || f.includes('port')) return context.portNo;

  // Tunnel / ID numeric fields
  if (f.includes('tunnel') || f.includes('tunnel_id') || f.includes('id')) {
    return String(Number(context.swId.replace('s', '')) * 10 + Number(context.peerId.replace('h', '').replace('s', '')));
  }

  // Prefixes / masks
  if (f.includes('prefix_len') || f.includes('prefix')) return context.isHost ? '32' : '24';

  // Generic fallback: Use empty string (UI will show placeholder)
  return '';
}

export function autoPopulateTables(
  nodes: Node[],
  edges: Edge[],
  existingSwitches: Array<{ id: string; tables: SwitchTableConfig }>,
  tableSchemas: TableSchema[]
): Array<{ id: string; tables: SwitchTableConfig }> {

  const switches = nodes.filter(n => n.id.startsWith('s'));

  return switches.map(swNode => {
    const swId = swNode.id;
    const existing = existingSwitches.find(s => s.id === swId);
    const tables: SwitchTableConfig = existing ? JSON.parse(JSON.stringify(existing.tables)) : {};

    // Ensure every schema table has an array slot
    for (const schema of tableSchemas) {
      if (!tables[schema.name]) tables[schema.name] = [];

      // Normalize existing ternary entries to avoid accidental wildcard-all masks
      // from older UI versions where masks were not visible/editable.
      const normalized = (tables[schema.name] ?? []).map((entry: any) => {
        if (!entry || typeof entry !== 'object') return entry;
        const match = { ...(entry.match ?? {}) };
        const matchMask = { ...(entry.matchMask ?? {}) };

        for (const key of schema.keys) {
          if (key.match_type !== 'ternary') continue;
          const val = String(match[key.field] ?? '').trim();
          const currentMask = String(matchMask[key.field] ?? '').trim();
          if (!val || isSymbolicToken(val)) continue;

          if (!currentMask) {
            matchMask[key.field] = inferTernaryMask(key.field, val);
            continue;
          }

          // Explicit masks (including 0.0.0.0) must be respected.
        }

        return { ...entry, match, matchMask };
      });
      tables[schema.name] = normalized as any[];
    }

    // Find all neighbors of this switch
    const connectedEdges = edges.filter(e => e.source === swId || e.target === swId);

    connectedEdges.forEach((edge, edgeIndex) => {
      const peerId = edge.source === swId ? edge.target : edge.source;
      const isHost = peerId.startsWith('h');

      const portNo = String(edgeIndex + 1);
      const swIndex = swId.replace('s', '');
      const peerIndex = peerId.replace(/[hs]/, '');

      const hostIp    = `10.0.${peerIndex}.10`;
      const subnetIp  = `10.0.${peerIndex}.0`;
      const hostMac   = `00:00:00:00:0${peerIndex}:00`;
      const peerMac   = isHost ? hostMac : `00:aa:bb:cc:dd:0${peerIndex}`;
      const swMac     = String(swNode.data?.mac ?? `00:aa:bb:cc:dd:0${swIndex}`);
      const peerIp    = isHost ? hostIp : subnetIp;

      const ctx = { portNo, hostIp, hostMac, peerIp, peerMac, swMac, peerId, swId, isHost, matchType: '' };

      // For each schema table, add one entry per neighbor if not already populated
      for (const schema of tableSchemas) {
        if (!schema.keys.length) continue; // skip tables with no match keys
        
        // Limit auto-entries: 1 per neighbor, up to 10 per table
        const tableEntries = tables[schema.name] ?? [];
        if (tableEntries.length >= connectedEdges.length && tableEntries.length > 0) continue;

        // Build match fields
        const match: Record<string, string> = {};
        const matchPrefix: Record<string, number> = {};
        const matchMask: Record<string, string> = {};

        for (const key of schema.keys) {
          ctx.matchType = key.match_type;
          const val = guessValue(key.field, ctx);
          match[key.field] = val;
          if (key.match_type === 'lpm') {
            matchPrefix[key.field] = isHost ? 32 : 24;
          } else if (key.match_type === 'ternary') {
            matchMask[key.field] = inferTernaryMask(key.field, val);
          }
        }

        // Dedup: skip if the same match already exists in this table
        const alreadyExists = tableEntries.some(e =>
          schema.keys.every(k => e.match[k.field] === match[k.field])
        );
        if (alreadyExists) continue;

        // Use first action from schema (or default)
        const action = schema.actions[0]?.name ?? schema.default_action;
        const firstAction = schema.actions[0];

        // Build action params from the first action's param list
        const action_params: Record<string, string> = {};
        if (firstAction?.params) {
          for (const param of firstAction.params) {
            ctx.matchType = '';
            action_params[param.name] = guessValue(param.name, ctx, {
              bitwidth: param.bitwidth,
              isActionParam: true,
            });
          }
        }

        const entry: any = { match, action, action_params };
        if (Object.keys(matchPrefix).length) entry.matchPrefix = matchPrefix;
        if (Object.keys(matchMask).length) entry.matchMask = matchMask;

        tables[schema.name] = [...(tables[schema.name] ?? []), entry];
      }
    });

    return { id: swId, tables };
  });
}
