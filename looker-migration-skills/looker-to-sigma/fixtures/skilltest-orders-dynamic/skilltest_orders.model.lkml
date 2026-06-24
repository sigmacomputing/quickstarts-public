connection: "snowflake_csa"

include: "views/*.view.lkml"

explore: order_fact {
  label: "Orders"

  join: customer_dim {
    type: left_outer
    relationship: many_to_one
    sql_on: ${order_fact.customer_key} = ${customer_dim.customer_key} ;;
  }
}
