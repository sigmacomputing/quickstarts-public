// ../wt-mcp-adddate/build/sigma-ids.js
var NS_MODULUS = 62 ** 4;
var SIGMA_LOWERCASE_WORDS = /* @__PURE__ */ new Set([
  "a",
  "an",
  "the",
  "and",
  "but",
  "or",
  "for",
  "nor",
  "so",
  "yet",
  "at",
  "by",
  "in",
  "of",
  "on",
  "to",
  "up",
  "as",
  "into",
  "via",
  "per"
]);
function sigmaDisplayName(s) {
  const normalized = (s || "").replace(/([a-z])([A-Z])/g, "$1_$2").replace(/([A-Z]+)([A-Z][a-z])/g, "$1_$2").replace(/([A-Za-z])([0-9])/g, "$1_$2").replace(/([0-9])([A-Za-z])/g, "$1_$2");
  const words = normalized.toLowerCase().split(/[_\s/-]+/).filter(Boolean);
  return words.map((w, i) => i === 0 || !SIGMA_LOWERCASE_WORDS.has(w) ? w.charAt(0).toUpperCase() + w.slice(1) : w).join(" ");
}
var DATA_MODEL_SCHEMA_SUMMARY = `
Sigma Data Model JSON top-level structure:
{
  "name": "Model Name",
  "pages": [{ "id": "pageId", "name": "Page 1", "elements": [...] }]
}

Element types: warehouse-table, custom-sql (kind:"sql"), join, union, control.
Columns: { "id": "inode-xxx/COL", "formula": "[TABLE/Display Name]" }
Calculated columns: { "id": "shortId", "formula": "[Price] - [Cost]", "name": "Profit" }
Metrics: { "id": "shortId", "formula": "Sum([Revenue])", "name": "Total Revenue" }
Relationships: { "id": "shortId", "targetElementId": "...", "keys": [{ "sourceColumnId": "...", "targetColumnId": "..." }] }

Cross-element Reference (accessing related dimension columns via relationships):
  [SOURCE_TABLE/REL_NAME/Column Display Name]
  REL_NAME is the relationship's "name" field (= target table name uppercase by convention).
  Example: DateDiff("day", [ORDER_FACT/PROMO_DIM/Start Date], [ORDER_FACT/PROMO_DIM/End Date])
  \u26A0 The dash-link form [SRC/FK_COL - link/Field] does NOT work via the API \u2014 use REL_NAME.

Conditional Aggregate Syntax:
  CountIf(condition) \u2014 condition only, NO field argument
  SumIf(field, condition) \u2014 FIELD FIRST, condition second
  AvgIf/MaxIf/MinIf/CountDistinctIf \u2014 all FIELD FIRST
  For booleans: always use [Column] = True, never bare [Column]

Groupings (for LOD / different aggregation levels):
  "groupings": [{ "id": "gId", "groupBy": ["colId1"], "calculations": ["calcId1"] }]
  Array order = nesting hierarchy. Use child elements for LOD patterns.
`.trim();

