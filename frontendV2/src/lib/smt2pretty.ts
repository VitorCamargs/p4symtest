// smt2pretty.ts — SMT2 expression pretty-printer utilities

// ---- EtherType lookup ----
const ETHER_TYPES: Record<number, string> = {
  0x0800: 'IPv4 (0x0800)',
  0x0806: 'ARP (0x0806)',
  0x86DD: 'IPv6 (0x86DD)',
  0x8100: 'VLAN (0x8100)',
  0x1212: 'MyTunnel (0x1212)',
  0x88CC: 'LLDP (0x88CC)',
};

// ---- Field-aware value formatter ----
/** Format a raw SMT2 literal based on the field it belongs to. */
export function prettyFieldValue(rawLiteral: string, fieldName: string): string {
  const field = fieldName.toLowerCase();

  // Decode numeric value from hex or binary literal
  let numVal: number | null = null;
  if (rawLiteral.startsWith('#x')) numVal = parseInt(rawLiteral.slice(2), 16);
  else if (rawLiteral.startsWith('#b')) numVal = parseInt(rawLiteral.slice(2), 2);

  if (numVal === null) return rawLiteral; // pass-through for non-literals

  // 1-bit booleans (valid flags)
  if (rawLiteral.startsWith('#b') && rawLiteral.slice(2).length === 1) {
    return numVal === 1 ? 'true' : 'false';
  }

  // EtherType field
  if (field.includes('ethertype') || field.includes('ethertype')) {
    return ETHER_TYPES[numVal] ?? `0x${numVal.toString(16).toUpperCase().padStart(4, '0')}`;
  }

  // MAC address (48-bit → xx:xx:xx:xx:xx:xx)
  if (
    field.includes('srcaddr') || field.includes('dstaddr') ||
    field.includes('smac') || field.includes('dmac') ||
    field.includes('mac') || numVal > 0xFFFF_FFFF
  ) {
    if (numVal >= 0 && numVal <= 0xFFFF_FFFF_FFFF) {
      const hex = numVal.toString(16).padStart(12, '0');
      return hex.match(/.{2}/g)!.join(':');
    }
  }

  // IP address (32-bit)
  if (field.includes('ipaddr') || field.includes('dstaddr') || field.includes('srcaddr')) {
    if (numVal >= 0 && numVal <= 0xFFFF_FFFF) {
      return `${(numVal >>> 24) & 0xff}.${(numVal >>> 16) & 0xff}.${(numVal >>> 8) & 0xff}.${numVal & 0xff}`;
    }
  }

  // Egress spec — port 511 = DROP
  if (field.includes('egress_spec') || field.includes('egress_port')) {
    if (numVal === 511) return 'DROP (511)';
    return `port ${numVal}`;
  }

  // Default: decimal
  return String(numVal);
}

/** Convert a field name like "ethernet.etherType" → "hdr.ethernet.etherType" */
export function prettyField(f: string): string {
  if (f.includes('.$valid$')) return `hdr.${f.replace('.$valid$', '').replace('$valid$', '')}.isValid()`;
  if (f.startsWith('standard_metadata.')) return f;
  return `hdr.${f}`;
}

/** Represent one parsed constraint as a simple {field, op, value, negated} object. */
export interface ParsedConstraint {
  original: string;
  field?: string;
  op?: '==' | '!=' | 'is true' | 'is false';
  value?: string;
  isComplex: boolean;
}

