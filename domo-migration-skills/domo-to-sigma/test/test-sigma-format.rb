#!/usr/bin/env ruby
# sigma_format must emit the released Sigma d3 formatString shape.
#   ruby test/test-sigma-format.rb

require_relative '../scripts/lib/domo_sigma_util'
include DomoSigma

f = sigma_format({'type'=>'NUMBER','precision'=>0}, 'Days Using')
raise "got #{f.inspect}" unless f == {'kind'=>'number','formatString'=>',.0f'}
f2 = sigma_format({'type'=>'DECIMAL','decimals'=>2}, 'Years in Domo')
raise "got #{f2.inspect}" unless f2['formatString']==',.2f'
percent = sigma_format({'type'=>'percent','format'=>'0.0 %'}, 'Open Rate')
raise "got #{percent.inspect}" unless percent['formatString']==',.1%'
currency = sigma_format({'type'=>'currency','format'=>'$###,###','precision'=>0}, 'Revenue')
raise "got #{currency.inspect}" unless currency['formatString']=='$,.0f'
abbrev = sigma_format({'type'=>'abbreviated','format'=>'$0.0'}, 'Sales this Period')
raise "got #{abbrev.inspect}" unless abbrev['formatString']=='$.4~s'
puts 'test-sigma-format: PASS'
