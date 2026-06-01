#!/usr/bin/env ruby
# Store Tableau credentials in ~/.claude/settings.json so Claude Code loads them automatically.
# Use this when the Tableau MCP isn't available (or when the workbook has an embedded
# datasource that the MCP can't see). See refs/tableau-rest.md.

require 'io/console'
require 'json'

SETTINGS_PATH = File.expand_path("~/.claude/settings.json")

puts "Tableau credential setup"
puts "Values are stored in #{SETTINGS_PATH} and loaded automatically into every Claude Code session."
puts

print "Server URL [https://10ay.online.tableau.com]: "
server = $stdin.gets.chomp
server = "https://10ay.online.tableau.com" if server.empty?
server = server.sub(%r{/+$}, '')

print "Site contentUrl (the path segment after /site/ in the Tableau URL, e.g. 'dataflow'): "
content_url = $stdin.gets.chomp

print "PAT name (the label you typed when creating the token in Tableau): "
pat_name = $stdin.gets.chomp

print "PAT secret (will be hidden): "
pat_secret = $stdin.noecho(&:gets).chomp
puts

if [server, content_url, pat_name, pat_secret].any?(&:empty?)
  abort "All four values are required. Aborting without writing settings."
end

settings = File.exist?(SETTINGS_PATH) ? JSON.parse(File.read(SETTINGS_PATH)) : {}
settings["env"] ||= {}
settings["env"]["TABLEAU_SERVER_URL"]        = server
settings["env"]["TABLEAU_SITE_CONTENT_URL"]  = content_url
settings["env"]["TABLEAU_PAT_NAME"]          = pat_name
settings["env"]["TABLEAU_PAT_SECRET"]        = pat_secret

File.write(SETTINGS_PATH, JSON.pretty_generate(settings))
puts "Wrote Tableau credentials to #{SETTINGS_PATH}."
puts
puts "Open a new Claude Code session (or `! source ~/.claude/settings.json`) so the env vars are live."
