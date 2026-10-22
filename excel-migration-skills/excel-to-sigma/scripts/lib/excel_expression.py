"""Safe parsed Excel expressions shared by migration analysis and rendering.

The parser intentionally supports a bounded scalar formula language. Unsupported
or external constructs raise :class:`UnsupportedExpression`; source text is never
passed to Python ``eval``.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, ROUND_UP
from datetime import datetime
import calendar
import math
import re
from typing import Callable, Iterable

from openpyxl.utils.cell import column_index_from_string, get_column_letter
from openpyxl.utils.datetime import from_excel, to_excel, WINDOWS_EPOCH


class ExpressionError(ValueError):
    pass


class UnsupportedExpression(ExpressionError):
    pass


class ExcelCalcError(ExpressionError):
    """A source calculation error, eligible for Excel IFERROR handling."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class CellReference:
    sheet: str | None
    address: str | None
    column_absolute: bool = False
    row_absolute: bool = False
    name: str | None = None
    workbook: str | None = None


@dataclass(frozen=True)
class Number:
    value: float | int
    source: str


@dataclass(frozen=True)
class Text:
    value: str


@dataclass(frozen=True)
class Boolean:
    value: bool


@dataclass(frozen=True)
class Reference:
    value: CellReference


@dataclass(frozen=True)
class Range:
    start: CellReference
    end: CellReference


@dataclass(frozen=True)
class ColumnRange:
    sheet: str | None
    start_column: str
    end_column: str


@dataclass(frozen=True)
class StructuredReference:
    table: str | None
    specification: str


@dataclass(frozen=True)
class BoundRange:
    start: CellReference
    end: CellReference
    source_kind: str
    declared_domain: str
    active_domain: str
    empty: bool = False


@dataclass(frozen=True)
class BoundIndirect:
    selector: object
    alternatives: tuple[tuple[str, object], ...]


@dataclass(frozen=True)
class Unary:
    operator: str
    operand: object


@dataclass(frozen=True)
class Percent:
    operand: object


@dataclass(frozen=True)
class Binary:
    operator: str
    left: object
    right: object


@dataclass(frozen=True)
class Function:
    name: str
    arguments: tuple[object, ...]


@dataclass(frozen=True)
class Group:
    expression: object


_CELL = re.compile(r"^(\$?)([A-Za-z]{1,3})(\$?)([1-9][0-9]*)$")
_CELL_TOKEN = re.compile(r"\$?[A-Za-z]{1,3}\$?[1-9][0-9]*")
_NUMBER = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
_IDENT = re.compile(r"[A-Za-z_\\][A-Za-z0-9_.\\]*")
_SUPPORTED_FUNCTIONS = {"SUM", "SUMIFS", "IF", "ROUND", "ABS", "MIN", "MAX", "INT"}
_WORKBOOK_FUNCTIONS = _SUPPORTED_FUNCTIONS | {"IFERROR", "AND", "OR", "COUNTIFS", "COUNTA",
    "INDEX", "MATCH", "VLOOKUP", "XLOOKUP", "DATE", "EDATE", "EOMONTH", "MONTH",
    "MOD", "CEILING", "AVERAGE", "INDIRECT", "ROUNDUP", "COUNT"}
_KNOWN_XLFN = {"XLOOKUP", "FORECAST.ETS", "FORECAST.LINEAR", "STDEV.S",
               "NORM.S.INV", "SEQUENCE", "_XLWS.SORT"}


def _unquote_sheet(value: str) -> str:
    if value.startswith("'"):
        return value[1:-1].replace("''", "'")
    return value


