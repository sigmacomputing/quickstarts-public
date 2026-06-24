view: order_fact {
  sql_table_name: CSA.TJ.ORDER_FACT ;;

  # ── Parameters (drive the dynamic dimensions below) ──────────────────────
  parameter: metric_basis {
    type: unquoted
    default_value: "scaled"
    allowed_value: { label: "Net Revenue" value: "net" }
    allowed_value: { label: "Net (per-thousand)" value: "scaled" }
  }

  parameter: revenue_column {
    type: unquoted
    default_value: "NET_REVENUE"
    allowed_value: { value: "NET_REVENUE" }
    allowed_value: { value: "ORDER_LINE" }
  }

  dimension: order_id {
    type: string
    sql: ${TABLE}.ORDER_ID ;;
  }

  dimension: order_line {
    type: number
    sql: ${TABLE}.ORDER_LINE ;;
  }

  dimension: pk {
    primary_key: yes
    hidden: yes
    type: string
    sql: ${TABLE}.ORDER_ID || '-' || ${TABLE}.ORDER_LINE ;;
  }

  dimension: customer_key {
    hidden: yes
    type: number
    sql: ${TABLE}.CUSTOMER_KEY ;;
  }

  dimension: order_channel {
    type: string
    sql: ${TABLE}.ORDER_CHANNEL ;;
  }

  dimension: ship_method {
    type: string
    sql: ${TABLE}.SHIP_METHOD ;;
  }

  dimension: order_status {
    type: string
    sql: ${TABLE}.ORDER_STATUS ;;
  }

  dimension: net_revenue {
    hidden: yes
    type: number
    sql: ${TABLE}.NET_REVENUE ;;
  }

  # ── Liquid {% if %} field-picker: switches expression on a parameter.
  #    Looker's unfiltered default state uses the DEFAULT branch (metric_basis
  #    default = "scaled"), so a faithful static conversion resolves to that. ──
  dimension: selected_metric {
    label: "Selected Metric"
    type: number
    sql:
      {% if metric_basis._parameter_value == 'scaled' %}
        ${TABLE}.NET_REVENUE / 1000.0
      {% else %}
        ${TABLE}.NET_REVENUE
      {% endif %} ;;
  }

  # ── ${parameter} substitution: parameter injected directly into SQL (no
  #    ${TABLE} ref) — the converter's line-912 "parameter substitution" case.
  #    Resolves to the parameter default value (NET_REVENUE). ──
  dimension: dynamic_revenue_col {
    label: "Dynamic Revenue Col"
    type: number
    sql: ${revenue_column} ;;
  }

  measure: total_net_revenue {
    type: sum
    sql: ${net_revenue} ;;
    value_format_name: usd
  }

  measure: order_count {
    type: count_distinct
    sql: ${TABLE}.ORDER_ID ;;
  }

  measure: average_order_value {
    type: number
    sql: 1.0 * ${total_net_revenue} / NULLIF(${order_count}, 0) ;;
    value_format_name: usd
  }
}
