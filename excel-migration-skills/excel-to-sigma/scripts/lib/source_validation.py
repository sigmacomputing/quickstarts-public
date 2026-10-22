"""Version 2 source validation declaration, without invented Excel route behavior.

The base SpreadsheetML namespace defaults are unverified here. Attribute
omission therefore remains distinct from an explicitly authored false value.
"""
from __future__ import annotations

import hashlib
import json
import posixpath
import re
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zipfile import ZipFile

POLICY_VERSION = 2
MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
DOC_REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG_REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
POLICY = {
    'version': POLICY_VERSION,
    'baseNamespace': MAIN,
    'baseNamespaceDefaults': 'UNVERIFIED',
    'reviewedOn': '2026-10-20',
    'primaryDocsAccessedOn': '2026-10-20',
    'declaredNumericInterpretation': 'Microsoft Press Excel Expert Objective 2.2 step 5: unchecked blank is evaluated against numeric validation as zero; source route/storage are unverified',
    'sources': [
        {'section': 'Objective 2.2, validation setup step 5', 'url': 'https://www.microsoftpressstore.com/articles/article.aspx?p=2999393&seqNum=2'},
        {'section': 'Validation.IgnoreBlank', 'url': 'https://learn.microsoft.com/en-us/office/vba/api/excel.validation.ignoreblank'},
        {'section': 'DataValidation / ISO IEC base description', 'url': 'https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.spreadsheet.datavalidation?view=openxml-2.20.0'},
        {'section': 'MS-XLSX 2.6.5, extension namespace only', 'url': 'https://learn.microsoft.com/en-us/openspecs/office_standards/ms-xlsx/89029dfc-1ca8-4ff9-afe0-46f9454d09c6'},
        {'section': 'More on data validation', 'url': 'https://support.microsoft.com/en-gb/excel/more-on-data-validation?nochrome=true'},
        {'section': 'Display or hide circles around invalid data', 'url': 'https://support.microsoft.com/en-gb/excel/display-or-hide-circles-around-invalid-data'},
        {'section': 'ECMA-376 publication; base XSD archive unavailable to review', 'url': 'https://ecma-international.org/publications-and-standards/standards/ecma-376/'},
    ],
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


POLICY_HASH = digest(POLICY)


def _literal_number(value):
    if not isinstance(value, str) or not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', value.strip()):
        return None
    try:
        result = Decimal(value.strip())
    except InvalidOperation:
        return None
    return result if result.is_finite() else None


def classify_blank(rule):
    """Classify declared membership only; never claim Save/Delete behavior."""
    raw = (rule.get('rawAttributes') or {}).get('allowBlank') or {}
    if raw.get('present') is True and raw.get('value') in ('1', 'true', 'True'):
        return 'ALLOW_BLANK'
    if raw.get('present') is True and raw.get('value') not in ('0', 'false', 'False'):
        return 'UNRESOLVED'
    if rule.get('sourceType') not in ('decimal', 'whole'):
        return 'UNRESOLVED'
    low, high = (_literal_number(rule.get('formula1')), _literal_number(rule.get('formula2')))
    if low is None:
        return 'UNRESOLVED'
    kind = rule.get('sourceType')
    if kind == 'whole' and low != low.to_integral_value():
        return 'UNRESOLVED'
    operator = rule.get('operator')
    zero = Decimal(0)
    if operator in ('between', 'notBetween'):
        if high is None or (kind == 'whole' and high != high.to_integral_value()) or low > high:
            return 'UNRESOLVED'
        member = low <= zero <= high
        if operator == 'notBetween':
            member = not member
    elif operator in ('equal', 'notEqual', 'lessThan', 'lessThanOrEqual', 'greaterThan', 'greaterThanOrEqual'):
        member = {'equal': zero == low, 'notEqual': zero != low, 'lessThan': zero < low,
                  'lessThanOrEqual': zero <= low, 'greaterThan': zero > low,
                  'greaterThanOrEqual': zero >= low}[operator]
    else:
        return 'UNRESOLVED'
    return 'SATISFIES_NUMERIC_RULE_AS_ZERO' if member else 'VIOLATES_NUMERIC_RULE_AS_ZERO'


def read_raw_validations(source_path):
    """Read authored validation XML and retain exact part/namespace/attributes."""
    source = Path(source_path)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    with ZipFile(source) as archive:
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        rels = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        targets = {r.attrib['Id']: r.attrib['Target'] for r in rels.findall(f'{{{PKG_REL}}}Relationship')}
        rows = []
        for sheet in workbook.findall(f'.//{{{MAIN}}}sheet'):
            target = targets[sheet.attrib[f'{{{DOC_REL}}}id']]
            part = posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join('xl', target))
            root = ET.fromstring(archive.read(part))
            for element in root.findall(f'.//{{{MAIN}}}dataValidation'):
                attributes = dict(element.attrib)
                raw = {name: {'present': name in attributes, 'value': attributes.get(name)}
                       for name in ('allowBlank', 'showErrorMessage', 'errorStyle')}
                record = {'sheet': sheet.attrib['name'], 'sheetPart': part, 'namespace': MAIN,
                          'xmlAttributes': attributes, 'rawAttributes': raw,
                          'sourceType': attributes.get('type'), 'operator': attributes.get('operator'),
                          'range': attributes.get('sqref'),
                          'formula1': element.findtext(f'{{{MAIN}}}formula1'),
                          'formula2': element.findtext(f'{{{MAIN}}}formula2'),
                          'sourceRuleXml': ET.tostring(element, encoding='unicode'),
                          'sourceHash': source_hash}
                record['ruleHash'] = digest(record)
                rows.append(record)
    return rows