class _Lexer:
    def __init__(self, source: str, workbook_mode: bool = False):
        self.source = source
        self.position = 0
        self.workbook_mode = workbook_mode

    def tokens(self):
        result = []
        while self.position < len(self.source):
            ch = self.source[self.position]
            if ch.isspace():
                self.position += 1
                continue
            if ch == "[" and self.workbook_mode:
                result.append(("STRUCT", (None, self._bracketed())))
                continue
            if ch in "{}[]#;@":
                raise UnsupportedExpression(f"unsupported formula token {ch!r}")
            if ch == '"':
                result.append(("TEXT", self._quoted_text()))
                continue
            if ch == "'":
                result.append(("SHEET", self._quoted_sheet()))
                continue
            number = _NUMBER.match(self.source, self.position)
            if number:
                value = number.group(0)
                self.position = number.end()
                result.append(("NUMBER", value))
                continue
            cell = _CELL_TOKEN.match(self.source, self.position)
            if cell:
                value = cell.group(0)
                self.position = cell.end()
                result.append(("IDENT", value))
                continue
            if self.workbook_mode and ch == "$":
                column = re.match(r"\$[A-Za-z]{1,3}(?![A-Za-z0-9])", self.source[self.position:])
                if column:
                    value = column.group(0)
                    self.position += len(value)
                    result.append(("IDENT", value))
                    continue
            ident = _IDENT.match(self.source, self.position)
            if ident:
                value = ident.group(0)
                self.position = ident.end()
                if self.workbook_mode and self.position < len(self.source) and self.source[self.position] == "[":
                    result.append(("STRUCT", (value, self._bracketed())))
                elif self.position < len(self.source) and self.source[self.position] == "!":
                    self.position += 1
                    result.append(("SHEET", value))
                else:
                    result.append(("IDENT", value))
                continue
            two = self.source[self.position:self.position + 2]
            if two in (">=", "<=", "<>"):
                result.append(("OP", two)); self.position += 2; continue
            if ch in "+-*/^%=><(),:&" if self.workbook_mode else ch in "+-*/^%=><(),:":
                result.append(("OP", ch)); self.position += 1; continue
            raise UnsupportedExpression(f"unsupported formula text near {self.source[self.position:]!r}")
        result.append(("EOF", ""))
        return result

    def _bracketed(self):
        start = self.position
        depth = 0
        while self.position < len(self.source):
            char = self.source[self.position]
            self.position += 1
            if char == "[": depth += 1
            elif char == "]":
                depth -= 1
                if depth == 0:
                    return self.source[start:self.position]
        raise ExpressionError("unterminated structured reference")

    def _quoted_text(self):
        self.position += 1
        out = []
        while self.position < len(self.source):
            ch = self.source[self.position]
            self.position += 1
            if ch == '"':
                if self.position < len(self.source) and self.source[self.position] == '"':
                    out.append('"'); self.position += 1; continue
                return "".join(out)
            out.append(ch)
        raise ExpressionError("unterminated string literal")

    def _quoted_sheet(self):
        start = self.position
        self.position += 1
        while self.position < len(self.source):
            if self.source[self.position] == "'":
                if self.position + 1 < len(self.source) and self.source[self.position + 1] == "'":
                    self.position += 2; continue
                self.position += 1
                if self.position >= len(self.source) or self.source[self.position] != "!":
                    raise UnsupportedExpression("quoted text is only supported as a sheet reference")
                value = self.source[start:self.position]
                self.position += 1
                if ("[" in value or "]" in value) and not self.workbook_mode:
                    raise UnsupportedExpression("external workbook references are unsupported")
                return value
            self.position += 1
        raise ExpressionError("unterminated quoted sheet name")


