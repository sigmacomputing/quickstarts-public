view: order_fact {
  sql_table_name: CSA.TJ.ORDER_FACT ;;

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
