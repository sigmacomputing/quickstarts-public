#!/usr/bin/env ruby
# Store MicroStrategy credentials so any coding agent can load them:
#   - ~/.claude/settings.json   — Claude Code auto-loads this into the env
#   - ~/.sigma-migration/env    — neutral, sourceable file every other agent uses
# MicroStrategy uses session-based auth (POST /api/auth/login, loginMode 1) — there
# is no API-key concept; scripts/mstr.py reads these env vars to authenticate.

require 'io/console'
require 'json'
require 'fileutils'

SETTINGS_PATH = File.expand_path("~/.claude/settings.json")
NEUTRAL_PATH  = File.expand_path("~/.sigma-migration/env")

# Upsert `export KEY='value'` lines into the neutral cred file (0600), preserving
# any other vars already there (e.g. Sigma creds from setup.rb).
def upsert_neutral_env(pairs)
  FileUtils.mkdir_p(File.dirname(NEUTRAL_PATH), mode: 0o700)
  body = File.exist?(NEUTRAL_PATH) ? File.read(NEUTRAL_PATH) : ""
  pairs.each do |k, v|
    line = "export #{k}='#{v}'"
    if body =~ /^export #{Regexp.escape(k)}=.*$/
      body = body.sub(/^export #{Regexp.escape(k)}=.*$/, line)
    else
      body += "\n" unless body.empty? || body.end_with?("\n")
      body += line + "\n"
    end
  end
  File.write(NEUTRAL_PATH, body)
  File.chmod(0o600, NEUTRAL_PATH)
end

puts "MicroStrategy credential setup"
puts "Values are stored in #{SETTINGS_PATH} and loaded automatically into every Claude Code session."
puts

print "Library URL (e.g. https://<host>/MicroStrategyLibrary): "
base = $stdin.gets.chomp
base = base.sub(%r{/+$}, '')

print "Username: "
username = $stdin.gets.chomp

print "Password (will be hidden): "
password = $stdin.noecho(&:gets).chomp
puts

print "Project ID (optional — Enter to default to the first project): "
project_id = $stdin.gets.chomp

if [base, username, password].any?(&:empty?)
  abort "Library URL, Username, and Password are all required. Aborting without writing settings."
end

settings = File.exist?(SETTINGS_PATH) ? JSON.parse(File.read(SETTINGS_PATH)) : {}
settings["env"] ||= {}
settings["env"]["MSTR_BASE_URL"] = base
settings["env"]["MSTR_USERNAME"] = username
settings["env"]["MSTR_PASSWORD"] = password
settings["env"]["MSTR_PROJECT_ID"] = project_id unless project_id.empty?

File.write(SETTINGS_PATH, JSON.pretty_generate(settings))

pairs = {
  "MSTR_BASE_URL" => base,
  "MSTR_USERNAME" => username,
  "MSTR_PASSWORD" => password,
}
pairs["MSTR_PROJECT_ID"] = project_id unless project_id.empty?
upsert_neutral_env(pairs)

puts "Wrote MicroStrategy credentials to:"
puts "  #{SETTINGS_PATH}  (Claude Code auto-loads this)"
puts "  #{NEUTRAL_PATH}  (any other agent / shell)"
puts
puts "Claude Code: open a new session (or `! source ~/.claude/settings.json`)."
puts "Other agents / shell: `source ~/.sigma-migration/env`, then run"
puts "`python3 scripts/mstr.py` to verify the login probe."
