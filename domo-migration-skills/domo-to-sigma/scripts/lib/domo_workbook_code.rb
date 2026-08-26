# frozen_string_literal: true

require_relative 'code_rep'

module DomoSigma
  module WorkbookCode
    module_function

    # Domo still has committed page-nested fixtures, while live and newly built
    # workbook specs use the released document envelope with flat elements.
    # Normalize both shapes for Domo-owned validation without changing shared
    # parity tooling.
    def normalized_document(spec)
      Sigma::CodeRep.wrap(Sigma::CodeRep.document(spec))['document']
    end
  end
end
