/**
 * IBM Cognos Analytics → Sigma Data Model converter.   [LOCAL / WIP — not registered]
 *
 * MVP Phase 1 (per research/cognos-to-sigma.md): **Data Module JSON → Sigma DM** —
 * the cleanest, highest-leverage Cognos input (CA 11.x's modern semantic layer,
 * `GET /modules/{id}`). Mirrors the bobj.ts pattern: a tolerant normalizer maps the
 * source into a single IR, and `convertCognosIR()` emits the Sigma data model.
 *
 *   query subject (dbQuery)      → Sigma warehouse-table element
 *   query item (attribute)       → column   (business label preserved via `name`)
 *   query item (fact + aggregate)→ metric   (Sum/Avg/... of the column)
 *   calculation                  → calculated column / metric (expression translated)
 *   relationship (join)          → DM relationship (FK keys parsed from the expression)
 *
 * Cognos expression DSL → Sigma formula is handled by `translateCognosExpr()`
 * (total/average/...[ for ] → Sum/Avg or *Over; if/then/else → If; _add_days etc.).
 * Hard cases (running-total, moving-*, rank, master-detail) emit a warning and pass
 * through, matching the "flag, never fake" philosophy.
 *
 * NOT yet covered (research long-tail): Framework Manager .cpf, report-spec XML
 * (workbook side), dashboards, sub-queries, RAVE2 charts.
 */

import {
  resetIds, sigmaShortId, sigmaDisplayName,
  inferSigmaFormat, buildDerivedElements,
  type SigmaElement, type SigmaColumn, type SigmaMetric, type ConversionResult,
} from './sigma-ids.js';

// ── Normalized IR ────────────────────────────────────────────────────────────

export interface CognosItem {
  identifier: string;          // physical/logical id, e.g. REVENUE
  label?: string;              // business label, e.g. "Revenue"
  expression?: string;         // Cognos expression (calc) — undefined for plain column
  datatype?: string;
  usage?: string;              // 'attribute' | 'identifier' | 'fact' | 'measure'
  aggregate?: string;          // regularAggregate: total/average/count/maximum/minimum/none
  isCalculation?: boolean;
}
export interface CognosQuerySubject {
  identifier: string;          // e.g. SALES_FACT
  label?: string;
  database?: string;
  schema?: string;
  table?: string;              // physical table name (defaults to identifier)
  items: CognosItem[];
}
export interface CognosRelationship {
  left: string;                // query-subject identifier
  right: string;
  leftKey?: string;            // join column on the left subject (real CA shape: link[].leftRef)
  rightKey?: string;           // join column on the right subject (link[].rightRef)
  leftCard?: string;           // left maxcard ('one'|'many')
  rightCard?: string;          // right maxcard
  expression?: string;         // fallback: "[A].[K] = [B].[K]" (authored-fixture shape)
  cardinality?: string;
}
export interface CognosSecurityFilter {
  type: string;                // 'data-module-security-filter'
  subject?: string;            // query-subject the filter is scoped to (if known)
  name?: string;
  expression?: string;
  groups?: string[];           // CAM group/role refs the filter applies to (if present)
}
export interface CognosModule {
  name: string;
  querySubjects: CognosQuerySubject[];
  relationships: CognosRelationship[];
  securityFilters: CognosSecurityFilter[];
}
export interface CognosConvertOptions {
  connectionId?: string;
  database?: string;
  schema?: string;
  modelName?: string;
  // Customer-discovered translation rules (from the gap-scout, persisted in
  // ~/.cognos-to-sigma/learned-rules.json). Applied to each Cognos expression
  // BEFORE the built-in translator, so a validated discovered rule wins.
  learnedRules?: Array<{ pattern: string; template: string; flags?: string }>;
}

// Apply customer-learned rules (regex pattern → Sigma template) to a raw Cognos expression.
export function applyLearnedRules(expr: string, rules?: CognosConvertOptions['learnedRules']): string {
  let s = expr || '';
  for (const r of (rules || [])) {
    try { s = s.replace(new RegExp(r.pattern, r.flags || 'gi'), r.template); } catch { /* bad rule — skip */ }
  }
  return s;
}

// ── Ingest: Data Module JSON → IR (tolerant of the common shape variants) ─────

