
function prettyField(f) { return 'hdr.' + f; }
function prettyFieldValue(val, f) { return val; }

function splitSexpr(s) {
  const tokens = [];
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
    } else if (/\s/.test(c)) {
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

function parseIte(smt, resultField = '') {
  const branches = [];
  let s = smt.trim();

  const processIte = (expr) => {
    expr = expr.trim();
    if (!expr.startsWith('(ite ') || !expr.endsWith(')')) {
      branches.push({ condition: 'Always', result: expr });
      return;
    }
    
    const inner = expr.substring(4, expr.length - 1).trim();
    const tokens = splitSexpr(inner);
    
    if (tokens.length >= 3) {
      const cond = tokens[0];
      const res = tokens[1];
      const fls = tokens.slice(2).join(' ');

      let prettyCond = cond;
      const eqMatch = cond.match(/^\(=\s+([a-zA-Z0-9_.$]+)\s+([^\s()]+)\)$/);
      if (eqMatch) {
         prettyCond = prettyField(eqMatch[1]) + ' == ' + eqMatch[2];
      }
      branches.push({ condition: prettyCond, result: res });

      if (fls.startsWith('(ite')) {
        processIte(fls);
      } else if (fls.trim() !== resultField && fls.trim() !== '') {
        branches.push({ condition: 'else', result: fls });
      }
    } else {
       branches.push({ condition: 'Always', result: expr });
    }
  };

  processIte(s);
  return branches.length > 0 ? branches : null;
}

const smt1 = `(ite (= ipv4.dstAddr #x0a000001)\n     #b000000001\n     (ite (= ipv4.dstAddr #x0a000002)\n          #b000000010\n          (ite (= ipv4.dstAddr #x0a000003) #b000000011 #b111111111)))`;

console.log(parseIte(smt1, 'foo'));
