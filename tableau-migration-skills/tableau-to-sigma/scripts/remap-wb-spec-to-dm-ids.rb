#!/usr/bin/env ruby
# Remap a workbook spec when its source DM has been re-POSTed and its element
# IDs reassigned.
#
# DM POST always reassigns element IDs (e.g. cached wb-spec.json pointed at
# `FImeSBgSl0` / `3hCjK_4LhH` / `cF1Lt3SDQE`, new DM POST gave
# `24QkBSa9Ah` / `TjMEUs0GNz` / `wNAZXRnagL`). The workbook spec must be
# rewritten to point at the new IDs in TWO places per master:
#   1. master element `source.elementId` (the DM element ID)
#   2. ALL master-column formulas: `[OldDMElementName/COL]` references — but
#      the element NAMES survive POST, so this is usually fine. If you ALSO
#      renamed elements, pass --rename old=new (repeatable).
#
# Inputs:
#   --wb-spec /tmp/<name>/wb-spec.json
#   --old-dm-ids /tmp/<name>/wb-ids.json         # readback from PRIOR DM POST
#   --new-dm-ids /tmp/<name>/dm-ids.json         # readback from CURRENT DM POST
#   [--rename "Old Name=New Name"]               # element-name remap, repeatable
#   --out /tmp/<name>/wb-spec.remapped.json
#
# The id-map files are the per-DM output of post-and-readback.rb:
#   { "dataModelId": "...", "pages": [{ "id", "name", "elements": [{id, kind, name}, ...] }] }
#
# Mapping is by element NAME (stable across POSTs). If a name is renamed,
# pass --rename to map old name → new name explicitly.

require 'json'
require 'optparse'

opts = { renames: {} }
OptionParser.new do |p|
  p.on('--wb-spec PATH')      { |v| opts[:spec] = v }
  p.on('--old-dm-ids PATH')   { |v| opts[:old]  = v }
  p.on('--new-dm-ids PATH')   { |v| opts[:new]  = v }
  p.on('--rename PAIR')       { |v| from, to = v.split('=', 2); opts[:renames][from] = to }
  p.on('--out PATH')          { |v| opts[:out]  = v }
end.parse!
%i[spec old new out].each { |k| abort "missing --#{k.to_s.gsub('_','-')}" unless opts[k] }

def read_id_map(path)
  raw = JSON.parse(File.read(path))
  els = (raw['pages'] || []).flat_map { |p| (p['elements'] || []) }
  by_name = els.each_with_object({}) { |e, h| h[e['name']] = e['id'] if e['name'] && e['id'] }
  [by_name, raw['dataModelId']]
end

old_by_name, old_dm_id = read_id_map(opts[:old])
new_by_name, new_dm_id = read_id_map(opts[:new])
abort 'new dm-ids file missing top-level dataModelId' unless new_dm_id

# Build old-id → new-id map. For each element in the OLD map, find its name,
# apply rename if present, look up in NEW map.
id_remap = {}
old_by_name.each do |old_name, old_id|
  new_name = opts[:renames][old_name] || old_name
  new_id = new_by_name[new_name]
  if new_id
    id_remap[old_id] = new_id
    warn "remap: #{old_name.inspect} #{old_id} → #{new_id}"
  else
    warn "WARN: no new ID for #{old_name.inspect} (old #{old_id}); pass --rename if it was renamed"
  end
end
abort 'no remappings produced — check id-map files' if id_remap.empty?

spec = JSON.parse(File.read(opts[:spec]))

# 1. Rewrite master-element `source.elementId` AND `source.dataModelId`.
#    DM re-POST reassigns BOTH the dataModelId (new DM created) and the
#    element IDs inside it. Missing the dataModelId rewrite leaves orphan
#    references that POST 4xx with "data model not found".
n_src = 0
n_dm  = 0
(spec['pages'] || []).each do |pg|
  (pg['elements'] || []).each do |el|
    src = el['source']
    next unless src.is_a?(Hash)
    if (eid = src['elementId']) && id_remap.key?(eid)
      src['elementId'] = id_remap[eid]
      n_src += 1
    end
    if (dm = src['dataModelId']) && (dm == old_dm_id || id_remap.values.include?(src['elementId']))
      if src['dataModelId'] != new_dm_id
        src['dataModelId'] = new_dm_id
        n_dm += 1
      end
    end
  end
end

# 2. Rewrite formula references that use element NAMES if a rename was passed.
#    `[OldName/Col]` → `[NewName/Col]`. Only walks the renames map — leaves
#    untouched names alone (no risk of mass-rewrite false positives).
n_formula = 0
if opts[:renames].any?
  walk = lambda do |obj|
    case obj
    when Hash  then obj.each { |k, v| obj[k] = walk.call(v) }; obj
    when Array then obj.map! { |x| walk.call(x) }
    when String
      out = obj.dup
      opts[:renames].each do |from, to|
        next if from == to
        before = out.dup
        out.gsub!(/\[#{Regexp.escape(from)}\//, "[#{to}/")
        n_formula += 1 if out != before
      end
      out
    else obj
    end
  end
  walk.call(spec)
end

File.write(opts[:out], JSON.pretty_generate(spec))
warn "rewrote #{n_src} source.elementId refs"
warn "rewrote #{n_dm} source.dataModelId refs (old #{old_dm_id || '(unset)'} → new #{new_dm_id})"
warn "rewrote #{n_formula} formula prefix refs" if opts[:renames].any?
warn "wrote #{opts[:out]}"