class _Parser:
    def __init__(self, source: str, sheet: str | None, workbook_mode: bool = False):
        self.tokens = _Lexer(source, workbook_mode).tokens()
        self.index = 0
        self.sheet = sheet
        self.workbook_mode = workbook_mode

    def parse(self):
        result = self._comparison()
        if self._peek()[0] != "EOF":
            raise UnsupportedExpression(f"unexpected token {self._peek()[1]!r}")
        return result

    def _peek(self):
        return self.tokens[self.index]

    def _take(self):
        value = self.tokens[self.index]
        self.index += 1
        return value

    def _accept(self, value):
        if self._peek() == ("OP", value):
            self.index += 1
            return True
        return False

    def _comparison(self):
        node = self._concatenate()
        while self._peek() in (("OP", "="), ("OP", "<>"), ("OP", "<"),
                               ("OP", ">"), ("OP", "<="), ("OP", ">=")):
            op = self._take()[1]
            node = Binary(op, node, self._concatenate())
        return node

    def _additive(self):
        node = self._multiplicative()
        while self._peek() in (("OP", "+"), ("OP", "-")):
            op = self._take()[1]
            node = Binary(op, node, self._multiplicative())
        return node

    def _concatenate(self):
        node = self._additive()
        while self._accept("&"):
            node = Binary("&", node, self._additive())
        return node

    def _multiplicative(self):
        node = self._power()
        while self._peek() in (("OP", "*"), ("OP", "/")):
            op = self._take()[1]
            node = Binary(op, node, self._power())
        return node

    def _power(self):
        node = self._unary()
        while self._accept("^"):
            node = Binary("^", node, self._unary())
        return node

    def _unary(self):
        if self._peek() in (("OP", "+"), ("OP", "-")):
            return Unary(self._take()[1], self._unary())
        node = self._primary()
        while self._accept("%"):
            node = Percent(node)
        return node

    def _primary(self):
        kind, value = self._take()
        if kind == "NUMBER":
            return Number(float(value) if any(c in value for c in ".eE") else int(value), value)
        if kind == "TEXT":
            return Text(value)
        if kind == "STRUCT":
            return StructuredReference(*value)
        if kind == "SHEET":
            return self._reference(_unquote_sheet(value))
        if kind == "IDENT":
            if self._accept("("):
                name = value.upper()
                if self.workbook_mode and name.startswith("_XLFN.") and name[6:] in _KNOWN_XLFN:
                    name = name[6:]
                if name not in (_WORKBOOK_FUNCTIONS if self.workbook_mode else _SUPPORTED_FUNCTIONS) and not self.workbook_mode:
                    raise UnsupportedExpression(f"unsupported function {name}")
                args = []
                if not self._accept(")"):
                    while True:
                        args.append(self._comparison())
                        if self._accept(")"):
                            break
                        if not self._accept(","):
                            raise ExpressionError("expected ',' or ')' in function")
                return Function(name, tuple(args))
            if self.workbook_mode and value.upper() in ("TRUE", "FALSE"):
                return Boolean(value.upper() == "TRUE")
            if _CELL.match(value):
                self.index -= 1
                return self._reference(self.sheet)
            if self.workbook_mode and self._peek() == ("OP", ":") and re.fullmatch(r"\$?[A-Za-z]{1,3}", value):
                self._take()
                kind2, value2 = self._take()
                if kind2 != "IDENT" or not re.fullmatch(r"\$?[A-Za-z]{1,3}", value2):
                    raise UnsupportedExpression("whole-column range needs two columns")
                return ColumnRange(self.sheet, value.replace("$", "").upper(), value2.replace("$", "").upper())
            return Reference(CellReference(None, None, name=value))
        if kind == "OP" and value == "(":
            expression = self._comparison()
            if not self._accept(")"):
                raise ExpressionError("unclosed parenthesis")
            return Group(expression)
        raise ExpressionError(f"expected expression, got {value!r}")

    def _reference(self, sheet):
        kind, value = self._take()
        if kind != "IDENT":
            raise UnsupportedExpression("sheet names must be followed by a cell reference")
        if self.workbook_mode and re.fullmatch(r"\$?[A-Za-z]{1,3}", value) and self._accept(":"):
            kind2, value2 = self._take()
            if kind2 != "IDENT" or not re.fullmatch(r"\$?[A-Za-z]{1,3}", value2):
                raise UnsupportedExpression("whole-column range needs two columns")
            return ColumnRange(sheet, value.replace("$", "").upper(), value2.replace("$", "").upper())
        if not _CELL.match(value):
            raise UnsupportedExpression("sheet names must be followed by a cell reference")
        start = _cell_reference(sheet, value)
        if not self._accept(":"):
            return Reference(start)
        end_sheet = sheet
        if self._peek()[0] == "SHEET":
            end_sheet = _unquote_sheet(self._take()[1])
        kind, value = self._take()
        if kind != "IDENT" or not _CELL.match(value):
            raise UnsupportedExpression("range endpoint must be a cell reference")
        return Range(start, _cell_reference(end_sheet, value))