// ../wt-mcp-adddate/build/formulas.js
function decodeXmlEntities(s) {
  if (!s || s.indexOf("&") === -1)
    return s;
  return s.replace(/&#x([0-9a-fA-F]+);/g, (_m, h) => String.fromCodePoint(parseInt(h, 16))).replace(/&#(\d+);/g, (_m, d) => String.fromCodePoint(parseInt(d, 10))).replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
}
function stripLineComments(s) {
  if (!s || s.indexOf("//") === -1)
    return s;
  let out = "", inS = false, inD = false;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (inS) {
      out += c;
      if (c === "'")
        inS = false;
      continue;
    }
    if (inD) {
      out += c;
      if (c === '"')
        inD = false;
      continue;
    }
    if (c === "'") {
      inS = true;
      out += c;
      continue;
    }
    if (c === '"') {
      inD = true;
      out += c;
      continue;
    }
    if (c === "/" && s[i + 1] === "/") {
      while (i < s.length && s[i] !== "\n")
        i++;
      if (i < s.length)
        out += "\n";
      continue;
    }
    out += c;
  }
  return out;
}
function tableauInToSigma(formula) {
  const re = /(\[[^\]]+\]|[A-Za-z_][\w]*)\s+(not\s+)?in\s*\(/gi;
  let f = formula, guard = 0;
  for (let m = re.exec(f); m && guard < 200; m = re.exec(f), guard++) {
    const operand = m[1];
    const isNot = !!m[2];
    const open = m.index + m[0].length - 1;
    let depth = 0, close = -1;
    for (let i = open; i < f.length; i++) {
      if (f[i] === "(")
        depth++;
      else if (f[i] === ")") {
        depth--;
        if (depth === 0) {
          close = i;
          break;
        }
      }
    }
    if (close === -1)
      break;
    const inner = f.slice(open + 1, close);
    const parts = [];
    let buf = "", d = 0, sq = false, dq = false;
    for (const ch of inner) {
      if (sq) {
        buf += ch;
        if (ch === "'")
          sq = false;
        continue;
      }
      if (dq) {
        buf += ch;
        if (ch === '"')
          dq = false;
        continue;
      }
      if (ch === "'") {
        sq = true;
        buf += ch;
        continue;
      }
      if (ch === '"') {
        dq = true;
        buf += ch;
        continue;
      }
      if (ch === "(") {
        d++;
        buf += ch;
        continue;
      }
      if (ch === ")") {
        d--;
        buf += ch;
        continue;
      }
      if (ch === "," && d === 0) {
        parts.push(buf.trim());
        buf = "";
        continue;
      }
      buf += ch;
    }
    if (buf.trim())
      parts.push(buf.trim());
    if (!parts.length)
      continue;
    const op = isNot ? "<>" : "=";
    const join = isNot ? " and " : " or ";
    const chain = "(" + parts.map((p) => `${operand} ${op} ${p}`).join(join) + ")";
    f = f.slice(0, m.index) + chain + f.slice(close + 1);
    re.lastIndex = m.index + chain.length;
  }
  return f;
}
var _TEXT_FN_RE = /(?:Coalesce|Concat|Text|Left|Right|Mid|Substring|Substr|Upper|Lower|Trim|Replace|MonthName|WeekdayName|DateName|Proper)$/i;
function stripOuterParens(s) {
  s = s.trim();
  while (s.length > 1 && s.startsWith("(") && s.endsWith(")")) {
    let depth = 0, quote = "", inBracket = false, wraps = true;
    for (let i = 0; i < s.length; i++) {
      const c = s[i];
      if (inBracket) {
        if (c === "]")
          inBracket = false;
        continue;
      }
      if (quote) {
        if (c === quote)
          quote = "";
        continue;
      }
      if (c === "[") {
        inBracket = true;
        continue;
      }
      if (c === "'" || c === '"') {
        quote = c;
        continue;
      }
      if (c === "(")
        depth++;
      else if (c === ")") {
        depth--;
        if (depth === 0 && i < s.length - 1) {
          wraps = false;
          break;
        }
      }
    }
    if (!wraps || depth !== 0)
      break;
    s = s.slice(1, -1).trim();
  }
  return s;
}
function _isTextOperand(op, isTextRef) {
  let s = stripOuterParens(op.trim());
  if (!s)
    return false;
  if (/^"(?:[^"\\]|\\.)*"$/.test(s) || /^'(?:[^'\\]|\\.)*'$/.test(s))
    return true;
  const ref = s.match(/^\[([^\]\/]+)\]$/);
  if (ref)
    return isTextRef ? isTextRef(ref[1]) : false;
  const fn = s.match(/^([A-Za-z_]+)\s*\(.*\)$/s);
  if (fn && _TEXT_FN_RE.test(fn[1]))
    return true;
  return false;
}
function tableauTextConcatToSigma(formula, isTextRef) {
  if (!formula || formula.indexOf("+") === -1)
    return formula;
  const grab = (s, i, dir) => {
    let j = i;
    while (j >= 0 && j < s.length && /\s/.test(s[j]))
      j += dir;
    if (j < 0 || j >= s.length)
      return "";
    const close = dir < 0 ? s[j] : "";
    if (dir < 0 && (close === ")" || close === "]")) {
      const open = close === ")" ? "(" : "[", cl = close;
      let depth = 0, k2 = j;
      for (; k2 >= 0; k2--) {
        if (s[k2] === cl)
          depth++;
        else if (s[k2] === open) {
          depth--;
          if (depth === 0)
            break;
        }
      }
      let f2 = k2;
      while (f2 - 1 >= 0 && /[A-Za-z0-9_]/.test(s[f2 - 1]))
        f2--;
      return s.slice(f2, j + 1);
    }
    if (dir > 0 && (s[j] === "(" || s[j] === "[")) {
      const open = s[j], cl = open === "(" ? ")" : "]";
      let depth = 0, k2 = j;
      for (; k2 < s.length; k2++) {
        if (s[k2] === open)
          depth++;
        else if (s[k2] === cl) {
          depth--;
          if (depth === 0)
            break;
        }
      }
      return s.slice(j, k2 + 1);
    }
    if (s[j] === '"' || s[j] === "'") {
      const q = s[j];
      let k2 = j + dir;
      while (k2 >= 0 && k2 < s.length && s[k2] !== q)
        k2 += dir;
      return dir < 0 ? s.slice(k2, j + 1) : s.slice(j, k2 + 1);
    }
    let k = j;
    while (k >= 0 && k < s.length && /[A-Za-z0-9_.]/.test(s[k]))
      k += dir;
    return dir < 0 ? s.slice(k + 1, j + 1) : s.slice(j, k);
  };
  let f = formula, changed = true, guard = 0;
  while (changed && guard++ < 500) {
    changed = false;
    for (let i = 0; i < f.length; i++) {
      if (f[i] !== "+")
        continue;
      const left = grab(f, i - 1, -1), right = grab(f, i + 1, 1);
      if (_isTextOperand(left, isTextRef) || _isTextOperand(right, isTextRef)) {
        f = f.slice(0, i) + "&" + f.slice(i + 1);
        changed = true;
        break;
      }
    }
  }
  return f;
}
function tableauParamSwitchToSigma(formula, controlId, warnings) {
  const f = decodeXmlEntities(stripLineComments(formula)).trim();
  const head = f.match(/^case\s+\[Parameters?\]\s*\.\s*\[([^\]]+)\]\s+([\s\S]*?)\s*end\s*$/i);
  if (!head)
    return null;
  const paramName = head[1];
  const { masked: body, lits } = _maskTableauLiterals(head[2]);
  const cases = [];
  const pairRe = new RegExp(`\\bwhen\\s+${_TABLEAU_SENTINEL_SRC}\\s+then\\s+([\\s\\S]*?)(?=\\s*\\bwhen\\b|\\s*\\belse\\b|$)`, "gi");
  let m;
  while (m = pairRe.exec(body)) {
    const whenVal = _tabLitInner(lits, m[1]);
    const thenRaw = _restoreRawTableauLiterals(m[2], lits).trim();
    const thenSig = tableauFormulaToSigma(thenRaw, warnings);
    cases.push({ when: whenVal, then: thenSig });
  }
  if (!cases.length)
    return null;
  const elseM = body.match(/\belse\s+([\s\S]*?)$/i);
  const elseExpr = elseM ? tableauFormulaToSigma(_restoreRawTableauLiterals(elseM[1], lits).trim(), warnings) : null;
  const parts = cases.map((c) => `"${c.when}", ${c.then}`).join(", ");
  const switchFormula = `Switch([${controlId}], ${parts}${elseExpr ? `, ${elseExpr}` : ""})`;
  return { paramName, controlId, cases, elseExpr, switchFormula };
}
function lookColRef(identifier) {
  return `[${sigmaDisplayName(identifier)}]`;
}
var UNSUPPORTED_SIGMA_SQL = [
  { pattern: /\bFLATTEN\s*\(/i, name: "FLATTEN" },
  { pattern: /\bLATERAL\b/i, name: "LATERAL" },
  { pattern: /\bQUALIFY\b/i, name: "QUALIFY" },
  { pattern: /\bPIVOT\s*\(/i, name: "PIVOT" },
  { pattern: /\bUNPIVOT\s*\(/i, name: "UNPIVOT" },
  { pattern: /\bGENERATOR\s*\(/i, name: "GENERATOR" },
  { pattern: /\bTABLESAMPLE\b/i, name: "TABLESAMPLE" },
  { pattern: /\bOBJECT_CONSTRUCT\s*\(/i, name: "OBJECT_CONSTRUCT" },
  { pattern: /\bARRAY_CONSTRUCT\s*\(/i, name: "ARRAY_CONSTRUCT" }
];
function detectUnsupportedSigmaFunction(formula) {
  for (const { pattern, name } of UNSUPPORTED_SIGMA_SQL) {
    if (pattern.test(formula))
      return name;
  }
  return null;
}
function lookIsComplexSql(sql) {
  if (!sql)
    return false;
  const cleaned = sql.replace(/\$\{TABLE\}\./gi, "").replace(/\$\{[^}]+\}/g, "X").trim();
  if (/^(?:CAST|SAFE_CAST|TRY_CAST)\s*\(\s*"?[A-Za-z_][A-Za-z0-9_]*"?\s+AS\s+\w[\w_]*\s*\)$/i.test(cleaned))
    return false;
  if (/^[A-Za-z_][A-Za-z0-9_]*\s*\(/.test(cleaned))
    return true;
  if (/^CASE\b/i.test(cleaned))
    return true;
  if (/\bIN\s*\(/i.test(cleaned))
    return true;
  if (cleaned.includes("||"))
    return true;
  if (/[=<>!+\-*\/%]/.test(cleaned.replace(/'[^']*'/g, "")))
    return true;
  return false;
}
function _splitTopLevelArgs(s) {
  const args = [];
  let depth = 0, quote = "", bracket = false, cur = "";
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (quote) {
      cur += c;
      if (c === quote)
        quote = "";
      continue;
    }
    if (c === "[") {
      bracket = true;
      cur += c;
      continue;
    }
    if (c === "]") {
      bracket = false;
      cur += c;
      continue;
    }
    if (!bracket) {
      if (c === "'" || c === '"') {
        quote = c;
        cur += c;
        continue;
      }
      if (c === "(")
        depth++;
      else if (c === ")")
        depth--;
      else if (c === "," && depth === 0) {
        args.push(cur);
        cur = "";
        continue;
      }
    }
    cur += c;
  }
  args.push(cur);
  return args;
}
var _MYSQL_DIFF_UNIT = { DATEDIFF: "day", TIMEDIFF: "second" };
function _rewriteMysqlDateDiff(expr) {
  const NAME = /\b(DATEDIFF|TIMEDIFF)\s*\(/i;
  let out = "", rest = expr;
  for (; ; ) {
    const m = NAME.exec(rest);
    if (!m) {
      out += rest;
      break;
    }
    const open = m.index + m[0].length - 1;
    let depth = 0, close = -1;
    for (let i = open; i < rest.length; i++) {
      if (rest[i] === "(")
        depth++;
      else if (rest[i] === ")") {
        depth--;
        if (depth === 0) {
          close = i;
          break;
        }
      }
    }
    if (close === -1) {
      out += rest;
      break;
    }
    const inner = rest.slice(open + 1, close);
    const args = _splitTopLevelArgs(inner);
    out += rest.slice(0, m.index);
    if (args.length === 2) {
      const unit = _MYSQL_DIFF_UNIT[m[1].toUpperCase()];
      const end = _rewriteMysqlDateDiff(args[0]).trim();
      const start = _rewriteMysqlDateDiff(args[1]).trim();
      out += `DateDiff("${unit}", ${start}, ${end})`;
    } else {
      out += `${rest.slice(m.index, open + 1)}${_rewriteMysqlDateDiff(inner)})`;
    }
    rest = rest.slice(close + 1);
  }
  return out;
}
var _MYSQL_ADD_SPEC = {
  ADDDATE: { unit: "day", negate: false },
  SUBDATE: { unit: "day", negate: true },
  DATE_ADD: { unit: "day", negate: false },
  DATE_SUB: { unit: "day", negate: true }
};
var _MYSQL_INTERVAL_UNIT = {
  SECOND: "second",
  MINUTE: "minute",
  HOUR: "hour",
  DAY: "day",
  WEEK: "week",
  MONTH: "month",
  QUARTER: "quarter",
  YEAR: "year"
};
function _negateAmount(amount) {
  const t = amount.trim();
  const num = t.match(/^([+-]?)(\d+(?:\.\d+)?)$/);
  if (num)
    return num[1] === "-" ? num[2] : `-${num[2]}`;
  return `-(${t})`;
}
function _rewriteMysqlDateAdd(expr) {
  const NAME = /\b(ADDDATE|SUBDATE|DATE_ADD|DATE_SUB)\s*\(/i;
  let out = "", rest = expr;
  for (; ; ) {
    const m = NAME.exec(rest);
    if (!m) {
      out += rest;
      break;
    }
    const open = m.index + m[0].length - 1;
    let depth = 0, close = -1;
    for (let i = open; i < rest.length; i++) {
      if (rest[i] === "(")
        depth++;
      else if (rest[i] === ")") {
        depth--;
        if (depth === 0) {
          close = i;
          break;
        }
      }
    }
    if (close === -1) {
      out += rest;
      break;
    }
    const inner = rest.slice(open + 1, close);
    const args = _splitTopLevelArgs(inner);
    out += rest.slice(0, m.index);
    const spec = _MYSQL_ADD_SPEC[m[1].toUpperCase()];
    let unit = spec.unit;
    let amount = null;
    if (args.length === 2) {
      const iv = args[1].trim().match(/^INTERVAL\s+(.+?)\s+([A-Za-z_]+)\s*$/i);
      if (iv) {
        const mapped = _MYSQL_INTERVAL_UNIT[iv[2].toUpperCase()];
        if (mapped) {
          unit = mapped;
          amount = _rewriteMysqlDateAdd(iv[1]).trim();
        }
      } else {
        amount = _rewriteMysqlDateAdd(args[1]).trim();
      }
    }
    if (amount !== null) {
      const date = _rewriteMysqlDateAdd(args[0]).trim();
      out += `DateAdd("${unit}", ${spec.negate ? _negateAmount(amount) : amount}, ${date})`;
    } else {
      out += `${rest.slice(m.index, open + 1)}${_rewriteMysqlDateAdd(inner)})`;
    }
    rest = rest.slice(close + 1);
  }
  return out;
}
var LOOK_FUNC_MAP = {
  "MONTH": "Month",
  "YEAR": "Year",
  "DAY": "Day",
  "HOUR": "Hour",
  "MINUTE": "Minute",
  "SECOND": "Second",
  "QUARTER": "Quarter",
  "WEEK": "WeekOfYear",
  "WEEKDAY": "Weekday",
  "DATE_TRUNC": "DateTrunc",
  "DATEADD": "DateAdd",
  "DATEDIFF": "DateDiff",
  "COALESCE": "Coalesce",
  "NVL": "Coalesce",
  "NULLIF": "Nullif",
  "ROUND": "Round",
  "FLOOR": "Floor",
  "CEILING": "Ceiling",
  "ABS": "Abs",
  "UPPER": "Upper",
  "LOWER": "Lower",
  "TRIM": "Trim",
  "LENGTH": "Length",
  "SUBSTR": "Substring",
  "SUBSTRING": "Substring",
  "CONCAT": "Concat",
  "CURRENT_DATE": "Today()",
  "GETDATE": "Now()",
  "IFF": "If",
  "IIF": "If",
  "DECODE": "Switch",
  "ISNULL": "IsNull",
  "IFNULL": "Coalesce",
  "TO_DATE": "ToDate",
  "TO_NUMBER": "ToNumber",
  "TO_VARCHAR": "Text"
};
var _CASE_KW_RE = /^(CASE|WHEN|THEN|ELSE|END)\b/i;
function _scanCase(s, pos) {
  const markers = [];
  let caseDepth = 1, parenDepth = 0, i = pos;
  while (i < s.length) {
    const c = s[i];
    if (c === "[") {
      const close = s.indexOf("]", i + 1);
      i = close === -1 ? s.length : close + 1;
      continue;
    }
    if (c === "(") {
      parenDepth++;
      i++;
      continue;
    }
    if (c === ")") {
      parenDepth--;
      i++;
      continue;
    }
    if (/[A-Za-z]/.test(c) && (i === 0 || !/[A-Za-z0-9_]/.test(s[i - 1]))) {
      const m = _CASE_KW_RE.exec(s.slice(i));
      if (m) {
        const kw = m[1].toUpperCase(), start = i, end = i + m[1].length;
        if (kw === "CASE") {
          caseDepth++;
        } else if (kw === "END") {
          caseDepth--;
          if (caseDepth === 0)
            return { endStart: start, endIndex: end, markers };
        } else if (caseDepth === 1 && parenDepth === 0) {
          markers.push({ type: kw, start, end });
        }
        i = end;
        continue;
      }
    }
    i++;
  }
  return { endStart: -1, endIndex: -1, markers };
}
function _isBalanced(s) {
  let paren = 0, bracket = 0, inStr = false;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (inStr) {
      if (c === "\\") {
        i++;
        continue;
      }
      if (c === '"')
        inStr = false;
      continue;
    }
    if (c === '"') {
      inStr = true;
      continue;
    }
    if (c === "(")
      paren++;
    else if (c === ")") {
      paren--;
      if (paren < 0)
        return false;
    } else if (c === "[")
      bracket++;
    else if (c === "]") {
      bracket--;
      if (bracket < 0)
        return false;
    }
  }
  return paren === 0 && bracket === 0 && !inStr;
}
var _NESTED_CASE_UNMASK_RE = /(\d+)/g;
function _convertNestedCases(s, lits, onUnparseable = "abort", cdArgs = []) {
  const blocks = [];
  let out = "", last = 0, i = 0;
  while (i < s.length) {
    const c = s[i];
    if (c === "[") {
      const close = s.indexOf("]", i + 1);
      i = close === -1 ? s.length : close + 1;
      continue;
    }
    if (/[A-Za-z]/.test(c) && (i === 0 || !/[A-Za-z0-9_]/.test(s[i - 1])) && /^CASE\b/i.test(s.slice(i))) {
      const caseStart = i;
      const scan = _scanCase(s, i + 4);
      if (scan.endIndex === -1) {
        if (onUnparseable === "abort")
          return null;
        break;
      }
      const rawSpan = _restoreRawCountDistinct(_restoreRawLiterals(s.slice(caseStart, scan.endIndex), lits), cdArgs);
      const converted = lookConvertCase(rawSpan);
      if (converted === null) {
        if (onUnparseable === "abort")
          return null;
        i = scan.endIndex;
        continue;
      }
      out += s.slice(last, caseStart) + `${blocks.push(converted) - 1}`;
      last = scan.endIndex;
      i = scan.endIndex;
      continue;
    }
    i++;
  }
  return { text: out + s.slice(last), blocks };
}
function _spliceNestedCases(s, blocks) {
  return s.replace(_NESTED_CASE_UNMASK_RE, (_m, i) => blocks[Number(i)] ?? _m);
}
function lookConvertCase(expr) {
  const trimmed = expr.trim();
  const head = /^CASE\b/i.exec(trimmed);
  if (!head)
    return null;
  const { masked, lits } = _maskLiterals(trimmed);
  const scan = _scanCase(masked, head[0].length);
  if (scan.endIndex === -1)
    return null;
  if (masked.slice(scan.endIndex).trim() !== "")
    return null;
  const m = scan.markers;
  const firstMarkerStart = m.length ? m[0].start : scan.endStart;
  if (masked.slice(head[0].length, firstMarkerStart).trim() !== "")
    return null;
  const branches = [];
  let elseVal = null;
  let idx = 0;
  while (true) {
    if (idx >= m.length || m[idx].type !== "WHEN")
      return null;
    const whenTok = m[idx++];
    if (idx >= m.length || m[idx].type !== "THEN")
      return null;
    const thenTok = m[idx++];
    const condText = masked.slice(whenTok.end, thenTok.start);
    let valEnd, sawElse = false;
    if (idx < m.length && m[idx].type === "WHEN") {
      valEnd = m[idx].start;
    } else if (idx < m.length && m[idx].type === "ELSE") {
      valEnd = m[idx].start;
      sawElse = true;
    } else if (idx === m.length) {
      valEnd = scan.endStart;
    } else {
      return null;
    }
    branches.push({ cond: condText, val: masked.slice(thenTok.end, valEnd) });
    if (sawElse) {
      const elseTok = m[idx++];
      if (idx !== m.length)
        return null;
      elseVal = masked.slice(elseTok.end, scan.endStart);
      break;
    }
    if (idx === m.length)
      break;
  }
  if (branches.length === 0)
    return null;
  const convertLeaf = (maskedChunk, allowNumber) => {
    const v = maskedChunk.trim();
    if (allowNumber && /^-?\d+(\.\d+)?$/.test(v))
      return v;
    const stripped = stripOuterParens(v);
    const nc = _convertNestedCases(stripped, lits);
    if (nc === null)
      return null;
    const raw = _restoreRawLiterals(nc.text, lits);
    const converted = lookConvertExpression(raw);
    const spliced = _spliceNestedCases(converted, nc.blocks);
    if (!spliced.trim())
      return null;
    return spliced;
  };
  let result = elseVal !== null ? convertLeaf(elseVal, true) : "null";
  if (result === null)
    return null;
  const conv = new Array(branches.length);
  for (let i = branches.length - 1; i >= 0; i--) {
    const sigmaCond = convertLeaf(branches[i].cond, false);
    const sigmaVal = convertLeaf(branches[i].val, true);
    if (sigmaCond === null || sigmaVal === null)
      return null;
    conv[i] = { cond: sigmaCond, val: sigmaVal };
  }
  const flat = _flattenToSwitch(conv, result);
  if (flat !== null)
    return _isBalanced(flat) ? flat : null;
  for (let i = conv.length - 1; i >= 0; i--) {
    result = `If(${conv[i].cond}, ${conv[i].val}, ${result})`;
  }
  if (!_isBalanced(result))
    return null;
  return result;
}
var _SWITCH_MIN_BRANCHES = 45;
var _SWITCH_LITERAL_RE = /^(?:"(?:[^"]|"")*"|-?\d+(?:\.\d+)?)$/;
function _flattenToSwitch(conv, elseVal) {
  if (conv.length < _SWITCH_MIN_BRANCHES)
    return null;
  let subject = null;
  const pairs = [];
  for (const { cond, val } of conv) {
    let subj = null;
    let matches = null;
    const eq = /^(.+?)\s*=\s*(.+)$/.exec(cond);
    if (eq && !/[<>!=]$/.test(eq[1].trim()) && _SWITCH_LITERAL_RE.test(eq[2].trim())) {
      subj = eq[1].trim();
      matches = [eq[2].trim()];
    } else {
      const inm = /^In\(([\s\S]*)\)$/i.exec(cond.trim());
      if (inm) {
        const args = _splitTopLevelArgs(inm[1]);
        if (args.length >= 2) {
          subj = args[0].trim();
          matches = args.slice(1).map((a) => a.trim());
        }
      }
    }
    if (subj === null || matches === null || matches.length === 0)
      return null;
    if (!matches.every((m) => _SWITCH_LITERAL_RE.test(m)))
      return null;
    if (subject === null)
      subject = subj;
    else if (subject !== subj)
      return null;
    for (const m of matches)
      pairs.push(`${m}, ${val}`);
  }
  if (subject === null)
    return null;
  return `Switch(${subject}, ${pairs.join(", ")}, ${elseVal})`;
}
function lookConvertMathExpr(expr) {
  expr = expr.replace(/NULLIF\s*\(([A-Z_][A-Z0-9_]*)\s*,\s*([^)]+)\)/gi, (_, col, val) => `If(${lookColRef(col)} = ${val.trim()}, null, ${lookColRef(col)})`);
  return lookConvertExpression(expr);
}
var _LIT_RE = /'(?:[^']|'')*'/g;
function _maskLiterals(s) {
  const lits = [];
  let out = "";
  let i = 0;
  while (i < s.length) {
    if (s[i] === "[") {
      const close = s.indexOf("]", i + 1);
      if (close !== -1) {
        out += s.slice(i, close + 1);
        i = close + 1;
        continue;
      }
    }
    if (s[i] === "'") {
      _LIT_RE.lastIndex = i;
      const m = _LIT_RE.exec(s);
      if (m && m.index === i) {
        out += `\0${lits.push(m[0]) - 1}`;
        i += m[0].length;
        continue;
      }
    }
    out += s[i];
    i++;
  }
  return { masked: out, lits };
}
function _unmaskLiterals(s, lits) {
  return s.replace(/\u0000(\d+)\u0001/g, (_m, i) => {
    const inner = lits[Number(i)].slice(1, -1).replace(/''/g, "'").replace(/"/g, '\\"');
    return `"${inner}"`;
  });
}
function _restoreRawLiterals(s, lits) {
  return s.replace(/\u0000(\d+)\u0001/g, (_m, i) => lits[Number(i)] ?? _m);
}
function _restoreRawCountDistinct(s, args) {
  return s.replace(/\x02(\d+)\x03/g, (_m, i) => `COUNT(DISTINCT ${args[Number(i)] ?? ""})`);
}
function _maskCountDistinct(s) {
  const args = [];
  const re = /\bCOUNT\s*\(\s*DISTINCT\s+/gi;
  let out = "", last = 0, m;
  while ((m = re.exec(s)) !== null) {
    const argStart = m.index + m[0].length;
    let depth = 1, quote = "", i = argStart;
    for (; i < s.length; i++) {
      const c = s[i];
      if (quote) {
        if (c === quote)
          quote = "";
        continue;
      }
      if (c === "'" || c === '"') {
        quote = c;
        continue;
      }
      if (c === "[") {
        const cl = s.indexOf("]", i + 1);
        if (cl !== -1) {
          i = cl;
          continue;
        }
      }
      if (c === "(")
        depth++;
      else if (c === ")") {
        depth--;
        if (depth === 0)
          break;
      }
    }
    if (depth !== 0)
      break;
    out += s.slice(last, m.index) + `${args.push(s.slice(argStart, i).trim()) - 1}`;
    last = i + 1;
    re.lastIndex = last;
  }
  return { masked: out + s.slice(last), args };
}
function hasResidualCaseKeyword(s) {
  const masked = s.replace(/"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|\[[^\]]*\]/g, " ");
  return /\b(?:CASE|WHEN|THEN|END)\b/i.test(masked);
}
function hasResidualInfixOperator(s) {
  const masked = s.replace(/"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|\[[^\]]*\]/g, " ");
  return /\b(?:LIKE|BETWEEN)\b/i.test(masked);
}
function _unmaskCountDistinct(s, args) {
  return s.replace(/(\d+)/g, (_m, i) => {
    const raw = stripOuterParens(args[Number(i)]);
    const viaRules = lookSqlToSigmaRules(raw);
    const converted = viaRules ?? lookConvertExpression(raw);
    if (viaRules === null && hasResidualCaseKeyword(converted)) {
      return `COUNT(DISTINCT ${raw})`;
    }
    return `CountDistinct(${converted})`;
  });
}
var _SQL_KEYWORD_RE = /^(?:AND|OR|NOT|IN|IS|NULL|CASE|WHEN|THEN|ELSE|END|BETWEEN|LIKE|AS|ON|BY|DISTINCT|TRUE|FALSE|OVER|GROUP|EXISTS)$/i;
function _naiveTitleCase(fn) {
  return fn.charAt(0).toUpperCase() + fn.slice(1).toLowerCase();
}
var _BRACKET_UNMASK_RE = /\x0E(\d+)\x0F/g;
function _bracketSpanFinalText(rawSpan) {
  const inner = rawSpan.slice(1, -1);
  if (/^[A-Z_][A-Z0-9_]*$/.test(inner) && !_SQL_KEYWORD_RE.test(inner)) {
    return lookColRef(inner);
  }
  return rawSpan;
}
function _maskBrackets(s) {
  const spans = [];
  let out = "", i = 0;
  while (i < s.length) {
    if (s[i] === "[") {
      const close = s.indexOf("]", i + 1);
      if (close !== -1) {
        const finalText = _bracketSpanFinalText(s.slice(i, close + 1));
        out += `${spans.push(finalText) - 1}`;
        i = close + 1;
        continue;
      }
    }
    out += s[i];
    i++;
  }
  return { masked: out, spans };
}
function _unmaskBrackets(s, spans) {
  return s.replace(_BRACKET_UNMASK_RE, (_m, i) => spans[Number(i)] ?? _m);
}
function lookConvertExpression(expr) {
  const cd = _maskCountDistinct(expr);
  const { masked, lits } = _maskLiterals(cd.masked);
  expr = masked;
  expr = _rewriteMysqlDateDiff(expr);
  expr = _rewriteMysqlDateAdd(expr);
  const ec = _convertNestedCases(expr, lits, "leave-raw", cd.args);
  expr = ec.text;
  expr = expr.replace(/\b([A-Z_][A-Z0-9_]*)\s*(?=\()/gi, (match, fn) => {
    const upper = fn.toUpperCase();
    if (_SQL_KEYWORD_RE.test(upper))
      return match;
    const mapped = LOOK_FUNC_MAP[upper];
    if (mapped)
      return mapped.endsWith("()") ? mapped.slice(0, -2) : mapped;
    return _naiveTitleCase(fn);
  });
  expr = expr.replace(/(\[[^\]]+\]|[\w\]\)]+(?:\([^)]*\))?)\s+IN\s*\(([^)]+)\)/gi, (_, lhs, list) => {
    return `In(${lhs}, ${list})`;
  });
  {
    const { masked: bracketMasked, spans } = _maskBrackets(expr);
    expr = bracketMasked.replace(/\b([A-Z_][A-Z0-9_]*)\b(?!\s*\()/g, (match) => {
      if (_SQL_KEYWORD_RE.test(match))
        return match;
      if (/^\d+$/.test(match))
        return match;
      return lookColRef(match);
    });
    expr = _unmaskBrackets(expr, spans);
  }
  expr = _spliceNestedCases(expr, ec.blocks);
  return _unmaskCountDistinct(_unmaskLiterals(expr, lits), cd.args).trim();
}
var _SUPPLEMENTAL_SIGMA_NAMES = [
  "Count",
  // resources.ts formula-syntax reference: "Count([Col])"
  "Rank",
  // qlik.test.ts: Rank(Sum([Sales Amount]), "desc")
  "Lag",
  // qlik.test.ts: Lag(Sum([Sales Amount]), 1)
  "Lead"
  // qlik.test.ts: Lead(Sum([Sales Amount]), 1)
];
var _sigmaPassthroughCache = null;
function _sigmaPassthrough() {
  if (_sigmaPassthroughCache)
    return _sigmaPassthroughCache;
  const names = /* @__PURE__ */ new Set();
  for (const raw of [...Object.values(LOOK_FUNC_MAP), ...Object.values(TABLEAU_FUNC_MAP), ..._SUPPLEMENTAL_SIGMA_NAMES]) {
    const stripped = raw.endsWith("()") ? raw.slice(0, -2) : raw;
    if (_naiveTitleCase(stripped) === stripped)
      names.add(stripped.toUpperCase());
  }
  _sigmaPassthroughCache = names;
  return names;
}
function lookUnknownFunctions(sql) {
  const { masked: rawMasked } = _maskLiterals(sql);
  const masked = _rewriteMysqlDateAdd(_rewriteMysqlDateDiff(rawMasked));
  const passthrough = _sigmaPassthrough();
  const seen = /* @__PURE__ */ new Set();
  for (const m of masked.matchAll(/\b([A-Za-z_][A-Za-z0-9_]*)\s*(?=\()/g)) {
    const upper = m[1].toUpperCase();
    if (_SQL_KEYWORD_RE.test(upper))
      continue;
    if (LOOK_FUNC_MAP[upper] || passthrough.has(upper))
      continue;
    seen.add(upper);
  }
  return [...seen];
}
function lookSqlToSigmaRules(sql) {
  let expr = sql.replace(/\$\{TABLE\}\./gi, "").replace(/\$\{[^.}]+\.([^}]+)\}/g, (_, f) => f.toUpperCase()).replace(/\$\{([A-Za-z_][A-Za-z0-9_]*)\}/g, (_, n) => n.toUpperCase()).replace(/[\r\n]+\s*/g, " ").trim();
  expr = stripOuterParens(expr);
  {
    const m = expr.match(/^([A-Z_][A-Z0-9_]*)\s*=\s*(\d+)$/i);
    if (m)
      return `${lookColRef(m[1])} = ${m[2]}`;
  }
  {
    const m = expr.match(/^([A-Z_][A-Z0-9_]*)\s+IN\s*\(([^)]+)\)$/i);
    if (m) {
      const col = lookColRef(m[1]);
      const vals = m[2].split(",").map((v) => {
        v = v.trim();
        if (/^'[^']*'$/.test(v))
          return `"${v.slice(1, -1)}"`;
        return v;
      });
      return `In(${col}, ${vals.join(", ")})`;
    }
  }
  {
    const m = expr.match(/^(\[[^\]]+\])\s*(>=|<=|!=|<>|>|<|=)\s*(-?\d+(?:\.\d+)?)$/i);
    if (m)
      return `${m[1]} ${m[2] === "<>" ? "!=" : m[2]} ${m[3]}`;
  }
  {
    const m = expr.match(/^(\[[^\]]+\])\s+IN\s*\(([^)]+)\)$/i);
    if (m) {
      const vals = m[2].split(",").map((v) => {
        v = v.trim();
        if (/^'[^']*'$/.test(v))
          return `"${v.slice(1, -1)}"`;
        return v;
      });
      return `In(${m[1]}, ${vals.join(", ")})`;
    }
  }
  if (/^ROUND\s*\(/i.test(expr)) {
    const inner = expr.replace(/^ROUND\s*\(/i, "").replace(/\)\s*$/, "");
    const lastComma = inner.lastIndexOf(",");
    if (lastComma >= 0) {
      const mathExpr = inner.slice(0, lastComma).trim();
      const decimals = inner.slice(lastComma + 1).trim();
      const converted = lookConvertMathExpr(mathExpr);
      return `Round(${converted}, ${decimals})`;
    }
  }
  {
    const m = expr.match(/^DATEDIFF\s*\(\s*'([^']+)'\s*,\s*([A-Z_][A-Z0-9_]*)\s*,\s*([A-Z_][A-Z0-9_]*)\s*\)$/i);
    if (m)
      return `DateDiff("${m[1]}", ${lookColRef(m[2])}, ${lookColRef(m[3])})`;
  }
  if (/^CASE\b/i.test(expr)) {
    return lookConvertCase(expr);
  }
  if (/^[A-Z_][A-Z0-9_]*\s*[+\-*\/]/.test(expr) || /NULLIF/i.test(expr)) {
    return lookConvertMathExpr(expr);
  }
  if (expr.includes("||")) {
    const parts = expr.split("||").map((p) => {
      p = p.trim();
      if (/^'[^']*'$/.test(p))
        return `"${p.slice(1, -1)}"`;
      if (/^\[[^\]]+\]$/.test(p))
        return `Text(${p})`;
      if (/^[A-Z_][A-Z0-9_]*$/i.test(p))
        return `Text(${lookColRef(p)})`;
      return null;
    });
    if (parts.length > 1 && parts.every((p) => p !== null))
      return `Concat(${parts.join(", ")})`;
  }
  return null;
}
var TABLEAU_FUNC_MAP = {
  "AVG": "Avg",
  "MAX": "Max",
  "MIN": "Min",
  "MEDIAN": "Median",
  "SUM": "Sum",
  "ABS": "Abs",
  "CEILING": "Ceiling",
  "FLOOR": "Floor",
  "ROUND": "Round",
  "SQRT": "Sqrt",
  "POWER": "Power",
  // scalar math (verified resolve in Sigma 2026-06-15; Tableau LOG default base 10 == Sigma Log default base 10)
  "LN": "Ln",
  "LOG": "Log",
  "EXP": "Exp",
  "MOD": "Mod",
  "SIGN": "Sign",
  "PI": "Pi",
  // trig + angle conversion — same names/arg-order in Sigma (live-verified 2026-07-10, bead tt3z.3)
  "SIN": "Sin",
  "COS": "Cos",
  "TAN": "Tan",
  "COT": "Cot",
  "ASIN": "Asin",
  "ACOS": "Acos",
  "ATAN": "Atan",
  "ATAN2": "Atan2",
  "DEGREES": "Degrees",
  "RADIANS": "Radians",
  // PROPER (title-case) — live-verified Sigma Proper() (bead tt3z.3)
  "PROPER": "Proper",
  "STR": "Text",
  "INT": "Int",
  "FLOAT": "Number",
  "LEN": "Len",
  "UPPER": "Upper",
  "LOWER": "Lower",
  "TRIM": "Trim",
  "LTRIM": "Ltrim",
  "RTRIM": "Rtrim",
  "LEFT": "Left",
  "RIGHT": "Right",
  "MID": "Mid",
  "REPLACE": "Replace",
  "CONTAINS": "Contains",
  "STARTSWITH": "StartsWith",
  "ENDSWITH": "EndsWith",
  "FIND": "Find",
  "TODAY": "Today",
  "NOW": "Now",
  "YEAR": "Year",
  "MONTH": "Month",
  "DAY": "Day",
  "HOUR": "Hour",
  "MINUTE": "Minute",
  "SECOND": "Second",
  // NOTE: no 'WEEK' entry — Sigma has no Week() function; WEEK(date) is rewritten
  // to DatePart("week", date) below (verified via docs + live query 2026-07-10).
  "QUARTER": "Quarter",
  "DATE": "Date",
  "DATETIME": "Datetime",
  "MAKEDATE": "MakeDate",
  // regex (same arg order as Tableau)
  "REGEXP_EXTRACT": "RegexpExtract",
  "REGEXP_REPLACE": "RegexpReplace",
  "REGEXP_MATCH": "RegexpMatch",
  // statistical aggregates (sample variants direct; STDEVP handled above)
  "STDEV": "StdDev",
  "VAR": "Variance",
  "VARP": "VariancePop",
  "PERCENTILE": "PercentileCont",
  "CORR": "Corr",
  // string split — both 1-indexed, negatives count from the right
  "SPLIT": "SplitPart"
};
var SIGMA_CHART_ONLY_WINDOW_RE = /\b(?:Cumulative(?:Sum|Avg|Min|Max|Count)|Moving(?:Sum|Avg|Min|Max|Count|StdDev)|RankDense|RankPercentile|Rank|PercentOfTotal|RowNumber|Lag|Lead)\s*\(/;
var TABLEAU_TABLE_CALC_TOKEN_RE = /\b(?:WINDOW_[A-Z]+|RUNNING_[A-Z]+|LOOKUP|PREVIOUS_VALUE|RANK(?:_[A-Z]+)?|INDEX|SIZE|TOTAL|FIRST|LAST)\s*\(/;
var TABLEAU_TABLE_CALC_TOKEN_CI_RE = /\b(?:WINDOW_[A-Za-z]+|RUNNING_[A-Za-z]+|PREVIOUS_VALUE)\s*\(/i;
var TABLEAU_LOD_LEFTOVER_RE = /\{\s*(?:FIXED|INCLUDE|EXCLUDE)\b/i;
function formulaHasUntranslatableFragment(f) {
  if (!f)
    return false;
  if (TABLEAU_LOD_LEFTOVER_RE.test(f) || TABLEAU_TABLE_CALC_TOKEN_RE.test(f) || TABLEAU_TABLE_CALC_TOKEN_CI_RE.test(f) || /\/\*\s*(?:LOD|table calc|no Sigma equivalent)/.test(f))
    return true;
  const masked = f.replace(/"[^"]*"|'[^']*'|\[[^\]]*\]/g, " ");
  return /\b(?:then|end|when)\b/i.test(masked);
}
var _TC_AGG_MAP = {
  SUM: "Sum",
  AVG: "Avg",
  MIN: "Min",
  MAX: "Max",
  COUNT: "Count",
  COUNTD: "CountDistinct",
  MEDIAN: "Median",
  STDEV: "StdDev",
  VAR: "Variance"
};
var _TC_COL = "(\\[[^\\]]+\\]|[A-Za-z_][A-Za-z0-9_]*)";
var _TC_AGG = "(SUM|AVG|MIN|MAX|COUNT|COUNTD|MEDIAN|STDEV|VAR)";
var _TC_AGG_EXPR = `${_TC_AGG}\\s*\\(\\s*${_TC_COL}\\s*\\)`;
function _tcCol(raw) {
  const name = raw.replace(/^\[|\]$/g, "");
  if (/^[A-Z][A-Z0-9_]{2,}$/.test(name))
    return "[" + sigmaDisplayName(name) + "]";
  return "[" + name + "]";
}
function _tcAgg(aggFunc, colRaw) {
  const fn = _TC_AGG_MAP[aggFunc.toUpperCase()] || "Sum";
  return `${fn}(${_tcCol(colRaw)})`;
}
function _tcSameRef(a, b) {
  const norm = (s) => s.replace(/^\[|\]$/g, "").replace(/[^A-Za-z0-9_]/g, "_").toUpperCase();
  return norm(a) === norm(b);
}
function tableauWindowUntranslatable(formula) {
  const m = (formula || "").match(/\b(WINDOW_MEDIAN|WINDOW_PERCENTILE|WINDOW_CORR|WINDOW_COVARP?|WINDOW_VARP?|WINDOW_STDEVP|PREVIOUS_VALUE|SIZE)\s*\(/i);
  return m ? m[1].toUpperCase() : null;
}
function tableauWindowToSigmaChart(formula) {
  const f = (formula || "").trim();
  if (!f || tableauWindowUntranslatable(f))
    return null;
  let m;
  m = f.match(new RegExp(`^${_TC_AGG_EXPR}\\s*\\/\\s*(?:TOTAL|WINDOW_SUM)\\s*\\(\\s*${_TC_AGG_EXPR}\\s*\\)$`, "i"));
  if (m && m[1].toUpperCase() === m[3].toUpperCase() && _tcSameRef(m[2], m[4])) {
    return { formula: `PercentOfTotal(${_tcAgg(m[1], m[2])}, "grand_total")`, kind: "percent-of-total" };
  }
  m = f.match(new RegExp(`^RUNNING_SUM\\s*\\(\\s*${_TC_AGG_EXPR}\\s*\\)\\s*\\/\\s*(?:TOTAL|WINDOW_SUM)\\s*\\(\\s*${_TC_AGG_EXPR}\\s*\\)$`, "i"));
  if (m && m[1].toUpperCase() === m[3].toUpperCase() && _tcSameRef(m[2], m[4])) {
    return { formula: `CumulativeSum(PercentOfTotal(${_tcAgg(m[1], m[2])}, "grand_total"))`, kind: "cumulative" };
  }
  m = f.match(new RegExp(`^RUNNING_(SUM|AVG|MIN|MAX|COUNT)\\s*\\(\\s*${_TC_AGG_EXPR}\\s*\\)$`, "i"));
  if (m) {
    const fn = "Cumulative" + m[1].charAt(0).toUpperCase() + m[1].slice(1).toLowerCase();
    return { formula: `${fn}(${_tcAgg(m[2], m[3])})`, kind: "cumulative" };
  }
  m = f.match(new RegExp(`^RUNNING_(SUM|AVG|MIN|MAX|COUNT)\\s*\\(\\s*${_TC_COL}\\s*\\)$`, "i"));
  if (m) {
    const fn = "Cumulative" + m[1].charAt(0).toUpperCase() + m[1].slice(1).toLowerCase();
    return { formula: `${fn}(${_tcAgg(m[1], m[2])})`, kind: "cumulative" };
  }
  m = f.match(new RegExp(`^WINDOW_(SUM|AVG|MIN|MAX|STDEV)\\s*\\(\\s*${_TC_AGG_EXPR}\\s*,\\s*(-?\\d+)\\s*,\\s*(-?\\d+)\\s*\\)$`, "i"));
  if (m) {
    const back = parseInt(m[4], 10);
    const fwd = parseInt(m[5], 10);
    if (back <= 0 && fwd >= 0) {
      const movMap = {
        SUM: "MovingSum",
        AVG: "MovingAvg",
        MIN: "MovingMin",
        MAX: "MovingMax",
        STDEV: "MovingStdDev"
      };
      const fn = movMap[m[1].toUpperCase()];
      const args = fwd === 0 ? `${-back}` : `${-back}, ${fwd}`;
      return { formula: `${fn}(${_tcAgg(m[2], m[3])}, ${args})`, kind: "moving" };
    }
    return null;
  }
  m = f.match(new RegExp(`^(RANK|RANK_DENSE|RANK_PERCENTILE|RANK_UNIQUE)\\s*\\(\\s*${_TC_AGG_EXPR}\\s*(?:,\\s*['"]?(asc|desc)['"]?\\s*)?\\)$`, "i"));
  if (m) {
    const fnMap = {
      RANK: "Rank",
      RANK_DENSE: "RankDense",
      RANK_PERCENTILE: "RankPercentile",
      RANK_UNIQUE: "Rank"
    };
    const fn = fnMap[m[1].toUpperCase()];
    const dir = (m[4] || "desc").toLowerCase();
    const unique = m[1].toUpperCase() === "RANK_UNIQUE";
    return {
      formula: `${fn}(${_tcAgg(m[2], m[3])}, "${dir}")`,
      kind: "rank",
      ...unique ? { verify: true, note: "RANK_UNIQUE breaks ties arbitrarily; Sigma Rank assigns equal ranks to ties \u2014 verify against Tableau." } : {}
    };
  }
  if (/^INDEX\s*\(\s*\)$/i.test(f))
    return { formula: "RowNumber()", kind: "index" };
  m = f.match(new RegExp(`^LOOKUP\\s*\\(\\s*${_TC_AGG_EXPR}\\s*,\\s*(-?\\d+)\\s*\\)$`, "i"));
  if (m) {
    const off = parseInt(m[3], 10);
    const agg = _tcAgg(m[1], m[2]);
    if (off === 0)
      return { formula: agg, kind: "lag", note: "LOOKUP(expr, 0) is the identity \u2014 no window function needed." };
    return off < 0 ? { formula: `Lag(${agg}, ${-off})`, kind: "lag" } : { formula: `Lead(${agg}, ${off})`, kind: "lead" };
  }
  return null;
}
var _TAB_BLOCK_KW_RE = /^(IF|CASE|ELSEIF|THEN|ELSE|WHEN|END)\b/i;
function _scanTableauBlock(s, pos) {
  const markers = [];
  let blockDepth = 1, i = pos;
  while (i < s.length) {
    const c = s[i];
    if (c === "[") {
      const close = s.indexOf("]", i + 1);
      i = close === -1 ? s.length : close + 1;
      continue;
    }
    if (/[A-Za-z]/.test(c) && (i === 0 || !/[A-Za-z0-9_]/.test(s[i - 1]))) {
      const m = _TAB_BLOCK_KW_RE.exec(s.slice(i));
      if (m) {
        const kw = m[1].toUpperCase(), start = i, end = i + m[1].length;
        if (kw === "IF" || kw === "CASE") {
          blockDepth++;
        } else if (kw === "END") {
          blockDepth--;
          if (blockDepth === 0)
            return { endStart: start, endIndex: end, markers };
        } else if (blockDepth === 1) {
          markers.push({ type: kw, start, end });
        }
        i = end;
        continue;
      }
    }
    i++;
  }
  return { endStart: -1, endIndex: -1, markers };
}
function _convertIfBody(inner, markers, innerOffset, lits) {
  const rel = markers.map((mk) => ({ type: mk.type, start: mk.start - innerOffset, end: mk.end - innerOffset }));
  const elseMarker = rel.find((mk) => mk.type === "ELSE");
  const chainEnd = elseMarker ? elseMarker.start : inner.length;
  const elseVal = elseMarker ? _tableauRecurse(inner.slice(elseMarker.end).trim(), lits) : "null";
  const chain = rel.filter((mk) => mk.type === "THEN" || mk.type === "ELSEIF");
  const clauses = [];
  let condStart = 0;
  for (let k = 0; k < chain.length; k += 2) {
    const thenMk = chain[k];
    if (!thenMk || thenMk.type !== "THEN")
      break;
    const cond = inner.slice(condStart, thenMk.start).trim();
    const nextMk = chain[k + 1];
    const valEnd = nextMk ? nextMk.start : chainEnd;
    const val = inner.slice(thenMk.end, valEnd).trim();
    clauses.push({ cond, val });
    condStart = nextMk ? nextMk.end : valEnd;
  }
  let result = elseVal;
  for (let k = clauses.length - 1; k >= 0; k--) {
    result = "If(" + _tableauRecurse(clauses[k].cond, lits) + ", " + _tableauRecurse(clauses[k].val, lits) + ", " + result + ")";
  }
  return result;
}
function _convertCaseBody(inner, markers, innerOffset, lits) {
  const rel = markers.map((mk) => ({ type: mk.type, start: mk.start - innerOffset, end: mk.end - innerOffset }));
  const elseMarker = rel.find((mk) => mk.type === "ELSE");
  const chainEnd = elseMarker ? elseMarker.start : inner.length;
  const elseVal = elseMarker ? _tableauRecurse(inner.slice(elseMarker.end).trim(), lits) : "null";
  const chain = rel.filter((mk) => mk.type === "WHEN" || mk.type === "THEN");
  const firstWhen = chain.find((mk) => mk.type === "WHEN");
  const field = firstWhen ? _tableauRecurse(inner.slice(0, firstWhen.start).trim(), lits) : "[?]";
  const clauses = [];
  for (let k = 0; k < chain.length; k += 2) {
    const whenMk = chain[k];
    const thenMk = chain[k + 1];
    if (!whenMk || whenMk.type !== "WHEN" || !thenMk || thenMk.type !== "THEN")
      break;
    const nextWhenMk = chain[k + 2];
    const cond = inner.slice(whenMk.end, thenMk.start).trim();
    const valEnd = nextWhenMk ? nextWhenMk.start : chainEnd;
    const val = inner.slice(thenMk.end, valEnd).trim();
    clauses.push({ cond, val });
  }
  let result = elseVal;
  for (let k = clauses.length - 1; k >= 0; k--) {
    result = "If(" + field + " = " + _tableauRecurse(clauses[k].cond, lits) + ", " + _tableauRecurse(clauses[k].val, lits) + ", " + result + ")";
  }
  return result;
}
function tableauControlToSigma(f, lits) {
  let out = "", last = 0, i = 0;
  while (i < f.length) {
    const c = f[i];
    if (c === "[") {
      const close = f.indexOf("]", i + 1);
      i = close === -1 ? f.length : close + 1;
      continue;
    }
    if (/[A-Za-z]/.test(c) && (i === 0 || !/[A-Za-z0-9_]/.test(f[i - 1]))) {
      const isIf = /^IF\b/i.test(f.slice(i));
      const isCase = !isIf && /^CASE\b/i.test(f.slice(i));
      if (isIf || isCase) {
        const blockStart = i;
        const bodyStart = i + (isIf ? 2 : 4);
        const scan = _scanTableauBlock(f, bodyStart);
        if (scan.endIndex === -1) {
          i++;
          continue;
        }
        const inner = f.slice(bodyStart, scan.endStart);
        const converted = isIf ? _convertIfBody(inner, scan.markers, bodyStart, lits) : _convertCaseBody(inner, scan.markers, bodyStart, lits);
        out += f.slice(last, blockStart) + converted;
        last = scan.endIndex;
        i = scan.endIndex;
        continue;
      }
    }
    i++;
  }
  return out + f.slice(last);
}
var _TABLEAU_LIT_SQ_RE = /'(?:[^'\\]|\\.)*'/g;
var _TABLEAU_LIT_DQ_RE = /"(?:[^"\\]|\\.)*"/g;
var _TABLEAU_SENTINEL_SRC = "\0(\\d+)";
var _TABLEAU_SENTINEL_RE = /\u0000(\d+)\u0001/g;
function _maskTableauLiterals(s, lits = []) {
  let out = "";
  let i = 0;
  while (i < s.length) {
    if (s[i] === "[") {
      const close = s.indexOf("]", i + 1);
      if (close !== -1) {
        out += s.slice(i, close + 1);
        i = close + 1;
        continue;
      }
    }
    if (s[i] === "'" || s[i] === '"') {
      const re = s[i] === "'" ? _TABLEAU_LIT_SQ_RE : _TABLEAU_LIT_DQ_RE;
      re.lastIndex = i;
      const m = re.exec(s);
      if (m && m.index === i) {
        out += `\0${lits.push(m[0]) - 1}`;
        i += m[0].length;
        continue;
      }
    }
    out += s[i];
    i++;
  }
  return { masked: out, lits };
}
function _restoreRawTableauLiterals(s, lits) {
  return s.replace(_TABLEAU_SENTINEL_RE, (_m, i) => lits[Number(i)] ?? _m);
}
function _tabLitInner(lits, idxStr) {
  const raw = lits[Number(idxStr)];
  return raw === void 0 ? "" : raw.slice(1, -1).replace(/\\(.)/g, "$1");
}
function _tabEscapeForSigma(inner) {
  return inner.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}
function _unmaskTableauLiterals(s, lits) {
  return s.replace(_TABLEAU_SENTINEL_RE, (_m, i) => `"${_tabEscapeForSigma(_tabLitInner(lits, i))}"`);
}
function _tableauRecurse(maskedSlice, lits) {
  const raw = _restoreRawTableauLiterals(maskedSlice, lits);
  const converted = tableauFormulaToSigma(raw);
  const { masked } = _maskTableauLiterals(converted, lits);
  return masked;
}
function tableauFormulaToSigma(formula, warnings) {
  if (!formula || !formula.trim())
    return "";
  const raw0 = stripLineComments(decodeXmlEntities(formula)).trim();
  const { masked, lits } = _maskTableauLiterals(raw0);
  let f = masked;
  if (/^\s*\{/.test(f)) {
    if (warnings)
      warnings.push("\u26A0 LOD expression not converted: " + raw0.slice(0, 60));
    return "/* LOD: " + raw0.replace(/\/\*/g, "").replace(/\*\//g, "") + " */";
  }
  {
    const winChart = tableauWindowToSigmaChart(raw0);
    if (winChart) {
      if (warnings)
        warnings.push(`\u2139 Table calc \u2192 ${winChart.formula} \u2014 CHART/grouped-element context ONLY: place in a grouped workbook element (group by the viz dimensions); window functions silently error in data-model calc columns and workbook master calc columns.` + (winChart.note ? " " + winChart.note : ""));
      return winChart.formula;
    }
    const untrans = tableauWindowUntranslatable(raw0);
    if (untrans) {
      if (warnings)
        warnings.push(`\u26A0 Table calculation NOT converted \u2014 ${untrans}() has no Sigma equivalent. Untranslated fragment: ${raw0.slice(0, 120)}`);
      return "/* table calc: " + raw0.replace(/\/\*/g, "").replace(/\*\//g, "") + " */";
    }
    if (/^(WINDOW_|RUNNING_|FIRST\(|LAST\(|INDEX\(|RANK\b|RANK_|LOOKUP\(|TOTAL\s*\()/i.test(raw0)) {
      const gt = raw0.match(/^WINDOW_SUM\s*\(\s*(SUM|COUNT|AVG|MIN|MAX)\s*\(\s*(\[[^\]]+\])\s*\)\s*\)$/i);
      if (gt) {
        const aggMap = { SUM: "Sum", COUNT: "Count", AVG: "Avg", MIN: "Min", MAX: "Max" };
        return "GrandTotal(" + (aggMap[gt[1].toUpperCase()] || gt[1]) + "(" + gt[2] + "))";
      }
      if (warnings)
        warnings.push(`\u26A0 Table calculation not converted. Untranslated fragment: ${raw0.slice(0, 120)}`);
      return "/* table calc: " + raw0.replace(/\/\*/g, "").replace(/\*\//g, "") + " */";
    }
  }
  if (/\bCOVARP?\s*\(/i.test(f)) {
    if (warnings)
      warnings.push(`\u26A0 COVAR/COVARP has no Sigma equivalent \u2014 not converted. Fragment: ${raw0.slice(0, 120)}`);
    return "/* no Sigma equivalent: " + raw0.replace(/\/\*/g, "").replace(/\*\//g, "") + " */";
  }
  f = f.replace(/\bZN\s*\(([^)]+)\)/gi, "Coalesce($1, 0)");
  f = f.replace(/\bIFNULL\s*\(/gi, "Coalesce(").replace(/\bIFERROR\s*\(/gi, "Coalesce(");
  f = f.replace(/\bISNULL\s*\(/gi, "IsNull(");
  f = f.replace(/\bCOUNT\s*\(([^)]+)\)/gi, (m, arg) => "CountIf(IsNotNull(" + arg.trim() + "))");
  f = f.replace(/\bCOUNTD\s*\(/gi, "CountDistinct(");
  f = f.replace(/\bATTR\s*\(([^)]+)\)/gi, "$1");
  f = tableauInToSigma(f);
  f = tableauControlToSigma(f, lits);
  f = f.replace(/\bIIF\s*\(/gi, "If(");
  f = f.replace(new RegExp(`\\bDATEPART\\s*\\(\\s*${_TABLEAU_SENTINEL_SRC}\\s*,\\s*([^)]+)\\)`, "gi"), (m, litIdx, dateArg) => {
    const part = _tabLitInner(lits, litIdx);
    if (!/^\w+$/.test(part))
      return m;
    if (part.toLowerCase() === "week")
      return 'DatePart("week", ' + dateArg.trim() + ")";
    const partMap = {
      year: "Year",
      month: "Month",
      day: "Day",
      hour: "Hour",
      minute: "Minute",
      second: "Second",
      quarter: "Quarter",
      dayofweek: "DayOfWeek",
      weekday: "DayOfWeek"
    };
    const fn = partMap[part.toLowerCase()];
    return fn ? fn + "(" + dateArg.trim() + ")" : m;
  });
  f = f.replace(new RegExp(`\\bDATENAME\\s*\\(\\s*${_TABLEAU_SENTINEL_SRC}\\s*,\\s*([^,)]+)(?:,[^)]*)?\\)`, "gi"), (m, litIdx, dateArg) => {
    const part = _tabLitInner(lits, litIdx);
    if (!/^\w+$/.test(part))
      return m;
    const arg = dateArg.trim();
    switch (part.toLowerCase()) {
      case "month":
        return "MonthName(" + arg + ")";
      case "weekday":
      case "dayofweek":
        return "WeekdayName(" + arg + ")";
      case "year":
        return "Text(Year(" + arg + "))";
      case "quarter":
        return "Text(Quarter(" + arg + "))";
      case "day":
        return "Text(Day(" + arg + "))";
      case "week":
        return "Text(Week(" + arg + "))";
      case "hour":
        return "Text(Hour(" + arg + "))";
      case "minute":
        return "Text(Minute(" + arg + "))";
      case "second":
        return "Text(Second(" + arg + "))";
      default:
        return m;
    }
  });
  f = f.replace(new RegExp(`\\bDATETRUNC\\s*\\(\\s*${_TABLEAU_SENTINEL_SRC}\\s*,`, "gi"), (_m, litIdx) => `DateTrunc("${_tabEscapeForSigma(_tabLitInner(lits, litIdx))}",`);
  f = f.replace(new RegExp(`,\\s*${_TABLEAU_SENTINEL_SRC}\\s*\\)`, "gi"), (m, litIdx) => {
    const val = _tabLitInner(lits, litIdx);
    return /^(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)$/i.test(val) ? ")" : m;
  });
  f = f.replace(new RegExp(`\\bDATEADD\\s*\\(\\s*${_TABLEAU_SENTINEL_SRC}\\s*,`, "gi"), (_m, litIdx) => `DateAdd("${_tabEscapeForSigma(_tabLitInner(lits, litIdx))}",`);
  f = f.replace(new RegExp(`\\bDATEDIFF\\s*\\(\\s*${_TABLEAU_SENTINEL_SRC}\\s*,`, "gi"), (_m, litIdx) => `DateDiff("${_tabEscapeForSigma(_tabLitInner(lits, litIdx))}",`);
  f = f.replace(/\bWEEK\s*\(\s*([^()]*(?:\([^()]*\)[^()]*)*)\)/gi, 'DatePart("week", $1)');
  f = f.replace(/\bSTDEVP\s*\(([^()]+(?:\([^()]*\)[^()]*)*)\)/gi, "Sqrt(VariancePop($1))");
  f = f.replace(new RegExp(`\\bDATEPARSE\\s*\\(\\s*${_TABLEAU_SENTINEL_SRC}\\s*,\\s*([^()]+(?:\\([^()]*\\)[^()]*)*)\\)`, "gi"), (_m, litIdx, str) => {
    const fmtRaw = _tabLitInner(lits, litIdx);
    const sf = fmtRaw.replace(/yyyy/g, "%Y").replace(/yy/g, "%y").replace(/MMMM/g, "%B").replace(/MMM/g, "%b").replace(/MM/g, "%m").replace(/dd/g, "%d").replace(/HH/g, "%H").replace(/hh/g, "%I").replace(/mm/g, "%M").replace(/ss/g, "%S");
    if (warnings)
      warnings.push("\u26A0 DATEPARSE format translated to strftime tokens \u2014 verify the pattern resolves on your warehouse.");
    return `DateParse(${str.trim()}, "${sf}")`;
  });
  f = f.replace(/\bUSERNAME\s*\(\s*\)/gi, "CurrentUserEmail()");
  f = f.replace(new RegExp(`\\bISMEMBEROF\\s*\\(\\s*${_TABLEAU_SENTINEL_SRC}\\s*\\)`, "gi"), (_m, litIdx) => `CurrentUserInTeam("${_tabEscapeForSigma(_tabLitInner(lits, litIdx))}")`);
  f = f.replace(new RegExp(`\\bUSERATTRIBUTE\\s*\\(\\s*${_TABLEAU_SENTINEL_SRC}\\s*\\)`, "gi"), (_m, litIdx) => `CurrentUserAttributeText("${_tabEscapeForSigma(_tabLitInner(lits, litIdx))}")`);
  f = f.replace(new RegExp(`\\bISUSERNAME\\s*\\(\\s*${_TABLEAU_SENTINEL_SRC}\\s*\\)`, "gi"), (_m, litIdx) => `(CurrentUserEmail() = "${_tabEscapeForSigma(_tabLitInner(lits, litIdx))}")`);
  f = f.replace(/\bSQUARE\s*\(\s*([^()]*(?:\([^()]*\)[^()]*)*)\)/gi, "Power($1, 2)");
  f = f.replace(/\bSPACE\s*\(\s*([^()]*(?:\([^()]*\)[^()]*)*)\)/gi, 'Repeat(" ", $1)');
  for (const [tab, sig] of Object.entries(TABLEAU_FUNC_MAP)) {
    f = f.replace(new RegExp("\\b" + tab + "\\s*\\(", "gi"), sig + "(");
  }
  f = f.replace(/\bNOT\b/g, "Not").replace(/\bAND\b/g, "and").replace(/\bOR\b/g, "or");
  f = f.replace(/\bTRUE\b/gi, "True").replace(/\bFALSE\b/gi, "False").replace(/\bNULL\b/gi, "null");
  f = f.replace(/\[([A-Z][A-Z0-9_]{2,})\]/g, (match, colName) => {
    if (colName === colName.toLowerCase() || colName.includes(" "))
      return match;
    return "[" + sigmaDisplayName(colName) + "]";
  });
  f = _unmaskTableauLiterals(f, lits);
  f = tableauTextConcatToSigma(f);
  if (warnings && TABLEAU_TABLE_CALC_TOKEN_RE.test(f)) {
    warnings.push(`\u26A0 Table-calc function embedded in a larger expression \u2014 NOT translated in place. Untranslated fragment: ${f.slice(0, 120)}`);
  }
  if (warnings) {
    const masked2 = f.replace(/"[^"]*"/g, '""').replace(/\[[^\]]*\]/g, "[]");
    const unmapped = /* @__PURE__ */ new Set();
    const scan = /\b([A-Z][A-Z0-9_]+)\s*\(/g;
    let mm;
    while ((mm = scan.exec(masked2)) !== null) {
      const fn = mm[1];
      if (TABLEAU_TABLE_CALC_TOKEN_RE.test(fn + "("))
        continue;
      unmapped.add(fn);
    }
    if (unmapped.size) {
      warnings.push(`\u26A0 Unmapped Tableau function(s) passed through unconverted: ${[...unmapped].join(", ")} \u2014 no validated Sigma equivalent yet. Rewrite manually; left as-is they error at query time.`);
    }
  }
  return f.trim();
}
function tableauIsAggregate(formula) {
  return /\b(SUM|AVG|COUNT|COUNTD|MAX|MIN|MEDIAN|STDEV|STDEVP|VAR|VARP|PERCENTILE|CORR|ATTR)\s*\(/i.test(formula);
}
function tableauFormulaIsRls(formula) {
  return /\b(USERNAME|FULLNAME|USERDOMAIN|ISMEMBEROF|ISUSERNAME|USERATTRIBUTE)\s*\(/i.test(formula || "");
}
function lookStripSql(sql) {
  if (!sql)
    return "";
  sql = sql.replace(/\$\{TABLE\}\./gi, "").trim();
  sql = sql.replace(/\$\{[^.}]+\.([^}]+)\}/g, "$1");
  sql = sql.replace(/`/g, "");
  sql = sql.replace(/\[([A-Za-z_][A-Za-z0-9_\s]*)\]/g, "$1");
  sql = sql.replace(/::\w[\w_]*/g, "");
  const castMatch = sql.match(/^(?:SAFE_CAST|TRY_CAST|CAST)\s*\(\s*("?[A-Za-z_][A-Za-z0-9_]*"?)\s+AS\s+\w[\w_]*\s*\)$/i);
  if (castMatch)
    sql = castMatch[1];
  sql = sql.replace(/"/g, "").trim();
  const m = sql.match(/^([A-Za-z_][A-Za-z0-9_]*)/);
  return m ? m[1] : sql;
}
function lookSigmaType(lkType) {
  const map = {
    string: "text",
    number: "number",
    yesno: "boolean",
    date: "datetime",
    time: "datetime",
    datetime: "datetime",
    zipcode: "text",
    tier: "text",
    location: "text",
    distance: "number",
    duration: "number",
    count: "number"
  };
  return map[(lkType || "").toLowerCase()] || "text";
}
function lookSigmaMetric(measureType, colName) {
  const dn = sigmaDisplayName(colName);
  const map = {
    sum: `Sum([${dn}])`,
    count: `CountIf(IsNotNull([${dn}]))`,
    count_distinct: `CountDistinct([${dn}])`,
    average: `Avg([${dn}])`,
    max: `Max([${dn}])`,
    min: `Min([${dn}])`,
    list: `ListAgg([${dn}])`,
    sum_distinct: `Sum(Distinct [${dn}])`,
    average_distinct: `Avg(Distinct [${dn}])`,
    median: `Median([${dn}])`,
    number: `[${dn}]`,
    yesno: `CountIf([${dn}])`
  };
  return map[(measureType || "").toLowerCase()] || `CountIf(IsNotNull([${dn}]))`;
}
export {
  SIGMA_CHART_ONLY_WINDOW_RE,
  TABLEAU_LOD_LEFTOVER_RE,
  TABLEAU_TABLE_CALC_TOKEN_CI_RE,
  TABLEAU_TABLE_CALC_TOKEN_RE,
  _SQL_KEYWORD_RE,
  decodeXmlEntities,
  detectUnsupportedSigmaFunction,
  formulaHasUntranslatableFragment,
  hasResidualCaseKeyword,
  hasResidualInfixOperator,
  lookColRef,
  lookConvertCase,
  lookConvertExpression,
  lookConvertMathExpr,
  lookIsComplexSql,
  lookSigmaMetric,
  lookSigmaType,
  lookSqlToSigmaRules,
  lookStripSql,
  lookUnknownFunctions,
  stripLineComments,
  stripOuterParens,
  tableauFormulaIsRls,
  tableauFormulaToSigma,
  tableauInToSigma,
  tableauIsAggregate,
  tableauParamSwitchToSigma,
  tableauTextConcatToSigma,
  tableauWindowToSigmaChart,
  tableauWindowUntranslatable
};
