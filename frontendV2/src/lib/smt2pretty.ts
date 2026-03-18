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

/**
 * Parse an ITE (if-then-else) SMT2 string into branches.
 * Returns array of { condition: string, result: string }
 */
export interface IteBranch {
  condition: string;
  result: string;
}

export function parseIte(smt: string, resultField = ''): IteBranch[] | null {
  const branches: IteBranch[] = [];
  let s = smt.trim();

  // Strip outer (let ...) wrapper if present
  const letMatch = s.match(/^\(let \(.*?\)\n?\s*([\s\S]+)\)/s);
  if (letMatch) s = letMatch[1].trim();

  const processIte = (expr: string): void => {
    const iteMatch = expr.match(/^\(ite \(= ([a-zA-Z0-9_.$]+) (#[xb][0-9a-fA-F]+)\)\s*(#[xb][0-9a-fA-F]+)\s*([\s\S]+)\)$/s);
    if (!iteMatch) return;
    const [, condField, condVal, result, rest] = iteMatch;
    branches.push({
      condition: `${prettyField(condField)} == ${prettyFieldValue(condVal, condField)}`,
      result: prettyFieldValue(result, resultField || condField),
    });
    if (rest.trim().startsWith('(ite')) {
      processIte(rest.trim());
    } else {
      const elseVal = rest.trim();
      branches.push({
        condition: 'else',
        result: elseVal.startsWith('#') ? prettyFieldValue(elseVal, resultField || condField) : elseVal,
      });
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