def _cell_reference(sheet, address):
    match = _CELL.match(address)
    workbook = None
    if sheet and sheet.startswith("[") and "]" in sheet:
        workbook, sheet = sheet[1:].split("]", 1)
    return CellReference(sheet, f"{match.group(2).upper()}{match.group(4)}",
                         bool(match.group(1)), bool(match.group(3)), workbook=workbook)


def parse_expression(formula: str, *, sheet: str | None = None, workbook_mode: bool = False):
    if not isinstance(formula, str) or not formula.startswith("="):
        raise ExpressionError("Excel expressions must start with '='")
    source = formula[1:].strip()
    if not source:
        raise ExpressionError("empty formula")
    if ("[" in source or "]" in source) and not workbook_mode:
        raise UnsupportedExpression("external or structured references are unsupported")
    return _Parser(source, sheet, workbook_mode).parse()


def _walk(node) -> Iterable[CellReference]:
    if isinstance(node, Reference):
        yield node.value
    elif isinstance(node, Range):
        yield node.start; yield node.end
    elif isinstance(node, (Unary, Percent, Group)):
        yield from _walk(node.operand if not isinstance(node, Group) else node.expression)
    elif isinstance(node, Binary):
        yield from _walk(node.left); yield from _walk(node.right)
    elif isinstance(node, Function):
        for argument in node.arguments:
            yield from _walk(argument)
    elif not isinstance(node, (Number, Text, Boolean)):
        raise UnsupportedExpression(f"cannot extract references from {type(node).__name__} before workbook binding")


def extract_references(expression) -> tuple[CellReference, ...]:
    return tuple(_walk(expression))


def expand_range(value: Range | BoundRange) -> tuple[CellReference, ...]:
    if isinstance(value, BoundRange) and value.empty:
        return ()
    if value.start.name or value.end.name or value.start.sheet != value.end.sheet:
        raise UnsupportedExpression("ranges must use cells on one sheet")
    start = _CELL.match(value.start.address)
    end = _CELL.match(value.end.address)
    c1, c2 = column_index_from_string(start.group(2)), column_index_from_string(end.group(2))
    r1, r2 = int(start.group(4)), int(end.group(4))
    refs = []
    for row in range(min(r1, r2), max(r1, r2) + 1):
        for col in range(min(c1, c2), max(c1, c2) + 1):
            refs.append(CellReference(value.start.sheet, f"{get_column_letter(col)}{row}"))
    return tuple(refs)


def _contains_whole_column(node) -> bool:
    if isinstance(node, BoundRange):
        return node.source_kind == "whole_column"
    if isinstance(node, Group):
        return _contains_whole_column(node.expression)
    if isinstance(node, (Unary, Percent)):
        return _contains_whole_column(node.operand)
    if isinstance(node, Binary):
        return _contains_whole_column(node.left) or _contains_whole_column(node.right)
    if isinstance(node, Function):
        return any(_contains_whole_column(argument) for argument in node.arguments)
    if isinstance(node, BoundIndirect):
        return (_contains_whole_column(node.selector)
                or any(_contains_whole_column(target) for _, target in node.alternatives))
    return False


_ARITHMETIC_OPERATORS = {"+", "-", "*", "/", "^"}
_NUMERIC_SCALAR_FUNCTIONS = {"ROUND", "ROUNDUP", "ABS", "INT"}


def _argument_arithmetic_context(name, index, outer_context):
    if name == "IF":
        return outer_context and index > 0
    return name in _NUMERIC_SCALAR_FUNCTIONS


