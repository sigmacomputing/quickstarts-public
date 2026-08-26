# frozen_string_literal: true

require 'json'

module DomoWarehouseColumnRefs
  module_function

  def normalize(value)
    value.to_s.downcase.gsub(/[^a-z0-9]/, '')
  end

  def catalog_match(entries, candidates)
    names = entries.map { |entry| entry['name'].to_s }.reject(&:empty?)
    candidates.compact.map(&:to_s).reject(&:empty?).each do |candidate|
      return candidate if names.include?(candidate)
      folded = names.select { |name| name.casecmp(candidate).zero? }
      return folded.first if folded.one?
      normalized = names.select { |name| normalize(name) == normalize(candidate) }
      return normalized.first if normalized.one?
    end
    nil
  end

  def apply!(spec, requester:, lister:)
    modes = {}
    cache = {}
    aliases = {}
    prefixes = {}
    id_map = {}
    unresolved = []
    rewritten = rekeyed = reprefixed = 0
    elements = (spec['pages'] || []).flat_map { |page| page['elements'] || [] }

    elements.each do |element|
      source = element['source'] || {}
      next unless source['kind'] == 'warehouse-table'
      connection, path = source['connectionId'].to_s, source['path']
      next if connection.empty? || !path.is_a?(Array) || path.empty?
      friendly = modes.fetch(connection) do
        modes[connection] = requester.call(:get, "/v2/connections/#{connection}")['friendlyName']
      end
      raise "connection #{connection} did not report friendlyName" unless friendly == true || friendly == false
      next if friendly

      old_name, physical_name = element['name'].to_s, path.last.to_s
      aliases[old_name] = physical_name unless old_name.empty? || old_name == physical_name
      element['name'] = physical_name
      entries = cache.fetch([connection, path]) do
        table = requester.call(:post, "/v2/connection/#{connection}/lookup",
                               body: JSON.generate('path' => path))
        raise "#{path.join('.')} did not resolve to a table" unless table['kind'] == 'table' && table['inodeId']
        cache[[connection, path]] = lister.call("/v2/connections/tables/#{table['inodeId']}/columns")
      end
      refs = entries.each_with_object({}) { |entry, out| out[normalize(entry['name'])] = entry['name'].to_s }
      prefixes[old_name] = prefixes[physical_name] = true

      (element['columns'] || []).each do |column|
        match = column['formula'].to_s.match(%r{\A\[([^\]/]+)/([^\]/]+)\]\z})
        next unless match
        prefix, leaf = match.captures
        cid = column['id'].to_s
        id_leaf = cid.split('/', 2)[1]
        physical = catalog_match(entries, [leaf, column['name'], id_leaf])
        unless physical
          unresolved << "#{path.join('.')}: #{prefix}/#{leaf}" if cid.start_with?('inode-')
          next
        end
        column['name'] = leaf if column['name'].to_s.empty?
        if cid.start_with?('inode-') && id_leaf != physical
          new_id = "#{cid.split('/', 2)[0]}/#{physical}"
          id_map[cid] = new_id
          column['id'] = new_id
          rekeyed += 1
        end
        grounded = "[#{physical_name}/#{physical}]"
        unless column['formula'] == grounded
          column['formula'] = grounded
          rewritten += 1
        end
      end

      same = lambda do |node|
        case node
        when Hash
          display = nil
          if node['formula'].is_a?(String)
            node['formula'] = node['formula'].gsub(/\[([^\]\/]+)(\/[^\]]+)\]/) do
              prefix = Regexp.last_match(1)
              original = Regexp.last_match(0)
              leaf = Regexp.last_match(2)[1..]
              next original if leaf.include?('/') || ![old_name, physical_name].include?(prefix)
              physical = refs[normalize(leaf)]
              next original unless physical
              display ||= leaf
              grounded = "[#{physical_name}/#{physical}]"
              rewritten += 1 if grounded != original
              grounded
            end
          end
          node['name'] = display if display && node['name'].to_s.empty?
          node.each { |key, value| same.call(value) unless key == 'formula' }
        when Array then node.each { |value| same.call(value) }
        end
      end
      same.call(element)
    end

    replace_ids = lambda do |node|
      case node
      when Hash then node.each { |key, value| node[key] = replace_ids.call(value) }
      when Array then node.map! { |value| replace_ids.call(value) }
      when String then id_map.fetch(node, node)
      else node
      end
    end
    replace_ids.call(spec)

    derived = lambda do |node|
      case node
      when Hash
        display = nil
        if node['formula'].is_a?(String)
          node['formula'] = node['formula'].gsub(/\[([^\]\/]+)(\/[^\]]+)\]/) do
            prefix = Regexp.last_match(1)
            suffix = Regexp.last_match(2)
            replacement = aliases.fetch(prefix, prefix)
            reprefixed += 1 if replacement != prefix
            display ||= suffix[1..] if !suffix[1..].include?('/') && (prefixes[prefix] || prefixes[replacement])
            "[#{replacement}#{suffix}]"
          end
        end
        node['name'] = display if display && node['name'].to_s.empty?
        node.each { |key, value| derived.call(value) unless key == 'formula' }
      when Array then node.each { |value| derived.call(value) }
      end
    end
    derived.call(spec)
    raise "warehouse columns not found in catalog: #{unresolved.uniq.join(', ')}" if unresolved.any?
    { rewritten: rewritten, rekeyed: rekeyed, reprefixed: reprefixed, connection_modes: modes }
  end
end
