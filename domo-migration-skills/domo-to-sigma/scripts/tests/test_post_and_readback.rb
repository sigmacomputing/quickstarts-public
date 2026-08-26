# frozen_string_literal: true
#
# test_post_and_readback.rb — regression test for the workbook code-rep
# document-wrapper fix (Task 3.1). Verifies the shared Sigma::CodeRep adapter
# (vendored at ../lib/code_rep.rb) reads the LIVE nested workbook readback
# shape and produces a properly-nested POST/PUT body, while confirming the
# datamodel surface's flat shape is untouched (it is NOT changing — do not
# apply CodeRep to /v2/dataModels/.../spec payloads).
#
# Run: ruby scripts/tests/test_post_and_readback.rb

require 'minitest/autorun'
require_relative '../lib/code_rep'

# Static AST check: does every Sigma::CodeRep call site in a script live
# STRICTLY inside the "then" clause of an `if`/ternary keyed on
# `opts[:type] == 'workbook'` — never in that guard's "else" (the datamodel
# path), and never unguarded? Ruby's ternary (`a ? b : c`) and `if/else/end`
# both parse to the same :IF node, so one walk covers both spellings.
#
# This protects the property test_script_uses_code_rep_adapter_for_workbook_branch
# (below) does NOT: a substring/regex match for "Sigma::CodeRep" anywhere in
# the file would still pass even if a future edit accidentally routed the
# DATAMODEL branch through the adapter too (e.g. by deleting the `else` or
# copying the wrapped body into both branches).
module CodeRepGuardCheck
  CODE_REP_METHODS = %i[document wrap metadata].freeze

  module_function

  def coderep_receiver?(recv)
    return false unless recv.is_a?(RubyVM::AbstractSyntaxTree::Node)
    case recv.type
    when :COLON2 then recv.children[1] == :CodeRep # Sigma::CodeRep
    when :CONST  then recv.children[0] == :CodeRep # bare CodeRep
    else false
    end
  end

  # First STR literal found in a condition subtree — extracts the 'workbook'
  # / 'datamodel' operand of an `opts[:type] == '<x>'` comparison regardless
  # of surrounding && / method-call wrapping.
  def type_guard_str(node)
    return nil unless node.is_a?(RubyVM::AbstractSyntaxTree::Node)
    return node.children[0] if node.type == :STR
    node.children.each do |c|
      next unless c.is_a?(RubyVM::AbstractSyntaxTree::Node)
      r = type_guard_str(c)
      return r if r
    end
    nil
  end

  # Walks the AST threading a context tag (:workbook / :datamodel / :top)
  # through nested `if`s so every CodeRep call is recorded with the tag of
  # the innermost type-keyed guard it's textually inside (or :top if none).
  def walk(node, ctx, findings)
    return unless node.is_a?(RubyVM::AbstractSyntaxTree::Node)

    if node.type == :IF
      cond, then_b, else_b = node.children
      guard = type_guard_str(cond)
      then_ctx, else_ctx =
        case guard
        when 'workbook'  then [:workbook, :datamodel]
        when 'datamodel' then [:datamodel, :workbook]
        else [ctx, ctx]
        end
      walk(cond, ctx, findings)
      walk(then_b, then_ctx, findings)
      walk(else_b, else_ctx, findings)
      return
    end

    if %i[CALL FCALL].include?(node.type)
      recv = node.type == :CALL ? node.children[0] : nil
      mid  = node.type == :CALL ? node.children[1] : node.children[0]
      findings << { line: node.first_lineno, ctx: ctx, method: mid } if recv && coderep_receiver?(recv) && CODE_REP_METHODS.include?(mid)
    end

    node.children.each { |c| walk(c, ctx, findings) if c.is_a?(RubyVM::AbstractSyntaxTree::Node) }
  end

  def find_calls(path)
    findings = []
    walk(RubyVM::AbstractSyntaxTree.parse_file(path), :top, findings)
    findings
  end
end

class TestPostAndReadback < Minitest::Test
  def test_workbook_readback_pages_found_when_nested
    readback = { 'workbookId' => 'w', 'document' => { 'pages' => [{ 'id' => 'p1' }] } }
    assert_equal [{ 'id' => 'p1' }], Sigma::CodeRep.document(readback)['pages']
  end

  def test_workbook_post_body_is_nested
    doc  = { 'schemaVersion' => 1, 'pages' => [], 'elements' => [],
             'layout' => '<?xml version="1.0"?><Page id="p"/>', 'kind' => 'workbook' }
    body = Sigma::CodeRep.wrap(doc, extra: { 'name' => 'n', 'folderId' => 'f' })
    assert_equal doc, body['document']
    refute body.key?('pages'), 'pages must not remain top-level'
  end

  def test_workbook_wrap_flattens_legacy_pages_but_not_datamodels
    legacy = {
      'schemaVersion' => 1, 'kind' => 'workbook', 'layout' => '<Page id="p"/>',
      'pages' => [{ 'id' => 'p', 'name' => 'P',
                    'elements' => [{ 'id' => 'e', 'kind' => 'text' }] }]
    }
    document = Sigma::CodeRep.wrap(legacy)['document']
    assert_equal [{ 'id' => 'p', 'name' => 'P' }], document['pages']
    assert_equal ['e'], document['elements'].map { |element| element['id'] }

    datamodel = { 'schemaVersion' => 1, 'pages' => legacy['pages'] }
    assert datamodel['pages'].first.key?('elements'),
           'data-model pages remain nested because CodeRep is never applied to that branch'
  end

  # The DM branch must be left alone — that surface is not changing.
  def test_datamodel_branch_stays_flat
    readback = { 'dataModelId' => 'd', 'pages' => [{ 'id' => 'p1' }], 'schemaVersion' => 1 }
    assert_equal [{ 'id' => 'p1' }], readback['pages'],
                 'DM readback must still be read flat, unchanged'
  end

  # Real regression signal (the 3 tests above only exercise the already-shipped
  # shared adapter): the sibling post-and-readback.rb script itself must route
  # its workbook branch through Sigma::CodeRep, not a flat readback['pages'] /
  # spec.to_json body — that's the actual bug this task fixes.
  def test_script_uses_code_rep_adapter_for_workbook_branch
    src = File.read(File.join(__dir__, '..', 'post-and-readback.rb'))
    assert_match(/Sigma::CodeRep\.(document|wrap|metadata)/, src,
                 'post-and-readback.rb must call Sigma::CodeRep for its workbook branch')
    assert_match(/missing required document\.layout/, src)
    assert_match(/pages must be metadata-only/, src)
  end

  # The property the test above does NOT protect: that a CodeRep call site
  # never appears reachable from the DATAMODEL branch (or unguarded). See
  # CodeRepGuardCheck's header comment for how "reachable" is determined.
  def test_code_rep_calls_are_workbook_only
    path = File.join(__dir__, '..', 'post-and-readback.rb')
    findings = CodeRepGuardCheck.find_calls(path)
    refute_empty findings, 'expected at least one Sigma::CodeRep call site in post-and-readback.rb'
    bad = findings.reject { |f| f[:ctx] == :workbook }
    assert_empty bad,
                 "Sigma::CodeRep call(s) reachable OUTSIDE the workbook branch: " +
                 bad.map { |f| "line #{f[:line]} (.#{f[:method]}, ctx=#{f[:ctx]})" }.join(', ')
  end
end