def evaluate(expression, resolver: Callable[[CellReference], object], *,
             arithmetic_reference_resolver: Callable[[CellReference, object], object] | None = None,
             arithmetic_context: bool = False, date_epoch=None, excel_errors: bool = False):
    """Evaluate one parsed expression; optionally coerce typed blank leaves in arithmetic.

    The callback sees only scalar references in numeric arithmetic context. It
    decides from source provenance whether a NULL is an empty numeric literal;
    a derived formula error must remain an error/NULL. ``arithmetic_context``
    carries the caller's numeric use through an inlined formula reference.
    """
    def run(node, arithmetic=False):
        if isinstance(node, Number): return node.value
        if isinstance(node, Text): return node.value
        if isinstance(node, Boolean): return node.value
        if isinstance(node, Reference):
            value = resolver(node.value)
            return (arithmetic_reference_resolver(node.value, value)
                    if arithmetic and arithmetic_reference_resolver is not None else value)
        if isinstance(node, (Range, BoundRange)):
            values = [resolver(ref) for ref in expand_range(node)]
            if (isinstance(node, BoundRange) and node.source_kind.endswith(":#this row")
                and len(values) == 1):
                return values[0]
            return values
        if isinstance(node, BoundIndirect):
            selector = _excel_text(run(node.selector))
            for name, target in node.alternatives:
                if name.casefold() == selector.casefold():
                    return run(target, arithmetic)
            raise ExcelCalcError("#REF!")
        if isinstance(node, Group): return run(node.expression, arithmetic)
        if isinstance(node, Unary):
            value = run(node.operand, True)
            return value if node.operator == "+" else -value
        if isinstance(node, Percent): return run(node.operand, True) * 0.01
        if isinstance(node, Binary):
            numeric = node.operator in _ARITHMETIC_OPERATORS
            left, right = run(node.left, numeric), run(node.right, numeric)
            if node.operator == "&": return _excel_text(left) + _excel_text(right)
            if numeric and excel_errors:
                left, right = _numeric(left), _numeric(right)
            elif excel_errors and node.operator in ("=", "<>", "<", ">", "<=", ">="):
                if left is None: left = "" if isinstance(right, str) else 0
                if right is None: right = "" if isinstance(left, str) else 0
            operations = {
                "+": lambda: left + right, "-": lambda: left - right,
                "*": lambda: left * right, "/": lambda: left / right,
                "^": lambda: left ** right, "=": lambda: left == right,
                "<>": lambda: left != right, "<": lambda: left < right,
                ">": lambda: left > right, "<=": lambda: left <= right,
                ">=": lambda: left >= right,
            }
            try:
                return operations[node.operator]()
            except ZeroDivisionError as error:
                if not excel_errors: raise
                raise ExcelCalcError("#DIV/0!") from error
            except (TypeError, ValueError, OverflowError) as error:
                if not excel_errors: raise
                raise ExcelCalcError("#VALUE!") from error
        if isinstance(node, Function):
            if node.name == "IF":
                if len(node.arguments) not in (2, 3):
                    raise ExpressionError("IF requires two or three arguments")
                condition = run(node.arguments[0])
                if condition:
                    return run(node.arguments[1], arithmetic)
                return run(node.arguments[2], arithmetic) if len(node.arguments) == 3 else False
            if node.name == "IFERROR":
                if len(node.arguments) != 2:
                    raise ExpressionError("IFERROR requires two arguments")
                try:
                    return run(node.arguments[0], arithmetic)
                except ExcelCalcError:
                    return run(node.arguments[1], arithmetic)
            if node.name not in _WORKBOOK_FUNCTIONS:
                raise UnsupportedExpression(f"unsupported function {node.name}")
            args = [run(arg, _argument_arithmetic_context(node.name, i, arithmetic))
                    for i, arg in enumerate(node.arguments)]
            if node.name == "ROUND":
                if len(args) != 2:
                    raise ExpressionError("ROUND requires two arguments")
                places = int(args[1])
                quantum = Decimal("1").scaleb(-places)
                return float(Decimal(str(args[0])).quantize(quantum, rounding=ROUND_HALF_UP))
            if node.name == "ROUNDUP":
                if len(args) != 2: raise ExpressionError("ROUNDUP requires two arguments")
                quantum = Decimal("1").scaleb(-int(_numeric(args[1])))
                return float(Decimal(str(_numeric(args[0]))).quantize(quantum, rounding=ROUND_UP))
            if node.name == "ABS": return abs(_numeric(args[0]))
            if node.name == "INT": return math.floor(_numeric(args[0]))
            if node.name == "MIN": return min((v for v in _flatten(args) if isinstance(v, (int, float))), default=0)
            if node.name == "MAX": return max((v for v in _flatten(args) if isinstance(v, (int, float))), default=0)
            if node.name == "SUM": return sum(v for v in _flatten(args) if _is_number(v))
            if node.name == "SUMIFS":
                matched = _criteria_indices(args[1:], len(_as_list(args[0])), "SUMIFS")
                return sum(value for i, value in enumerate(_as_list(args[0]))
                           if i in matched and _is_number(value))
            if node.name == "COUNTIFS":
                for index in range(0, len(args), 2):
                    if (index + 1 < len(args) and _contains_whole_column(node.arguments[index])
                        and _criteria_match(None, args[index + 1])):
                        raise UnsupportedExpression("COUNTIFS criterion matches omitted whole-column blanks")
                return len(_criteria_indices(args, len(_as_list(args[0])), "COUNTIFS"))
            if node.name == "COUNTA":
                return sum(value is not None for value in _flatten(args))
            if node.name == "COUNT":
                return sum(_is_number(value) for value in _flatten(args))
            if node.name == "AVERAGE":
                numbers = [value for value in _flatten(args) if _is_number(value)]
                if not numbers: raise ExcelCalcError("#DIV/0!")
                return sum(numbers) / len(numbers)
            if node.name in ("AND", "OR"):
                logical = [value for value in _flatten(args) if value is not None]
                if not logical: raise ExcelCalcError("#VALUE!")
                return (all if node.name == "AND" else any)(bool(value) for value in logical)
            if node.name == "MOD":
                if args[1] == 0: raise ExcelCalcError("#DIV/0!")
                return _numeric(args[0]) % _numeric(args[1])
            if node.name == "CEILING":
                significance = _numeric(args[1])
                if significance == 0: return 0
                if _numeric(args[0]) * significance < 0: raise ExcelCalcError("#NUM!")
                return math.ceil(_numeric(args[0]) / significance) * significance
            if node.name == "DATE":
                if len(args) != 3: raise ExpressionError("DATE requires three arguments")
                year, month, day = (int(_numeric(value)) for value in args)
                if 0 <= year <= 1899: year += 1900
                year += (month - 1) // 12
                month = (month - 1) % 12 + 1
                from datetime import timedelta
                return int(to_excel(datetime(year, month, 1) + timedelta(days=day - 1), date_epoch or WINDOWS_EPOCH))
            if node.name in ("EDATE", "EOMONTH", "MONTH"):
                if len(args) != (1 if node.name == "MONTH" else 2):
                    raise ExpressionError(f"{node.name} argument count")
                start = from_excel(_numeric(args[0]), date_epoch or WINDOWS_EPOCH)
                if node.name == "MONTH": return start.month
                months = int(_numeric(args[1]))
                year = start.year + (start.month - 1 + months) // 12
                month = (start.month - 1 + months) % 12 + 1
                day = calendar.monthrange(year, month)[1] if node.name == "EOMONTH" else min(start.day, calendar.monthrange(year, month)[1])
                return int(to_excel(datetime(year, month, day), date_epoch or WINDOWS_EPOCH))
            if node.name == "INDEX":
                if len(args) not in (2, 3): raise ExpressionError("INDEX argument count")
                values = _as_list(args[0]); row = int(_numeric(args[1]))
                width = _range_width(node.arguments[0])
                column = int(_numeric(args[2])) if len(args) == 3 else 1
                if row > 0 and column == 0:
                    start = (row - 1) * width
                    if start >= len(values): raise ExcelCalcError("#REF!")
                    return values[start:start + width]
                if row == 0 and column > 0:
                    if column > width: raise ExcelCalcError("#REF!")
                    return values[column - 1::width]
                offset = (row - 1) * width + column - 1
                if row < 1 or column < 1 or column > width or offset >= len(values):
                    raise ExcelCalcError("#REF!")
                return values[offset]
            if node.name == "MATCH":
                if len(args) not in (2, 3): raise ExpressionError("MATCH argument count")
                if len(args) < 3 or args[2] != 0:
                    raise UnsupportedExpression("MATCH approximate mode requires review")
                for index, value in enumerate(_as_list(args[1]), 1):
                    if _excel_equal(value, args[0]): return index
                raise ExcelCalcError("#N/A")
            if node.name == "VLOOKUP":
                if len(args) != 4 or args[3] not in (False, 0):
                    raise UnsupportedExpression("VLOOKUP approximate mode requires review")
                width = _range_width(node.arguments[1]); col = int(_numeric(args[2]))
                if col < 1 or col > width: raise ExcelCalcError("#REF!")
                values = _as_list(args[1])
                for offset in range(0, len(values), width):
                    if _excel_equal(values[offset], args[0]): return values[offset + col - 1]
                raise ExcelCalcError("#N/A")
            if node.name == "XLOOKUP":
                if len(args) < 3 or len(args) > 6: raise ExpressionError("XLOOKUP argument count")
                if len(args) >= 5 and args[4] not in (0, None):
                    raise UnsupportedExpression("XLOOKUP match mode requires review")
                if len(args) >= 6 and args[5] not in (1, None):
                    raise UnsupportedExpression("XLOOKUP search mode requires review")
                looked, returned = _as_list(args[1]), _as_list(args[2])
                if len(looked) != len(returned): raise ExcelCalcError("#VALUE!")
                for index, value in enumerate(looked):
                    if _excel_equal(value, args[0]): return returned[index]
                if len(args) >= 4: return args[3]
                raise ExcelCalcError("#N/A")
            if node.name == "INDIRECT":
                raise UnsupportedExpression("INDIRECT requires finite workbook binding")
        raise UnsupportedExpression(f"cannot evaluate {type(node).__name__}")
    try:
        return run(expression, arithmetic_context)
    except (ValueError, TypeError, OverflowError) as error:
        if isinstance(error, ExpressionError): raise
        if not excel_errors: raise
        raise ExcelCalcError("#VALUE!") from error


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _numeric(value):
    if value is None: return 0
    if isinstance(value, bool): return int(value)
    if _is_number(value): return value
    raise ExcelCalcError("#VALUE!")