const arr = (x: any): any[] => (Array.isArray(x) ? x : x == null ? [] : [x]);
const lc = (s: any) => String(s ?? '').toLowerCase();

export function normalizeCognosDataModule(input: any): CognosModule {
  const root = typeof input === 'string' ? JSON.parse(input) : input;
  const name = root.label || root.identifier || root.name || 'Cognos Data Module';

  const querySubjects: CognosQuerySubject[] = [];
  // Cognos uses `querySubject`; some exports nest under `module.querySubject`.
  const qsList = arr(root.querySubject || root.querySubjects || root.module?.querySubject);

  for (const qs of qsList) {
    const identifier = qs.identifier || qs.idForExpression || qs.label || 'QUERY_SUBJECT';
    // physical table: real CA shape is qs.ref = ["M1.Sales"] (useSpec.sheet/table);
    // fall back to the authored-fixture shape definition.dbQuery.tableRef.sourceTable.
    let table = identifier, database: string | undefined, schema: string | undefined;
    const ref0 = arr(qs.ref)[0];
    if (typeof ref0 === 'string' && ref0.includes('.')) {
      table = ref0.split('.').slice(1).join('.');         // "M1.Sales" → "Sales"
    } else {
      const tableRef = arr(qs.definition?.dbQuery?.tableRef)[0] || qs.sourceTable || qs.table;
      const src = tableRef?.sourceTable || tableRef || {};
      table = src.name || (typeof tableRef === 'string' ? tableRef : identifier);
      database = src.catalog || src.database || qs.catalog;
      schema = src.schema || qs.schema;
    }

    const items: CognosItem[] = [];
    for (const raw of arr(qs.item || qs.items)) {
      const qi = raw.queryItem || raw.calculation || raw.measure;
      if (!qi || !(qi.identifier || qi.label)) continue;   // skip folders / nested groups
      const ident = qi.identifier || qi.label;
      const expr = qi.expression;
      const isCalc = !!raw.calculation || (expr != null && !isPlainColumn(expr, identifier));
      items.push({
        identifier: ident,
        label: qi.label,
        expression: expr,
        datatype: qi.datatype || qi.highlevelDatatype,
        usage: lc(qi.usage),
        aggregate: lc(qi.regularAggregate || qi.aggregate || qi.aggregateFunction),
        isCalculation: isCalc,
      });
    }
    querySubjects.push({ identifier, label: qs.label, database, schema, table, items });
  }

  const relationships: CognosRelationship[] = [];
  for (const rel of arr(root.relationship || root.relationships)) {
    const links = arr(rel.link);
    // real CA shape: rel.left.ref / rel.right.ref (subjects) + link[].leftRef/rightRef (columns)
    const left = qsKey(rel.left?.ref || links[0]?.ref || rel.left);
    const right = qsKey(rel.right?.ref || links[1]?.ref || rel.right);
    if (!left || !right) continue;
    const colLink = links.find((l: any) => l && (l.leftRef || l.rightRef));
    relationships.push({
      left, right,
      leftKey: colLink?.leftRef, rightKey: colLink?.rightRef,
      leftCard: lc(rel.left?.maxcard), rightCard: lc(rel.right?.maxcard),
      expression: rel.expression || rel.linkExpression,
      cardinality: rel.cardinality,
    });
  }

  // Security filters (detect-only — see ConversionResult.security). Real CA data
  // modules carry row-level security as `securityFilter` entries (top-level or
  // per-query-subject) holding an expression + the CAM groups/roles it applies to.
  // Shape tolerance: also catch plain `filter` entries explicitly marked as security.
  const securityFilters: CognosSecurityFilter[] = [];
  const pushSec = (sf: any, subject?: string) => {
    if (!sf || typeof sf !== 'object') return;
    const groups = arr(sf.securityObject || sf.member || sf.members || sf.appliesTo)
      .map((g: any) => (typeof g === 'string' ? g : g?.searchPath || g?.ref || g?.identifier))
      .filter(Boolean);
    securityFilters.push({
      type: 'data-module-security-filter',
      subject,
      name: sf.label || sf.identifier,
      expression: sf.expression || sf.filterDefinition || sf.embeddedFilter?.expression,
      ...(groups.length ? { groups } : {}),
    });
  };
  for (const sf of arr(root.securityFilter || root.securityFilters)) pushSec(sf);
  for (const qs of qsList) {
    for (const sf of arr(qs.securityFilter || qs.securityFilters)) pushSec(sf, qs.identifier || qs.label);
  }
  for (const fl of arr(root.filter || root.filters)) {
    if (fl && (lc(fl.classifier).includes('security') || arr(fl.propertyOverride).some((p: any) => lc(p).includes('security')))) pushSec(fl);
  }

  return { name, querySubjects, relationships, securityFilters };
}

