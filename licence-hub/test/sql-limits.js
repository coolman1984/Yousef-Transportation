/** Strip single-quoted SQL literals so UNION tokens inside strings are ignored. */
function stripSqlStrings(sql) {
  return sql.replace(/'(?:''|[^'])*'/g, "''");
}

/**
 * Count compound SELECT terms (UNION / UNION ALL at depth 0) in a fragment.
 * SQLite applies SQLITE_LIMIT_COMPOUND_SELECT per compound SELECT, including CTE bodies.
 */
export function compoundSelectTerms(fragment) {
  const text = stripSqlStrings(fragment);
  let depth = 0;
  let terms = 1;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === '(') {
      depth += 1;
      continue;
    }
    if (ch === ')') {
      depth = Math.max(0, depth - 1);
      continue;
    }
    if (depth !== 0) continue;
    if (text[i] === 'U' || text[i] === 'u') {
      const rest = text.slice(i).toUpperCase();
      if (rest.startsWith('UNION ALL')) {
        terms += 1;
        i += 'UNION ALL'.length - 1;
        continue;
      }
      if (rest.startsWith('UNION')) {
        terms += 1;
        i += 'UNION'.length - 1;
      }
    }
  }
  return terms;
}

/** Extract parenthesized bodies after `name AS (` in a WITH clause (best-effort lexer). */
function extractCteBodies(sql) {
  const bodies = [];
  const text = stripSqlStrings(sql);
  const withIdx = text.search(/\bWITH\b/i);
  if (withIdx < 0) return bodies;
  let i = withIdx;
  while (i < text.length) {
    const asMatch = text.slice(i).search(/\bAS\s*\(/i);
    if (asMatch < 0) break;
    i += asMatch;
    const open = text.indexOf('(', i);
    if (open < 0) break;
    let depth = 0;
    let start = open + 1;
    for (let j = open; j < text.length; j++) {
      if (text[j] === '(') depth += 1;
      else if (text[j] === ')') {
        depth -= 1;
        if (depth === 0) {
          bodies.push(text.slice(start, j));
          i = j + 1;
          break;
        }
      }
    }
    if (depth !== 0) break;
  }
  return bodies;
}

/** Maximum compound SELECT term count in any CTE body or the main query tail. */
export function maxCompoundSelectTerms(sql) {
  const text = stripSqlStrings(sql);
  let max = 1;
  for (const body of extractCteBodies(sql)) {
    max = Math.max(max, compoundSelectTerms(body));
  }
  const withIdx = text.search(/\bWITH\b/i);
  let tail = withIdx >= 0 ? text.slice(withIdx) : text;
  const closeIdx = tail.lastIndexOf(')');
  if (withIdx >= 0 && closeIdx >= 0) {
    tail = tail.slice(closeIdx + 1);
  }
  max = Math.max(max, compoundSelectTerms(tail));
  return max;
}

export function assertD1CompoundSelectCap(sql, cap = 5) {
  const n = maxCompoundSelectTerms(sql);
  if (n > cap) {
    throw new Error(`compound_select_terms:${n}>${cap}`);
  }
}