def _excel_text(value):
    if value is None: return ""
    if value is True: return "TRUE"
    if value is False: return "FALSE"
    return str(value)


def _as_list(value):
    return value if isinstance(value, list) else [value]


def _range_width(node):
    if isinstance(node, (Range, BoundRange)):
        a = column_index_from_string(_CELL.match(node.start.address).group(2))
        b = column_index_from_string(_CELL.match(node.end.address).group(2))
        return abs(b - a) + 1
    return 1


def _excel_equal(left, right):
    if isinstance(left, str) and isinstance(right, str):
        return left.casefold() == right.casefold()
    return left == right


NUMERIC_TEXT = r"^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$"


def _parse_criterion(criterion):
    """Separate blank references (numeric zero) from empty criterion text.

    Numeric recognition uses the native compiler's grammar; Python float alone
    also accepts non-Excel spellings such as inf/NaN and digit separators.
    Preserve whitespace for nonnumeric text and wildcard criteria.
    """
    if not isinstance(criterion, str):
        return "=", 0 if criterion is None else criterion
    match = re.match(r"^(<=|>=|<>|=|<|>)(.*)$", criterion)
    operator, operand = match.groups() if match else ("=", criterion)
    if operand == "": return operator, None
    if re.fullmatch(NUMERIC_TEXT, operand.strip()):
        number = float(operand)
        if not math.isfinite(number):
            raise UnsupportedExpression("nonfinite numeric criterion requires Excel oracle")
        return operator, number
    return operator, operand


