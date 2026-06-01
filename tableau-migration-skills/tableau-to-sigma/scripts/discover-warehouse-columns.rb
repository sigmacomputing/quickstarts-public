#!/usr/bin/env ruby
# Fetch warehouse column metadata for one or more table inodeIds in parallel.
# Encapsulates the "response key is `entries`, not `columns`" gotcha and the
# Sigma auth refresh.
#
# Usage:
#   ruby discover-warehouse-columns.rb <out-dir> <inodeId> [<inodeId> ...]

require 'net/http'
require 'uri'
require 'json'
require 'fileutils'

OUT_DIR = ARGV.shift || abort('usage: discover-warehouse-columns.rb <out-dir> <inodeId>+')
INODES  = ARGV
abort 'no inodeIds given' if INODES.empty?

BASE = ENV.fetch('SIGMA_BASE_URL')
$LOAD_PATH.unshift File.expand_path('lib', __dir__)
require 'sigma_rest'
FileUtils.mkdir_p(OUT_DIR)

# Fans out to N inodes in parallel; Sigma.request handles 401-refresh
# (single-flight mutex so threads don't all refresh at once).
def get(path)
  Sigma.request(:get, path, accept: '*/*')
end

threads = INODES.map do |inode|
  Thread.new do
    raw  = get("/v2/connections/tables/#{inode}/columns")
    body = JSON.parse(raw)
    cols = body['entries'] || []   # API gotcha: entries, not columns
    File.write("#{OUT_DIR}/#{inode}.json", JSON.pretty_generate(cols))
    [inode, cols.size]
  end
end

threads.each(&:join).map(&:value).each do |inode, n|
  puts "  #{inode}: #{n} columns"
end
