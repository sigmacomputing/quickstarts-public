# frozen_string_literal: true
#
# redact.rb — credential masking for anything that ECHOES configuration.
#
# Contract (refs/operating-contract.md, "Credential hygiene"): NEVER echo
# credential values (tokens, secrets, PATs) into output, commands, or files —
# reference env var names only. When displaying config, mask all but the last
# 4 characters. This lib is the one place that masking lives so every echo
# path (setup.rb summaries, doctor readouts, logs) masks the same way.

module Redact
  module_function

  # Env-var NAMES whose values are credentials. \b-less on purpose: matches
  # SIGMA_CLIENT_SECRET, SIGMA_API_TOKEN, TABLEAU_PAT_SECRET, *_PASSWORD — but
  # NOT PATH/CLASSPATH (PAT must be a full underscore-delimited segment).
  SENSITIVE_ENV = /SECRET|TOKEN|PASSWORD|(\A|_)PAT(\z|_)/.freeze

  # Mask a single credential value, keeping only the last 4 characters:
  #   'sk-abcdef123456' -> '****3456'. Short values mask entirely.
  def mask(value)
    v = value.to_s
    return '(unset)' if v.empty?
    return '****' if v.length <= 4
    "****#{v[-4..-1]}"
  end

  # Scrub free text: any value of a sensitive env var (per SENSITIVE_ENV) that
  # appears verbatim in TEXT is replaced with its mask. Values shorter than 6
  # chars are skipped (too collision-prone to substitute safely).
  def scrub(text)
    out = text.to_s.dup
    ENV.each do |k, v|
      next if v.to_s.length < 6
      next unless k.to_s =~ SENSITIVE_ENV
      out = out.gsub(v, mask(v))
    end
    out
  end
end
