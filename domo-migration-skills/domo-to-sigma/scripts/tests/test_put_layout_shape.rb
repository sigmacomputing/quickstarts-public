# frozen_string_literal: true
#
# test_put_layout_shape.rb — regression test for the workbook code-rep
# document-wrapper fix (Task 3.7). put-layout.rb is the mandatory "apply
# layout" step named in assert-phase6-ran.rb gate 4's own fix-it message.
# Every copy did `spec = JSON.parse(GET .../spec)` then `spec['pages'].each`
# then PUT — since the live API now nests non-metadata fields under a
# top-level `document` key, `spec['pages']` is nil and iterating over it
# raised NoMethodError immediately, crashing the tool on every run.
#
# Run: ruby scripts/tests/test_put_layout_shape.rb

require 'minitest/autorun'
require_relative '../lib/code_rep'

class TestPutLayoutShape < Minitest::Test
  NESTED = { 'workbookId' => 'w', 'document' => { 'pages' => [{ 'id' => 'p' }], 'layout' => nil } }

  def test_pages_iteration_does_not_raise_on_nested_readback
    # The bug: NESTED['pages'] is nil -> nil.each -> NoMethodError.
    assert_nil NESTED['pages'], 'proves the crash precondition'
    assert_equal [{ 'id' => 'p' }], Sigma::CodeRep.document(NESTED)['pages']
    Sigma::CodeRep.document(NESTED)['pages'].each { |p| assert p['id'] }   # must not raise
  end

  def test_put_body_is_wrapped
    doc = { 'pages' => [], 'layout' => '<Layout/>' }
    assert_equal doc.merge('elements' => []), Sigma::CodeRep.wrap(doc)['document']
  end

  # Real regression signal: the two tests above only prove the already-shipped
  # shared adapter behaves as documented. This checks that put-layout.rb
  # itself actually calls it — not a flat spec['pages'] / JSON.pretty_generate
  # (spec) body, which is the actual bug this task fixes.
  def test_script_reads_via_code_rep_document
    src = File.read(File.join(__dir__, '..', 'put-layout.rb'))
    assert_match(/Sigma::CodeRep\.document\(/, src,
                 'put-layout.rb must unwrap the GET response via Sigma::CodeRep.document')
  end

  def test_script_writes_via_code_rep_wrap
    src = File.read(File.join(__dir__, '..', 'put-layout.rb'))
    assert_match(/Sigma::CodeRep\.wrap\(/, src,
                 'put-layout.rb must wrap the PUT body via Sigma::CodeRep.wrap')
    assert_match(/spec\['elements'\]\s*<<\s*el/, src,
                 'layout sidecar elements must join document.elements')
    refute_match(/page\['elements'\]\s*<<\s*el/, src,
                 'metadata-only pages must never regain nested elements')
    assert_match(/layout must place every flat workbook element exactly once/, src,
                 'layout PUT must fail closed on missing or duplicate placements')
  end

  # Ordering: the document() unwrap must happen before the PUT, and the
  # wrap() must happen at (or immediately before) the PUT call — so
  # verify_spec!/http(:put, ...) can never be handed the still-flat spec.
  def test_unwrap_precedes_put_and_wrap_precedes_put
    src   = File.read(File.join(__dir__, '..', 'put-layout.rb'))
    lines = src.lines
    doc_idx  = lines.find_index { |l| l =~ /Sigma::CodeRep\.document\(/ }
    wrap_idx = lines.find_index { |l| l =~ /Sigma::CodeRep\.wrap\(/ }
    put_idx  = lines.find_index { |l| l =~ /http\(:put,/ }
    refute_nil doc_idx,  'expected a Sigma::CodeRep.document( call'
    refute_nil wrap_idx, 'expected a Sigma::CodeRep.wrap( call'
    refute_nil put_idx,  'expected an http(:put, ...) call'
    assert doc_idx < put_idx,  'the GET must be unwrapped before the PUT is issued'
    assert wrap_idx <= put_idx, 'the PUT body must be wrapped at or before the PUT call'
  end
end
