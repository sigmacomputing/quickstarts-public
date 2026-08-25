# frozen_string_literal: true
#
# cli_encoding.rb — G3: UTF-8 bootstrap for CLI entry points (system Ruby 2.6).
#
# Field failure, BOTH field-workbook runs (3 crashes total): under an unset/C
# locale, Ruby 2.6 tags ARGV strings ASCII-8BIT; the first em-dash ("—", \xE2…)
# in an agent-authored --notes/--name then raises
# Encoding::UndefinedConversionError inside JSON.generate (pick-destination.rb
# cmd_create, record-visual-check.rb) and costs a retry. Any script that
# round-trips agent-authored prose through JSON must `require_relative
# 'lib/cli_encoding'` before parsing options.
Encoding.default_external = Encoding::UTF_8
Encoding.default_internal = Encoding::UTF_8
ARGV.each do |a|
  next unless a.is_a?(String) && a.encoding == Encoding::ASCII_8BIT
  a.force_encoding(Encoding::UTF_8)
  a.scrub!('') unless a.valid_encoding?
end
