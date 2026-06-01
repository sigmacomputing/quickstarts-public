#!/usr/bin/env ruby
# Phase 2: Fetch the site-wide Tableau Metadata API graph.
# One GraphQL call to /api/metadata/graphql returns the cross-cutting structure
# (publishedDatasources, embedded datasources per workbook, customSQLTables, flows)
# with connection hostnames for true on-prem vs cloud classification.
#
# Usage:
#   ruby scripts/fetch-metadata-graph.rb --out /tmp/assessment-<site>

require 'json'
require 'optparse'
$LOAD_PATH.unshift File.expand_path('../../tableau-to-sigma/scripts/lib', __dir__)
require 'tableau_rest'

opts = {}
OptionParser.new do |p|
  p.on('--out DIR') { |v| opts[:out] = v }
end.parse!
abort('--out required') unless opts[:out]

QUERY = <<~GRAPHQL
  {
    publishedDatasources {
      luid id name hasExtracts isCertified extractLastUpdateTime
      upstreamTables { name schema fullName }
      upstreamDatabases {
        name connectionType
        ... on DatabaseServer { hostName port }
      }
      downstreamWorkbooks { luid name }
      fields { name }
    }
    workbooks {
      luid id name
      embeddedDatasources {
        id name hasExtracts
        upstreamTables { name schema fullName }
        upstreamDatabases {
          name connectionType
          ... on DatabaseServer { hostName port }
        }
        fields {
          __typename name
          ... on CalculatedField {
            formula isHidden role dataType aggregation
          }
        }
      }
    }
    customSQLTables {
      name query
      downstreamWorkbooks { luid name }
      downstreamDatasources { name }
      database {
        name connectionType
        ... on DatabaseServer { hostName }
      }
    }
    flows {
      luid id name
      upstreamDatabases {
        name connectionType
        ... on DatabaseServer { hostName }
      }
      downstreamWorkbooks { luid name }
      downstreamDatasources { name }
    }
  }
GRAPHQL

warn 'Querying /api/metadata/graphql ...'
resp = Tableau.graphql(QUERY)
if resp['errors']
  warn 'GraphQL errors:'
  warn JSON.pretty_generate(resp['errors'])
  exit 1
end

out_path = File.join(opts[:out], 'metadata-graph.json')
File.write(out_path, JSON.pretty_generate(resp['data']))
puts "wrote #{out_path} (#{File.size(out_path)} bytes)"

data = resp['data']
puts "  publishedDatasources: #{(data['publishedDatasources'] || []).size}"
puts "  workbooks:            #{(data['workbooks'] || []).size}"
puts "  customSQLTables:      #{(data['customSQLTables'] || []).size}"
puts "  flows:                #{(data['flows'] || []).size}"
