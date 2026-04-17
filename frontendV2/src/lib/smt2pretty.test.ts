import { describe, expect, it } from 'vitest';
import { parseConstraint } from './smt2pretty';

describe('parseConstraint', () => {
  it('parses reversed equality for valid-bit constraints', () => {
    const parsed = parseConstraint('(= #b1 ipv4.$valid$)');
    expect(parsed.isComplex).toBe(false);
    expect(parsed.field).toBe('hdr.ipv4.isValid()');
    expect(parsed.op).toBe('==');
    expect(parsed.value).toBe('true');
  });

  it('parses reversed equality for metadata scalar constraints', () => {
    const parsed = parseConstraint('(= #x01 scalars.metadata.condicao)');
    expect(parsed.isComplex).toBe(false);
    expect(parsed.field).toBe('hdr.scalars.metadata.condicao');
    expect(parsed.op).toBe('==');
    expect(parsed.value).toBe('1');
  });

  it('normalizes distinct no-drop constraints as egress_spec != DROP', () => {
    const parsed = parseConstraint(
      '(let ((a!1 (ite (= ipv4.dstAddr #x0a00010a) #b000000001 standard_metadata.egress_spec))) (distinct #b111111111 a!1))'
    );
    expect(parsed.isComplex).toBe(false);
    expect(parsed.field).toBe('standard_metadata.egress_spec');
    expect(parsed.op).toBe('!=');
    expect(parsed.value).toBe('DROP (511)');
  });
});

