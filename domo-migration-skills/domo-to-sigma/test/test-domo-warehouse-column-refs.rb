#!/usr/bin/env ruby
# frozen_string_literal: true

require_relative '../scripts/lib/domo_warehouse_column_refs'

spec = { 'pages' => [{ 'elements' => [{
  'name' => 'Transactions',
  'source' => { 'kind' => 'warehouse-table', 'connectionId' => 'conn', 'path' => %w[DB S TRANSACTIONS] },
  'columns' => [{ 'id' => 'inode-x/TXN_ID', 'formula' => '[TRANSACTIONS/Txn Id]' },
                { 'id' => 'calc', 'formula' => 'Text([Transactions/Txn Id])', 'name' => 'Txn Text' }]
}, { 'name' => 'Transactions View', 'source' => { 'kind' => 'table', 'elementId' => 'base' },
     'columns' => [{ 'id' => 'pass', 'formula' => '[Transactions/Txn Id]' }] }] }] }
requester = ->(method, _path, **_kwargs) { method == :get ? { 'friendlyName' => false } : { 'kind' => 'table', 'inodeId' => 't' } }
result = DomoWarehouseColumnRefs.apply!(spec, requester: requester, lister: ->(_path) { [{ 'name' => 'TXN_ID' }] })
base, view = spec['pages'][0]['elements']
raise unless base['name'] == 'TRANSACTIONS'
raise unless base['columns'][0] == { 'id' => 'inode-x/TXN_ID', 'formula' => '[TRANSACTIONS/TXN_ID]', 'name' => 'Txn Id' }
raise unless base['columns'][1]['formula'] == 'Text([TRANSACTIONS/TXN_ID])'
raise unless view['columns'][0] == { 'id' => 'pass', 'formula' => '[TRANSACTIONS/Txn Id]', 'name' => 'Txn Id' }
raise unless result[:connection_modes] == { 'conn' => false }
puts 'test-domo-warehouse-column-refs: PASS'