def _criteria_match(value, criterion):
    operator, target = _parse_criterion(criterion)
    if isinstance(target, str) and any(char in target for char in "*?~") and operator in ("=", "<>"):
        pattern = []
        index = 0
        while index < len(target):
            char = target[index]
            if char == "~" and index + 1 < len(target):
                index += 1; pattern.append(re.escape(target[index]))
            elif char == "*": pattern.append(".*")
            elif char == "?": pattern.append(".")
            else: pattern.append(re.escape(char))
            index += 1
        result = re.fullmatch("".join(pattern), _excel_text(value), flags=re.IGNORECASE) is not None
        return result if operator == "=" else not result
    if operator in ("=", "<>"):
        if target is None:
            result = value is None or value == ""
        # Criteria equality accepts numeric text in the range; keep ordinary
        # comparison/lookup equality and ordered criteria type-sensitive.
        elif (_is_number(target) and isinstance(value, str)
              and re.fullmatch(NUMERIC_TEXT, value.strip())):
            result = float(value) == target
        else:
            result = _excel_equal(value, target) or value is None and target == 0
        return result if operator == "=" else not result
    if value is None: return False
    if _is_number(value) and _is_number(target):
        left, right = value, target
    elif isinstance(value, str) and isinstance(target, str):
        left, right = value.casefold(), target.casefold()
    else: return False
    return {"<": left < right, ">": left > right, "<=": left <= right, ">=": left >= right}[operator]


