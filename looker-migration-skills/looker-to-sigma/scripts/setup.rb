#!/usr/bin/env ruby
# Store Sigma credentials in ~/.claude/settings.json so Claude Code loads them automatically.

require 'io/console'
require 'json'

SETTINGS_PATH = File.expand_path("~/.claude/settings.json")

puts "Sigma credential setup"
puts "Values are stored in #{SETTINGS_PATH} and loaded automatically into every Claude Code session."
puts

print "Base URL [https://aws-api.sigmacomputing.com]: "
base = $stdin.gets.chomp
base = "https://aws-api.sigmacomputing.com" if base.empty?

print "Client ID (not a secret — will echo): "
cid = $stdin.gets.chomp

print "Client Secret (hidden): "
sec = $stdin.noecho(&:gets).chomp
puts

if [base, cid, sec].any?(&:empty?)
  abort "Base URL, Client ID, and Client Secret are all required. Aborting without writing settings."
end

settings = File.exist?(SETTINGS_PATH) ? JSON.parse(File.read(SETTINGS_PATH)) : {}
settings["env"] ||= {}
settings["env"]["SIGMA_BASE_URL"]      = base
settings["env"]["SIGMA_CLIENT_ID"]     = cid
settings["env"]["SIGMA_CLIENT_SECRET"] = sec

File.write(SETTINGS_PATH, JSON.pretty_generate(settings))

redacted_secret = sec.length > 8 ? "#{sec[0..3]}…#{sec[-4..]} (#{sec.length} chars)" : "(#{sec.length} chars)"

puts
puts "Saved to #{SETTINGS_PATH}:"
puts "  SIGMA_BASE_URL:      #{base}"
puts "  SIGMA_CLIENT_ID:     #{cid}"
puts "  SIGMA_CLIENT_SECRET: #{redacted_secret}"
puts
puts "If the Client ID above looks like a URL or doesn't match what Sigma showed you, re-run this script."
puts "Open a new Claude Code session (or run `! source ~/.claude/settings.json`) to pick them up."
