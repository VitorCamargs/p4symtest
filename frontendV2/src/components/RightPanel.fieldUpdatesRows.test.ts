import { describe, expect, it } from 'vitest';
import { buildFieldUpdateRows } from './RightPanel';

function nestedIte(conditions: string[], values: string[], elseValue: string): string {
  if (conditions.length !== values.length) {
    throw new Error('conditions and values must have same length');
  }
  let expr = elseValue;
  for (let i = conditions.length - 1; i >= 0; i--) {
    expr = `(ite ${conditions[i]} ${values[i]} ${expr})`;
  }
  return expr;
}

describe('buildFieldUpdateRows', () => {
  it('renders simple if/else from one exact ite', () => {
    const rows = buildFieldUpdateRows({
      'scalars.metadata.routing_class': '(ite (= ipv4.dstAddr #x0a00010a) #x01 #x00)',
    });

    expect(rows).toHaveLength(2);
    expect(rows[0].label).toBe('hdr.ipv4.dstAddr == 10.0.1.10');
    expect(rows[1].label).toBe('else');
    expect(rows[0].cells[0]).toBe('1');
    expect(rows[1].cells[0]).toBe('0');
  });

  it('renders else if + else for nested exact/lpm branches', () => {
    const rows = buildFieldUpdateRows({
      'scalars.metadata.routing_class': nestedIte(
        [
          '(= ipv4.dstAddr #x0a00010a)',
          '(= ((_ extract 31 8) ipv4.dstAddr) #x0a0002)',
        ],
        ['#x01', '#x02'],
        '#x00'
      ),
    });

    expect(rows).toHaveLength(3);
    expect(rows[0].label).toBe('hdr.ipv4.dstAddr == 10.0.1.10');
    expect(rows[1].label).toMatch(/else if|hdr\.ipv4\.dstAddr in/);
    expect(rows[1].label).toContain('hdr.ipv4.dstAddr in 10.0.2.0/24');
    expect(rows[2].label).toBe('else');
  });

  it('keeps src+dst information on ACL-like second branch', () => {
    const rows = buildFieldUpdateRows({
      'scalars.metadata.routing_class': nestedIte(
        [
          '(and (= ipv4.srcAddr #x00000000) (= ipv4.dstAddr #x0a00010a))',
          '(and (= ipv4.srcAddr #x00000000) (= ((_ extract 31 8) ipv4.dstAddr) #x0a0002))',
        ],
        ['#x01', '#x02'],
        '#x00'
      ),
    });

    expect(rows).toHaveLength(3);
    expect(rows[1].label).toContain('else if');
    expect(rows[1].label).toContain('hdr.ipv4.srcAddr == 0.0.0.0');
    expect(rows[1].label).toContain('hdr.ipv4.dstAddr in 10.0.2.0/24');
    expect(rows[2].label).toBe('else');
  });

  it('handles let-inlined ACL expression without collapsing second branch into raw ite', () => {
    const expr = `(let ((a!1 (ite (and (= ipv4.srcAddr #x00000000)
                                       (= ((_ extract 31 8) ipv4.dstAddr) #x0a0002))
                                  #x02
                                  ipv4.diffserv)))
      (ite (and (= ipv4.srcAddr #x00000000) (= ipv4.dstAddr #x0a00010a)) #x01 a!1))`;

    const rows = buildFieldUpdateRows({
      'ipv4.diffserv': expr,
    });

    expect(rows).toHaveLength(3);
    expect(rows[0].label).toContain('hdr.ipv4.srcAddr == 0.0.0.0');
    expect(rows[0].label).toContain('hdr.ipv4.dstAddr == 10.0.1.10');
    expect(rows[1].label).toContain('hdr.ipv4.dstAddr in 10.0.2.0/24');
    expect(rows[1].cells[0]).toBe('2');
    expect(rows[2].label).toBe('else');
    expect(rows[2].cells[0]).toBe('none');
  });

  it('aligns row cells across fields and keeps unchanged fallback as none', () => {
    const rows = buildFieldUpdateRows({
      'standard_metadata.egress_spec': nestedIte(
        [
          '(= ipv4.dstAddr #x0a00010a)',
          '(= ((_ extract 31 8) ipv4.dstAddr) #x0a0002)',
        ],
        ['#b000000001', '#b000000010'],
        'standard_metadata.egress_spec'
      ),
      'ipv4.ttl': '(ite (= ipv4.dstAddr #x0a00010a) (bvadd #xff ipv4.ttl) ipv4.ttl)',
    });

    expect(rows).toHaveLength(3);
    expect(rows[0].cells[0]).toBe('port 1');
    expect(rows[1].cells[0]).toBe('port 2');
    expect(rows[2].cells[0]).toBe('none');
    expect(rows[0].cells[1]).toBe('hdr.ipv4.ttl - 1');
    expect(rows[1].cells[1]).toBe('none');
    expect(rows[2].cells[1]).toBe('none');
  });

  it('propagates inherited reach conditions into each row payload', () => {
    const rows = buildFieldUpdateRows(
      {
        'scalars.metadata.routing_class': '(ite (= ipv4.dstAddr #x0a00010a) #x01 #x00)',
      },
      ['hdr.ipv4.isValid() is true', 'Packet is not dropped (egress_spec != DROP)']
    );

    expect(rows).toHaveLength(2);
    expect(rows[0].stackedReachCompact).toBe('2 cond.');
    expect(rows[0].stackedReachLines).toEqual([
      'Inherited reach conditions:',
      '- hdr.ipv4.isValid() is true',
      '- Packet is not dropped (egress_spec != DROP)',
    ]);
  });

  it('covers condition-shape combinations produced by nested z3 ite chains', () => {
    const conditionShapes = [
      '(= ipv4.dstAddr #x0a00010a)',
      '(= ((_ extract 31 8) ipv4.dstAddr) #x0a0002)',
      '(and (= ipv4.srcAddr #x00000000) (= ipv4.dstAddr #x0a00010a))',
      '(and (= ipv4.srcAddr #x00000000) (= ((_ extract 31 8) ipv4.dstAddr) #x0a0002))',
    ];

    for (let i = 0; i < conditionShapes.length; i++) {
      for (let j = 0; j < conditionShapes.length; j++) {
        const rows = buildFieldUpdateRows({
          'scalars.metadata.routing_class': nestedIte(
            [conditionShapes[i], conditionShapes[j]],
            ['#x01', '#x02'],
            '#x00'
          ),
        });

        expect(rows).toHaveLength(3);
        expect(rows[0].label).not.toContain('NOT (');
        expect(rows[1].label).toMatch(/else if|hdr\./);
        expect(rows[2].label).toBe('else');
      }
    }
  });
});
