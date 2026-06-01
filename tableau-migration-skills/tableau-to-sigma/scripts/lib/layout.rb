# Layout-XML helpers. require'd by per-workbook layout configs.
module SigmaLayout
  module_function

  def gc(eid, c0, c1, r0, r1, inner)
    "<GridContainer elementId=\"#{eid}\" type=\"grid\" " \
    "gridColumn=\"#{c0} / #{c1}\" gridRow=\"#{r0} / #{r1}\" " \
    "gridTemplateColumns=\"repeat(24, 1fr)\" gridTemplateRows=\"auto\">\n#{inner}\n</GridContainer>"
  end

  def le(eid, c0, c1, r0, r1)
    "  <LayoutElement elementId=\"#{eid}\" gridColumn=\"#{c0} / #{c1}\" gridRow=\"#{r0} / #{r1}\"/>"
  end

  def page_xml(page_id, *children)
    header = "<Page type=\"grid\" gridTemplateColumns=\"repeat(24, 1fr)\" gridTemplateRows=\"auto\" id=\"#{page_id}\">"
    [header, *children.compact, "</Page>"].join("\n")
  end

  def assemble(*pages)
    %(<?xml version="1.0" encoding="utf-8"?>\n) + pages.join("\n")
  end
end