export function parseConstraint(smt: string): ParsedConstraint {
  // Simple equality: (= field.name #x...)
  const eqMatch = smt.match(/^\(= ([a-zA-Z0-9_.$]+) (#[xb][0-9a-fA-F]+)\)$/);
  if (eqMatch) {
    return {
      original: smt,
      field: prettyField(eqMatch[1]),
      op: '==',
      value: prettyFieldValue(eqMatch[2], eqMatch[1]),
      isComplex: false,
    };
  }
  // Negated equality: (not (= field.name #x...))
  const notEqMatch = smt.match(/^\(not \(= ([a-zA-Z0-9_.$]+) (#[xb][0-9a-fA-F]+)\)\)$/);
  if (notEqMatch) {
    return {
      original: smt,
      field: prettyField(notEqMatch[1]),
      op: '!=',
      value: prettyFieldValue(notEqMatch[2], notEqMatch[1]),
      isComplex: false,
    };
  }
  return { original: smt, isComplex: true };
}

export interface IteBranch {
  condition: string;
  result: string;
}

function splitSexpr(s: string): string[] {
  const tokens: string[] = [];
  let depth = 0;
  let current = '';
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (c === '(') {
      depth++;
      current += c;
    } else if (c === ')') {
      depth--;
      current += c;
      if (depth === 0) {
        tokens.push(current.trim());
        current = '';
      }
    } else if (/\\s/.test(c)) {
      if (depth === 0) {
        if (current.trim()) {
          tokens.push(current.trim());
          current = '';
        }
      } else {
        current += c;
      }
    } else {
      current += c;
    }
  }
  if (current.trim()) tokens.push(current.trim());
  return tokens;
}

export function parseIte(smt: string, resultField = ''): IteBranch[] | null {
  const branches: IteBranch[] = [];
  let s = smt.trim();

  // Strip outer (let ...) wrapper if present
  const letMatch = s.match(/^\\(let\\s+\\(.*?\\)\\s+([\\s\\S]+)\\)$/s);
  if (letMatch) s = letMatch[1].trim();
  const letMatch2 = s.match(/^\\(let\\s+\\(\\(.*?\\)\\)\\n?\\s*([\\s\\S]+)\\)$/s);
  if (letMatch2) s = letMatch2[1].trim();

  const processIte = (expr: string): void => {
    expr = expr.trim();
    if (!expr.startsWith('(ite ') || !expr.endsWith(')')) {
      branches.push({
        condition: 'Always',
        result: expr.startsWith('#') ? prettyFieldValue(expr, resultField) : expr,
      });
      return;
    }
    
    const inner = expr.substring(4, expr.length - 1).trim();
    const tokens = splitSexpr(inner);
    
    if (tokens.length >= 3) {
      const cond = tokens[0];
      const res = tokens[1];
      const fls = tokens.slice(2).join(' ');

      let prettyCond = cond;
      const eqMatch = cond.match(/^\\(=\\s+([a-zA-Z0-9_.$]+)\\s+([^\\s()]+)\\)$/);
      if (eqMatch) {
        prettyCond = `${prettyField(eqMatch[1])} == ${prettyFieldValue(eqMatch[2], eqMatch[1])}`;
      } else if (cond.startsWith('(or ')) {
        const orInner = splitSexpr(cond.substring(4, cond.length - 1));
        const orItems = orInner.map(c => {
           const cEq = c.match(/^\\(=\\s+([a-zA-Z0-9_.$]+)\\s+([^\\s()]+)\\)$/);
           if (cEq) return `${prettyField(cEq[1])} == ${prettyFieldValue(cEq[2], cEq[1])}`;
           return c;
        });
        prettyCond = orItems.join(' OR ');
      } else if (cond.startsWith('(not ')) {
        const notInner = cond.substring(5, cond.length - 1).trim();
        const cEq = notInner.match(/^\\(=\\s+([a-zA-Z0-9_.$]+)\\s+([^\\s()]+)\\)$/);
        if (cEq) {
          prettyCond = `${prettyField(cEq[1])} != ${prettyFieldValue(cEq[2], cEq[1])}`;
        } else {
          prettyCond = `NOT ${notInner}`;
        }
      }

      let formattedRes = res.startsWith('#') ? prettyFieldValue(res, resultField) : res;
      if (formattedRes.includes('(bvadd #xff ')) {
         const m = formattedRes.match(/\(bvadd #xff\s+([a-zA-Z0-9_.$]+)\)/);
         if (m) formattedRes = `${prettyField(m[1])} - 1`;
      }

      branches.push({
        condition: prettyCond,
        result: formattedRes,
      });

      if (fls.startsWith('(ite')) {
        processIte(fls);
      } else if (fls.trim() !== resultField && fls.trim() !== '') {
        let flsRes = fls.startsWith('#') ? prettyFieldValue(fls, resultField) : fls;
        if (flsRes.includes('(bvadd #xff ')) {
           const m = flsRes.match(/\(bvadd #xff\s+([a-zA-Z0-9_.$]+)\)/);
           if (m) flsRes = `${prettyField(m[1])} - 1`;
        }
        branches.push({
          condition: 'else',
          result: flsRes,
        });
      }
    } else {
       branches.push({ condition: 'Always', result: expr });
    }
  };

  processIte(s);
  return branches.length > 0 ? branches : null;
}

/** Convert a distinct SMT expression to readable "not all equal to drop" */
export function prettyComplexConstraint(smt: string): string {
  if (smt.includes('distinct') && smt.includes('#b111111111')) return 'egress_spec ≠ DROP (511) — packet is forwarded';
  if (smt.includes('distinct')) return 'Result must be distinct (valid forward path)';
  if (smt.includes('(let')) return 'Forwarding decision (ITE expression)';
  return smt;
}
