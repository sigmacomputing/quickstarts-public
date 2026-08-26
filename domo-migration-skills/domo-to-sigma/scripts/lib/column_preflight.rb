# frozen_string_literal: true
require 'set'
require_relative 'domo_sigma_util'

#
# Pure logic for the domo DM column pre-flight check (bead m655): diffing a
# Domo dataset's schema columns against a warehouse table's REAL columns
# against what discovery/dataset-map.json's excludeColumns/columnOverrides
# already resolve, and — for anything still unresolved — checking one
# extensible derivation-pattern registry for an auto-*suggestion* (never an
# auto-applied fix; see docs/superpowers/specs/2026-07-31-domo-dm-column-
# preflight-design.md). No HTTP, no filesystem — the live warehouse-column
# fetch is scripts/preflight-columns.rb's sole network seam; everything here
# is pure and offline-testable (test/test-column-preflight.rb), matching
# build-dm.rb's own derive_map_entry/autofill_dataset_map split.
module ColumnPreflight
  # A dataset-map.json entry flagged with one of these `_source` values (see
  # build-dm.rb's derive_map_entry) has no real warehouse table to check yet —
  # a query-only stream, or landed data with no connector at all. Shared here
  # (not just preflight-columns.rb's own concern) so build-dm.rb's "needs
  # human review" warning and preflight-columns.rb's/run_preflight's skip
  # condition can never drift apart into two different lists.
  SENTINEL_SOURCES = %w[domo-stream-config-query-only domo-landed-data].freeze

  module_function

  # Uppercase, strip every non-alphanumeric character — loose comparison
  # between a missing Domo column's name and a candidate warehouse column's
  # name (e.g. "Order Date" vs "ORDER_DATE_KEY" both normalize with a shared
  # "ORDERDATE" prefix).
  def normalize_name(name)
    name.to_s.upcase.gsub(/[^A-Z0-9]/, '')
  end

  # schema_cols: Domo's discovery/datasets.json schema.columns[] ({'name','type'}).
  # warehouse_cols: [{'name','type'}] as fetched live for the mapped table.
  # excluded: Array of upcased column names already in dataset-map's excludeColumns.
  # overrides: Hash of upcased column name => columnOverrides entry (already
  #            resolved by a human in dataset-map.json).
  #
  # Returns { 'missing' => [names], 'resolved_by_exclude' => [names],
  #           'resolved_by_override' => [names] } — 'missing' is every Domo
  # column absent from warehouse_cols that isn't already excluded or overridden.
  # Matching against warehouse_cols is case-insensitive (warehouse catalogs
  # commonly return lowercase names for some connectors — Postgres, BigQuery —
  # while Domo's own names may be any case).
  def diff_columns(schema_cols, warehouse_cols, excluded, overrides)
    # Warehouse-existence is checked on the SAME transform build_element
    # actually emits into the formula reference ([table/display_name(raw)] —
    # see build-dm.rb) — not the raw Domo name and not the raw warehouse
    # catalog name. Two differently-styled Domo names for the same column
    # (e.g. "order_date" and "Order Date") must both resolve identically here,
    # since build_element emits the identical reference for both.
    # excludeColumns/columnOverrides matching stays on the RAW Domo name
    # (unchanged) — those are human-authored keys, not a warehouse-existence
    # check.
    warehouse_display_names = Array(warehouse_cols)
      .map { |c| DomoSigma.display_name(c['name'].to_s).upcase }.to_set
    missing = []
    resolved_by_exclude = []
    resolved_by_override = []
    Array(schema_cols).each do |c|
      raw = (c['name'] || c['id']).to_s
      next if raw.empty?
      up = raw.upcase
      next if warehouse_display_names.include?(DomoSigma.display_name(raw).upcase)
      if excluded.include?(up)
        resolved_by_exclude << raw
      elsif overrides.key?(up)
        resolved_by_override << raw
      else
        missing << raw
      end
    end
    { 'missing' => missing, 'resolved_by_exclude' => resolved_by_exclude,
      'resolved_by_override' => resolved_by_override }
  end

  # Warehouse column types treated as "numeric" for the derivation pattern
  # below — a YYYYMMDD surrogate key is always an integer/number type, never
  # text. Deliberately conservative (no VARCHAR/TEXT) — a text column matching
  # the name pattern is NOT a YYYYMMDD key candidate.
  NUMERIC_TYPES = %w[LONG DECIMAL DOUBLE INTEGER NUMBER BIGINT NUMERIC FLOAT SMALLINT TINYINT].freeze

  def numeric_warehouse_column?(col)
    NUMERIC_TYPES.include?(col['type'].to_s.upcase)
  end

  # Sigma's SERVER auto-names a raw warehouse table column (as returned by
  # fetch_warehouse_columns / /v2/connections/tables/<inodeId>/columns —
  # e.g. an unquoted Snowflake identifier, all-caps with underscores) by
  # Title-Casing every underscore-separated word UNCONDITIONALLY:
  # ORDER_DATE_KEY -> "Order Date Key", TAX_AMOUNT -> "Tax Amount". Confirmed
  # LIVE against ~28 real columns on one warehouse table, 2026-08-03.
  #
  # This is DELIBERATELY separate from DomoSigma.display_name
  # (domo_sigma_util.rb), which preserves an all-caps word-segment as-is
  # (e.g. an "ID"/"URL" acronym) — the right rule for DOMO'S OWN
  # dataset/calc-field names, but NOT for a raw warehouse identifier Sigma
  # is auto-labeling fresh, where there is no way to distinguish "a real
  # acronym" from "just an all-caps word" — Sigma doesn't try, so this
  # helper doesn't either. Do not merge these two functions: same input
  # shape, two different correct answers depending on which naming
  # pipeline produced the name.
  def warehouse_column_display_name(raw)
    raw.to_s.split('_').map { |w| w.empty? ? w : w.capitalize }.join(' ')
  end

  # The one derivation pattern shipped in this PR (see design doc — the
  # registry is shaped so a second pattern is additive, but only one exists
  # today; YAGNI). Triggers when a missing column's Domo type is DATE/DATETIME
  # and warehouse_cols has EXACTLY ONE numeric-typed column whose normalized
  # name starts with the missing column's own normalized name. Zero or 2+
  # candidates -> nil (ambiguous or no match) — never guess.
  #
  # missing_col_name: the raw Domo column name (e.g. "Order Date").
  # domo_type: the Domo column's raw type string (e.g. "DATE").
  # warehouse_cols: same shape as diff_columns's second argument.
  #
  # Returns nil, or { 'pattern' => 'yyyymmdd_integer_key',
  #   'candidate_source_column' => name, 'suggested_formula' => formula }.
  def suggest_derivation(missing_col_name, domo_type, warehouse_cols)
    return nil unless %w[DATE DATETIME].include?(domo_type.to_s.upcase)
    target = normalize_name(missing_col_name)
    return nil if target.empty?
    candidates = Array(warehouse_cols).select do |c|
      numeric_warehouse_column?(c) && normalize_name(c['name']).start_with?(target)
    end
    return nil unless candidates.size == 1
    source = candidates.first['name']
    # The formula reference must be the column's SIGMA-ASSIGNED display label
    # (what Sigma auto-names the raw warehouse column), not the raw warehouse
    # identifier itself — see warehouse_column_display_name above.
    display = warehouse_column_display_name(source)
    {
      'pattern' => 'yyyymmdd_integer_key',
      'candidate_source_column' => source,
      'suggested_formula' =>
        "MakeDate(Floor([#{display}]/10000), Floor(Mod([#{display}],10000)/100), Mod([#{display}],100))",
    }
  end

  # Builds one discovery/column-preflight.json entry for a single dataset.
  # `table` is the mapped warehouse table name (dataset-map.json's own
  # `table` value) — carried through purely for the report's readability.
  def build_report_entry(table, schema_cols, warehouse_cols, excluded, overrides)
    diff = diff_columns(schema_cols, warehouse_cols, excluded, overrides)
    domo_type_by_name = Array(schema_cols).each_with_object({}) do |c, h|
      h[(c['name'] || c['id']).to_s] = c['type']
    end
    suggestions = {}
    diff['missing'].each do |name|
      s = suggest_derivation(name, domo_type_by_name[name], warehouse_cols)
      suggestions[name] = s if s
    end
    {
      'table' => table,
      'missing' => diff['missing'],
      'resolved_by_exclude' => diff['resolved_by_exclude'],
      'resolved_by_override' => diff['resolved_by_override'],
      'suggested_overrides' => suggestions,
    }
  end
end