// A query-subject ref may arrive as "NS.SALES_FACT" or "[NS].[SALES_FACT]" — take the tail.
function qsKey(ref: string): string {
  const parts = String(ref).replace(/[[\]]/g, '').split('.');
  return parts[parts.length - 1].trim();
}
// A plain column = a bare identifier expression ("Quantity") — real CA shape — OR a
// bracketed self-subject ref ("[Sales].[Quantity]") — authored-fixture shape.
function isPlainColumn(expr: string, subjectId: string): boolean {
  const e = (expr || '').trim();
  if (/^[A-Za-z_][\w ]*$/.test(e)) return true;                  // bare identifier
  const m = e.replace(/[[\]\s]/g, '').match(/^([\w]+)\.([\w]+)$/);
  return !!m && m[1].toUpperCase() === subjectId.toUpperCase();
}

// ── Convert IR → Sigma data model ────────────────────────────────────────────

interface ElemCtx {
  element: SigmaElement;
  columns: SigmaColumn[];
  metrics: SigmaMetric[];
  order: string[];
  colIdByName: Map<string, string>;
  tableTail: string;   // warehouse table name (path tail) — the prefix Sigma resolves col refs against
}

export function convertCognosIR(model: CognosModule, options: CognosConvertOptions = {}): ConversionResult {
  resetIds();
  const { connectionId = '<CONNECTION_ID>', database: dbOverride = '', schema: schOverride = '', modelName } = options;
  const warnings: string[] = [];
  const ctxByKey = new Map<string, ElemCtx>();

  // Pass 1 — one Sigma element per query subject (physical table).
  for (const qs of model.querySubjects) {
    const key = qs.identifier.toUpperCase();
    const path: string[] = [];
    const db = dbOverride || qs.database || '';
    const sch = schOverride || qs.schema || '';
    if (db) path.push(db);
    if (sch) path.push(sch);
    const tableTail = (qs.table || qs.identifier).toUpperCase();
    path.push(tableTail);
    const element: SigmaElement = {
      id: sigmaShortId(), kind: 'table', name: sigmaDisplayName(qs.identifier),
      source: { connectionId, kind: 'warehouse-table', path },
      columns: [], order: [],
    };
    ctxByKey.set(key, { element, columns: [], metrics: [], order: [], colIdByName: new Map(), tableTail });
  }

  const ensureRawCol = (ctx: ElemCtx, _tableKey: string, ident: string, hidden = false): string => {
    const disp = sigmaDisplayName(ident);
    const existing = ctx.colIdByName.get(disp);
    if (existing) return existing;
    const id = sigmaShortId();
    // warehouse-table self-ref: prefix is the raw table tail (Sigma fuzzy-matches the column)
    const col: SigmaColumn = { id, formula: `[${ctx.tableTail}/${disp}]` };
    if (hidden) col.hidden = true;
    ctx.columns.push(col); ctx.order.push(id); ctx.colIdByName.set(disp, id);
    return id;
  };

  // Pass 2 — place each query item as a column or metric on its subject.
  for (const qs of model.querySubjects) {
    const key = qs.identifier.toUpperCase();
    const ctx = ctxByKey.get(key)!;
    for (const item of qs.items) {
      const dispName = sigmaDisplayName(item.label || item.identifier);
      const isMeasure = !item.isCalculation && (item.usage === 'fact' || item.usage === 'measure')
        && item.aggregate && item.aggregate !== 'none';

      if (item.isCalculation && item.expression) {
        const { formula, warnings: w } = translateCognosExpr(applyLearnedRules(item.expression, options.learnedRules), qs, ensureRawCol, ctx);
        w.forEach(x => warnings.push(`"${qs.identifier}.${item.identifier}": ${x}`));
        // a calc that aggregates → metric, else calculated column
        if (/\b(Sum|Avg|Count|Min|Max|.*Over)\(/.test(formula)) {
          const m: SigmaMetric = { id: sigmaShortId(), name: dispName, formula };
          const fmt = inferSigmaFormat(formula, dispName); if (fmt) (m as any).format = fmt;
          ctx.metrics.push(m);
        } else {
          const id = sigmaShortId();
          ctx.columns.push({ id, name: dispName, formula }); ctx.order.push(id);
        }
      } else if (isMeasure) {
        ensureRawCol(ctx, key, item.identifier);
        const agg = aggFn(item.aggregate!, `[${sigmaDisplayName(item.identifier)}]`);
        const m: SigmaMetric = { id: sigmaShortId(), name: dispName, formula: agg };
        const fmt = inferSigmaFormat(agg, dispName); if (fmt) (m as any).format = fmt;
        ctx.metrics.push(m);
      } else {
        // plain attribute → column (preserve business label)
        const physDisp = sigmaDisplayName(item.identifier);
        const existing = ctx.colIdByName.get(physDisp);
        if (existing) { if (dispName !== physDisp) { /* alias already mapped */ } continue; }
        const id = sigmaShortId();
        const col: SigmaColumn = { id, formula: `[${ctx.tableTail}/${physDisp}]` };
        if (dispName !== physDisp) col.name = dispName;
        ctx.columns.push(col); ctx.order.push(id); ctx.colIdByName.set(physDisp, id);
      }
    }
  }

  // Pass 3 — relationships from joins.
  for (const rel of model.relationships) {
    // Real CA shape gives join columns directly; fall back to parsing an expression.
    let leftTable = rel.left, rightTable = rel.right, leftCol = rel.leftKey, rightCol = rel.rightKey;
    if (!leftCol || !rightCol) {
      const parsed = parseJoinExpr(rel.expression);
      if (!parsed) { warnings.push(`Relationship ${rel.left}→${rel.right}: no join columns and expression "${trunc(rel.expression)}" not a simple equi-join — add manually in Sigma.`); continue; }
      ({ leftTable, leftCol, rightTable, rightCol } = parsed);
    }
    // Sigma relationship source = the "many" side. Flip if the RIGHT side is many.
    const rightIsMany = /many|\bn\b|\*/.test(rel.rightCard || '');
    const leftIsMany = /many|\bn\b|\*/.test(rel.leftCard || '');
    if (rightIsMany && !leftIsMany) {
      [leftTable, leftCol, rightTable, rightCol] = [rightTable, rightCol, leftTable, leftCol];
    }
    const srcKey = leftTable.toUpperCase(), tgtKey = rightTable.toUpperCase();
    const srcCtx = ctxByKey.get(srcKey), tgtCtx = ctxByKey.get(tgtKey);
    if (!srcCtx || !tgtCtx) { warnings.push(`Relationship ${srcKey}→${tgtKey}: a query subject is missing — relationship skipped.`); continue; }
    const srcColId = ensureRawCol(srcCtx, srcKey, leftCol!, true);
    const tgtColId = ensureRawCol(tgtCtx, tgtKey, rightCol!, true);
    (srcCtx.element.relationships ||= []).push({
      id: sigmaShortId(), targetElementId: tgtCtx.element.id,
      keys: [{ sourceColumnId: srcColId, targetColumnId: tgtColId }], name: tgtKey,
    });
  }

  // Finalize.
  const elements: SigmaElement[] = [];
  for (const ctx of ctxByKey.values()) {
    ctx.element.columns = ctx.columns; ctx.element.order = ctx.order;
    if (ctx.metrics.length) (ctx.element as any).metrics = ctx.metrics;
    elements.push(ctx.element);
  }
  for (const de of buildDerivedElements(elements)) elements.push(de);

  const stats = {
    querySubjects: model.querySubjects.length,
    elements: elements.length,
    columns: elements.reduce((n, e) => n + (e.columns?.length || 0), 0),
    metrics: elements.reduce((n, e) => n + ((e as any).metrics?.length || 0), 0),
    relationships: elements.reduce((n, e) => n + (e.relationships?.length || 0), 0),
  };
  const security = (model.securityFilters || []).map((sf) => ({ ...sf }));
  if (security.length) {
    warnings.push(`SECURITY: ${security.length} data-module security filter(s) detected — NOT ported into the model spec. ` +
      `Run the skill's RLS flow (scripts/apply_sigma_rls.py) after posting the model; skipping leaves ALL rows visible to everyone.`);
  }
  return {
    model: { name: modelName || model.name, schemaVersion: 1, pages: [{ id: sigmaShortId(), name: 'Page 1', elements }] },
    warnings, stats,
    ...(security.length ? { security } : {}),
  };
}

/** Top-level entry: Data Module JSON (string or object) → Sigma data model. */
export function convertCognosToSigma(input: string | object, options: CognosConvertOptions = {}): ConversionResult {
  return convertCognosIR(normalizeCognosDataModule(input), options);
}

// ── Cognos expression DSL → Sigma formula ────────────────────────────────────

const AGG_MAP: Record<string, string> = {
  total: 'Sum', sum: 'Sum', average: 'Avg', avg: 'Avg',
  count: 'Count', 'count distinct': 'CountDistinct',
  maximum: 'Max', max: 'Max', minimum: 'Min', min: 'Min',
};
const OVER_MAP: Record<string, string> = { total: 'SumOver', sum: 'SumOver', average: 'AvgOver', count: 'CountOver', maximum: 'MaxOver', minimum: 'MinOver' };

function aggFn(agg: string, inner: string): string {
  const fn = AGG_MAP[agg] || 'Sum';
  return `${fn}(${inner})`;
}

export function translateCognosExpr(
  expr: string, qs: CognosQuerySubject, ensureRawCol: (c: ElemCtx, k: string, i: string) => string, ctx: ElemCtx,
): { formula: string; warnings: string[] } {
  const warnings: string[] = [];
  let f = (expr || '').trim();

  // Flag unsupported window/running constructs up front (pass through, warn).
  for (const bad of ['running-total', 'running-count', 'running-average', 'running-difference', 'moving-total', 'moving-average', 'rank', 'percentile', 'quantile', 'tertile']) {
    if (new RegExp(`\\b${bad}\\b`, 'i').test(f)) warnings.push(`uses Cognos "${bad}" (window/running calc) — no clean single-column Sigma analog; needs manual authoring (window function).`);
  }

  // Column references: [NS].[QS].[Item] | [QS].[Item] | [Item]  → [Display Name]
  f = f.replace(/\[[^\]]+\](?:\.\[[^\]]+\])*/g, (ref) => {
    const segs = ref.split('.').map(s => s.replace(/[[\]]/g, '').trim());
    const item = segs[segs.length - 1];
    return `[${sigmaDisplayName(item)}]`;
  });

  // SQL-style CASE … WHEN … THEN … END (common in Cognos calc cols) →
  // searched CASE → nested If(); simple CASE (case <sel> when <v>…) → Switch().
  f = translateCaseExpr(f);
  // Bracket bare column identifiers (Cognos calcs often reference columns unbracketed,
  // e.g. `case when (Product_line) = …`). Only bracket words that match a real column on
  // this subject, and never touch text already inside [ ].
  const identMap = new Map<string, string>();
  for (const it of (qs.items || [])) identMap.set(it.identifier.toLowerCase(), sigmaDisplayName(it.label || it.identifier));
  if (identMap.size) {
    // Prefix with the warehouse table tail so a bare ref to a fact column resolves to the
    // raw column, NOT the same-named metric (a bare `[Revenue]` is otherwise ambiguous).
    const pfx = (ctx && (ctx as any).tableTail) ? `${(ctx as any).tableTail}/` : '';
    f = f.replace(/\[[^\]]*\]|[^[\]]+/g, (seg) => seg.startsWith('[') ? seg
      : seg.replace(/\b([A-Za-z_][A-Za-z0-9_]*)\b(?!\s*\()/g, (w) => {
          const d = identMap.get(w.toLowerCase());
          return d ? `[${pfx}${d}]` : w;
        }));
  }
  if (/\bcase\b[\s\S]*\bwhen\b/i.test(f)) warnings.push('a CASE expression could not be fully translated (nested or non-standard) — review/author manually.');

  // Aggregations with optional "for" scope: total([X] for [A],[B])
  f = f.replace(/\b(total|sum|average|count|maximum|minimum)\s*\(\s*([^()]*?)\s+for\s+([^()]*)\)/gi,
    (_m, fn, inner, scope) => {
      const over = OVER_MAP[lc(fn)] || 'SumOver';
      const dims = scope.split(',').map((s: string) => s.trim()).join(', ');
      return `${over}(${inner.trim()}, ${dims})`;
    });
  // Plain aggregations: total([X]) → Sum([X])
  f = f.replace(/\b(total|sum|average|count|maximum|minimum)\s*\(/gi, (_m, fn) => `${AGG_MAP[lc(fn)] || 'Sum'}(`);

  // if (..) then (..) else (..)  → If(.., .., ..)   (handles nested else-if chains)
  let guard = 0;
  while (/\bif\s*\(/i.test(f) && guard++ < 25) {
    f = f.replace(/\bif\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)\s*then\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)\s*else\s*/i,
      (_m, cond, thenv) => `If(${cond.trim()}, ${thenv.trim()}, `);
    // close the trailing else value if it's a bare token/paren group
    if (!/\bif\s*\(/i.test(f)) break;
  }
  // balance the If( we opened (rough: append closing parens for each unmatched If()
  const opens = (f.match(/If\(/g) || []).length;
  const closes = (f.match(/\)/g) || []).length - (f.match(/\(/g) || []).length + opens;
  if (opens > 0 && closes < opens) f = f + ')'.repeat(opens - Math.max(0, closes));

  // Date helpers
  f = f.replace(/_add_days\s*\(([^,]+),\s*([^)]+)\)/gi, (_m, d, n) => `DateAdd("day", ${n.trim()}, ${d.trim()})`);
  f = f.replace(/_add_months\s*\(([^,]+),\s*([^)]+)\)/gi, (_m, d, n) => `DateAdd("month", ${n.trim()}, ${d.trim()})`);
  f = f.replace(/_add_years\s*\(([^,]+),\s*([^)]+)\)/gi, (_m, d, n) => `DateAdd("year", ${n.trim()}, ${d.trim()})`);
  f = f.replace(/_days_between\s*\(([^,]+),\s*([^)]+)\)/gi, (_m, a, b) => `DateDiff("day", ${b.trim()}, ${a.trim()})`);
  f = f.replace(/\bextract\s*\(\s*(year|month|day)\s*,\s*([^)]+)\)/gi, (_m, part, d) => `DatePart("${lc(part)}", ${d.trim()})`);

  // String functions + operators
  f = f.replace(/\bsubstring\s*\(/gi, 'Mid(').replace(/\bsubstr\s*\(/gi, 'Mid(')
       .replace(/\bupper\s*\(/gi, 'Upper(').replace(/\blower\s*\(/gi, 'Lower(').replace(/\btrim\s*\(/gi, 'Trim(');
  // substitute(pattern, replacement, source) → RegexpReplace(source, pattern, replacement)
  f = f.replace(/\bsubstitute\s*\(\s*([^,]+?)\s*,\s*([^,]+?)\s*,\s*([^)]+?)\s*\)/gi,
    (_m, p, r, s) => `RegexpReplace(${s.trim()}, ${p.trim()}, ${r.trim()})`);
  // cast(expr AS type) / cast(expr, type) → Text() for char types, numeric passthrough otherwise
  const castRepl = (_m: string, x: string, ty: string) => (/char|text|string|varchar/i.test(ty) ? `Text(${x.trim()})` : x.trim());
  f = f.replace(/\bcast\s*\(\s*([^,()]+?)\s+as\s+(\w+)[^)]*\)/gi, castRepl);
  f = f.replace(/\bcast\s*\(\s*([^,()]+?)\s*,\s*(\w+)[^)]*\)/gi, castRepl);
  // standalone type-coercion fns: varchar()/char()/nvarchar() → Text(); decimal()/double() → passthrough
  f = f.replace(/\b(?:n?varchar|char)\s*\(\s*([^,)]+?)(?:\s*,\s*\d+)?\s*\)/gi, (_m, x) => `Text(${x.trim()})`);
  f = f.replace(/\b(?:decimal|double|float|number)\s*\(\s*([^,)]+?)(?:\s*,[^)]*)?\)/gi, (_m, x) => x.trim());
  f = f.replace(/\|\|/g, '&');          // Cognos concat → Sigma concat
  f = f.replace(/\bcoalesce\s*\(/gi, 'Coalesce(');
  // Math fns with direct Sigma analogs
  f = f.replace(/\babs\s*\(/gi, 'Abs(').replace(/\bround\s*\(/gi, 'Round(')
       .replace(/\bfloor\s*\(/gi, 'Floor(').replace(/\bceiling\s*\(/gi, 'Ceiling(')
       .replace(/\bsqrt\s*\(/gi, 'Sqrt(').replace(/\bln\s*\(/gi, 'Ln(')
       .replace(/\bmod\s*\(/gi, 'Mod(').replace(/\bpower\s*\(/gi, 'Power(');
  f = f.replace(/'([^']*)'/g, '"$1"');  // Cognos single-quoted strings → Sigma double-quoted

  // Unknown bareword(...) functions → warn (kept as-is for manual review)
  const known = /\b(If|Switch|Sum|Avg|Count|CountDistinct|Min|Max|SumOver|AvgOver|CountOver|MinOver|MaxOver|DateAdd|DateDiff|DatePart|Mid|Upper|Lower|Trim|Coalesce|Text|RegexpReplace|Replace|Abs|Round|Floor|Ceiling|Sqrt|Ln|Mod|Power)\b/;
  for (const m of f.matchAll(/\b([a-z][a-z0-9_-]*)\s*\(/gi)) {
    if (!known.test(m[1]) && !/^(and|or|not|in|like|between|then|else|end|case|when)$/i.test(m[1])) {
      warnings.push(`function "${m[1]}()" has no confirmed Sigma mapping — review/translate manually.`);
    }
  }
  return { formula: f, warnings };
}

// CASE … END → Sigma. Searched CASE → nested If(); simple CASE (selector before the
// first WHEN) → Switch(selector, v1, r1, …, default). Handles flat (non-nested) CASE;
// anything it can't parse is left intact (and flagged by the caller).
function translateCaseExpr(s: string): string {
  let guard = 0;
  while (/\bcase\b/i.test(s) && guard++ < 25) {
    const m = s.match(/\bcase\b([\s\S]*?)\bend\b/i);
    if (!m || m.index == null) break;
    const repl = convertCaseBody(m[1]);
    if (repl == null) break;
    s = s.slice(0, m.index) + repl + s.slice(m.index + m[0].length);
  }
  return s;
}
function convertCaseBody(body: string): string | null {
  const em = body.match(/\belse\b([\s\S]*)$/i);
  const elseVal = em ? em[1].trim() : 'Null';
  const head = em ? body.slice(0, em.index) : body;
  const fw = head.search(/\bwhen\b/i);
  if (fw < 0) return null;
  const selector = head.slice(0, fw).trim();          // empty ⇒ searched CASE
  const clauses = head.slice(fw).split(/\bwhen\b/i).map(c => c.trim()).filter(Boolean);
  const pairs: Array<[string, string]> = [];
  for (const cl of clauses) {
    const tm = cl.match(/^([\s\S]*?)\bthen\b([\s\S]*)$/i);
    if (!tm) return null;
    pairs.push([tm[1].trim(), tm[2].trim()]);
  }
  if (!pairs.length) return null;
  if (selector) return `Switch(${[selector, ...pairs.flatMap(p => [p[0], p[1]]), elseVal].join(', ')})`;
  let out = elseVal;
  for (let i = pairs.length - 1; i >= 0; i--) out = `If(${pairs[i][0]}, ${pairs[i][1]}, ${out})`;
  return out;
}

// ── small parsers ─────────────────────────────────────────────────────────────

function parseJoinExpr(expr?: string): { leftTable: string; leftCol: string; rightTable: string; rightCol: string } | null {
  if (!expr) return null;
  const e = expr.replace(/[[\]]/g, '');
  // SALES_FACT.PRODUCT_KEY = PRODUCT_DIM.PRODUCT_KEY   (single equi-join only for MVP)
  const m = e.match(/([\w]+)\.([\w]+)\s*=\s*([\w]+)\.([\w]+)/);
  if (!m) return null;
  if (/\band\b|\bor\b/i.test(e)) return null; // composite/condition joins → manual
  return { leftTable: m[1].trim(), leftCol: m[2].trim(), rightTable: m[3].trim(), rightCol: m[4].trim() };
}
const trunc = (s?: string, n = 80) => (s && s.length > n ? s.slice(0, n) + '…' : (s || ''));
