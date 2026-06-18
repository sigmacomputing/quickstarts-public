view: customer_dim {
  sql_table_name: CSA.TJ.CUSTOMER_DIM ;;

  dimension: customer_key {
    primary_key: yes
    hidden: yes
    type: number
    sql: ${TABLE}.CUSTOMER_KEY ;;
  }

  dimension: region {
    type: string
    sql: ${TABLE}.REGION ;;
  }

  dimension_group: first_order {
    type: time
    timeframes: [raw, date, month, year]
    sql: ${TABLE}.FIRST_ORDER_DATE ;;
  }

  dimension: customer_segment {
    type: string
    sql: ${TABLE}.CUSTOMER_SEGMENT ;;
  }

  dimension: loyalty_tier {
    type: string
    sql: ${TABLE}.LOYALTY_TIER ;;
  }
}