def _criteria_indices(arguments, length, name):
    if len(arguments) < 2 or len(arguments) % 2:
        raise ExpressionError(f"{name} requires range/criterion pairs")
    conditions = []
    for index in range(0, len(arguments), 2):
        values = _as_list(arguments[index])
        if len(values) != length:
            raise ExcelCalcError("#VALUE!")
        conditions.append((values, arguments[index + 1]))
    return {index for index in range(length)
            if all(_criteria_match(values[index], criterion) for values, criterion in conditions)}


def _flatten(values):
    for value in values:
        if isinstance(value, list):
            yield from value
        else:
            yield value


def emit_sigma(expression, reference_renderer: Callable[[CellReference], str],
               range_renderer: Callable[[Range], str] | None = None, *,
               arithmetic_reference_renderer: Callable[[CellReference], str] | None = None,
               arithmetic_context: bool = False) -> str:
    function_names = {"IF": "If", "ROUND": "Round", "ABS": "Abs", "MIN": "Min",
                      "MAX": "Max", "SUM": "Sum", "INT": "Floor", "SUMIFS": "SumIfs"}

    def render(node, arithmetic=False):
        if isinstance(node, Number): return node.source
        if isinstance(node, Text): return '"' + node.value.replace('"', '\\"') + '"'
        if isinstance(node, Boolean): raise UnsupportedExpression("Boolean workbook literal requires native binding")
        if isinstance(node, Reference):
            if node.value.workbook:
                raise UnsupportedExpression("cannot emit external workbook reference to Sigma without explicit binding")
            return (arithmetic_reference_renderer(node.value)
                    if arithmetic and arithmetic_reference_renderer is not None
                    else reference_renderer(node.value))
        if isinstance(node, Range):
            if range_renderer is not None:
                return range_renderer(node)
            return f"Range({reference_renderer(node.start)}, {reference_renderer(node.end)})"
        if isinstance(node, Group): return f"({render(node.expression, arithmetic)})"
        if isinstance(node, Unary): return f"{node.operator}{render(node.operand, True)}"
        if isinstance(node, Percent): return f"({render(node.operand, True)} * 0.01)"
        if isinstance(node, Binary):
            if node.operator == "&":
                raise UnsupportedExpression("cannot emit Excel concatenation to Sigma without qualified mapping")
            numeric = node.operator in _ARITHMETIC_OPERATORS
            if node.operator == "^":
                return f"Power({render(node.left, numeric)}, {render(node.right, numeric)})"
            operator = "!=" if node.operator == "<>" else node.operator
            return f"{render(node.left, numeric)} {operator} {render(node.right, numeric)}"
        if isinstance(node, Function):
            if node.name not in function_names:
                raise UnsupportedExpression(f"cannot emit function {node.name} to Sigma")
            return f"{function_names[node.name]}(" + ", ".join(
                render(arg, _argument_arithmetic_context(node.name, i, arithmetic))
                for i, arg in enumerate(node.arguments)) + ")"
        raise UnsupportedExpression(f"cannot emit {type(node).__name__}")
    return render(expression, arithmetic_context)
