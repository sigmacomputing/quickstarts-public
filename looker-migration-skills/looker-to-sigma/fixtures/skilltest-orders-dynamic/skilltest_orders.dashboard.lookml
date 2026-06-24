- dashboard: skilltest_looker_orders_pulse
  title: SKILLTEST Looker Orders Pulse
  layout: newspaper
  preferred_viewer: dashboards-next

  filters:
  - name: Region
    title: Region
    type: field_filter
    model: skilltest_orders
    explore: order_fact
    field: customer_dim.region
    allow_multiple_values: true

  - name: Order Channel
    title: Order Channel
    type: field_filter
    model: skilltest_orders
    explore: order_fact
    field: order_fact.order_channel
    allow_multiple_values: true

  - name: First Order Date
    title: First Order Date
    type: date_filter
    model: skilltest_orders
    explore: order_fact
    field: customer_dim.first_order

  elements:
  - name: Total Net Revenue
    title: Total Net Revenue
    model: skilltest_orders
    explore: order_fact
    type: single_value
    fields: [order_fact.total_net_revenue]
    listen:
      Region: customer_dim.region
      Order Channel: order_fact.order_channel
      First Order Date: customer_dim.first_order_date
    row: 0
    col: 0
    width: 8
    height: 4

  - name: Order Count
    title: Order Count
    model: skilltest_orders
    explore: order_fact
    type: single_value
    fields: [order_fact.order_count]
    listen:
      Region: customer_dim.region
      Order Channel: order_fact.order_channel
      First Order Date: customer_dim.first_order_date
    row: 0
    col: 8
    width: 8
    height: 4

  - name: Average Order Value
    title: Average Order Value
    model: skilltest_orders
    explore: order_fact
    type: single_value
    fields: [order_fact.average_order_value]
    listen:
      Region: customer_dim.region
      Order Channel: order_fact.order_channel
      First Order Date: customer_dim.first_order_date
    row: 0
    col: 16
    width: 8
    height: 4

  - name: Net Revenue by Region
    title: Net Revenue by Region
    model: skilltest_orders
    explore: order_fact
    type: looker_column
    fields: [customer_dim.region, order_fact.total_net_revenue]
    sorts: [order_fact.total_net_revenue desc]
    limit: 500
    listen:
      Order Channel: order_fact.order_channel
    row: 4
    col: 0
    width: 12
    height: 8

  - name: Orders by Ship Method
    title: Orders by Ship Method
    model: skilltest_orders
    explore: order_fact
    type: looker_pie
    fields: [order_fact.ship_method, order_fact.order_count]
    sorts: [order_fact.order_count desc]
    limit: 500
    listen:
      Region: customer_dim.region
    row: 4
    col: 12
    width: 12
    height: 8

  - name: Channel Summary
    title: Channel Summary
    model: skilltest_orders
    explore: order_fact
    type: table
    fields: [order_fact.order_channel, order_fact.order_count, order_fact.total_net_revenue, order_fact.average_order_value]
    sorts: [order_fact.total_net_revenue desc]
    filters:
      order_fact.order_status: "Complete,Returned"
    listen:
      Region: customer_dim.region
    row: 12
    col: 0
    width: 24
    height: 8
