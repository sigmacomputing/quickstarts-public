"""Cell-granular workbook dependency graphs for formula migration."""
from __future__ import annotations

from dataclasses import dataclass

try:
    from .excel_expression import (ExpressionError, Function, Group, Binary, Unary, Percent,
                                   Number, Text, Range, Reference, UnsupportedExpression,
                                   evaluate, expand_range, parse_expression)
except ImportError:  # standalone tests/scripts that place lib directly on sys.path
    from excel_expression import (ExpressionError, Function, Group, Binary, Unary, Percent,
                                  Number, Text, Range, Reference, UnsupportedExpression,
                                  evaluate, expand_range, parse_expression)


@dataclass(frozen=True, order=True)
class CellIdentity:
    sheet: str
    address: str

    @property
    def id(self):
        return f"{self.sheet}!{self.address}"


def formula_source(value):
    """Keep scalar formulas unchanged and serialize object anchors without executing them."""
    if isinstance(value, str):
        return value
    attributes = vars(value)
    if any(not isinstance(key, str) or item is not None and
           not isinstance(item, (str, int, float, bool)) for key, item in attributes.items()):
        raise ValueError(f"formula object {type(value).__name__} has unsupported source attributes")
    return {"objectType": type(value).__name__, "attributes": dict(sorted(attributes.items()))}


class FormulaGraph:
    def __init__(self, formulas, literals, dependencies, unresolved, unsupported, names=None,
                 unresolved_names=None):
        self.formulas = formulas
        self.literals = literals
        self.dependencies = dependencies
        self.unresolved_references = unresolved
        self.unsupported_formulas = unsupported
        self.names = names or {}
        self.unresolved_names = unresolved_names or {}

    @classmethod
    def from_workbook(cls, workbook):
        formulas, literals = {}, {}
        for ws in workbook.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if cell.value is None:
                        continue
                    identity = CellIdentity(ws.title, cell.coordinate)
                    if cell.data_type == "f":
                        formulas[identity] = formula_source(cell.value)
                    else:
                        literals[identity] = cell.value
        existing = set(formulas) | set(literals)
        names = _defined_names(workbook)
        dependencies, unresolved, unsupported, unresolved_names = {}, {}, {}, {}
        for identity, formula in formulas.items():
            if not isinstance(formula, str):
                unsupported[identity] = f"formula object {formula['objectType']} requires review"
                refs = ()
            else:
                try:
                    expression = parse_expression(formula, sheet=identity.sheet)
                    refs = tuple(_expression_cells(expression))
                except ExpressionError as error:
                    unsupported[identity] = str(error)
                    refs = ()
            deps = set()
            missing_names = set()
            for ref in refs:
                if ref.name:
                    if ref.name in names:
                        deps.add(names[ref.name])
                    else:
                        missing_names.add(ref.name)
                elif ref.sheet and ref.address:
                    deps.add(CellIdentity(ref.sheet, ref.address))
            deps = tuple(sorted(deps))
            dependencies[identity] = deps
            missing = tuple(dep for dep in deps if dep not in existing)
            if missing:
                unresolved[identity] = missing
            if missing_names:
                unresolved_names[identity] = tuple(sorted(missing_names))
        return cls(formulas, literals, dependencies, unresolved, unsupported, names,
                   unresolved_names)

    def unresolved_formula_nodes(self):
        """Return directly and transitively unresolved formula cells."""
        result = (set(self.unresolved_references) | set(self.unresolved_names)
                  | set(self.unsupported_formulas)
                  | {cell for component in self.cycles() for cell in component})
        changed = True
        while changed:
            changed = False
            for node, deps in self.dependencies.items():
                if node not in result and any(dep in result for dep in deps):
                    result.add(node)
                    changed = True
        return result

    def cycles(self):
        formula_nodes = set(self.formulas)
        edges = {node: tuple(dep for dep in self.dependencies.get(node, ()) if dep in formula_nodes)
                 for node in formula_nodes}
        index = 0
        stack = []
        on_stack = set()
        indices, low = {}, {}
        result = []

        def strong_connect(node):
            nonlocal index
            indices[node] = low[node] = index
            index += 1
            stack.append(node); on_stack.add(node)
            for dep in edges[node]:
                if dep not in indices:
                    strong_connect(dep); low[node] = min(low[node], low[dep])
                elif dep in on_stack:
                    low[node] = min(low[node], indices[dep])
            if low[node] == indices[node]:
                component = []
                while True:
                    member = stack.pop(); on_stack.remove(member); component.append(member)
                    if member == node:
                        break
                self_loop = len(component) == 1 and component[0] in edges[component[0]]
                if len(component) > 1 or self_loop:
                    result.append(tuple(sorted(component)))

        for node in sorted(formula_nodes):
            if node not in indices:
                strong_connect(node)
        return sorted(result)

    def topological_order(self):
        cycle_members = {node for component in self.cycles() for node in component}
        nodes = set(self.formulas) - cycle_members
        edges = {node: {dep for dep in self.dependencies.get(node, ()) if dep in nodes}
                 for node in nodes}
        result = []
        ready = sorted(node for node, deps in edges.items() if not deps)
        while ready:
            node = ready.pop(0)
            result.append(node)
            for candidate in sorted(nodes - set(result)):
                if node in edges[candidate]:
                    edges[candidate].remove(node)
                    if not edges[candidate] and candidate not in ready:
                        ready.append(candidate); ready.sort()
        return tuple(result)

    def evaluate(self, literal_overrides=None):
        """Evaluate acyclic formulas, optionally substituting known source literals."""
        values = dict(self.literals)
        for identity, value in (literal_overrides or {}).items():
            original = self.literals.get(identity)
            if not isinstance(original, (int, float)) or isinstance(original, bool):
                raise ValueError(f"numeric source literal required: {identity.id}")
            if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool)):
                raise ValueError(f"numeric source literal override required: {identity.id}")
            values[identity] = value
        # Cleared source literals stay None. A formula returning a reference
        # reads that blank as zero; its consumers therefore see a numeric result.
        # Failed formulas stay absent and never become ignorable blank inputs.
        expressions = {}
        for identity, formula in self.formulas.items():
            if not isinstance(formula, str):
                continue
            try:
                expressions[identity] = parse_expression(formula, sheet=identity.sheet)
            except ExpressionError:
                continue
        for identity in self.topological_order():
            expression = expressions.get(identity)
            if expression is None:
                continue

            def target_for(reference):
                if reference.name:
                    target = self.names.get(reference.name)
                    if target is None:
                        raise UnsupportedExpression(f"unresolved defined name {reference.name}")
                    return target
                return CellIdentity(reference.sheet, reference.address)

            def resolve(reference):
                target = target_for(reference)
                if target not in values:
                    raise UnsupportedExpression(f"unresolved or failed reference {target.id}")
                return values[target]

            def arithmetic_value(reference, value):
                target = target_for(reference)
                original = self.literals.get(target)
                return (0 if value is None and isinstance(original, (int, float))
                        and not isinstance(original, bool) else value)
            try:
                values[identity] = evaluate(expression, resolve,
                                            arithmetic_reference_resolver=arithmetic_value,
                                            arithmetic_context=True)
            except (ArithmeticError, TypeError, ValueError):
                continue
        return values


def _expression_cells(expression):
    if isinstance(expression, Reference):
        if expression.value.address or expression.value.name:
            yield expression.value
        return
    if isinstance(expression, Range):
        yield from expand_range(expression)
        return
    if isinstance(expression, (Number, Text)):
        return
    if not isinstance(expression, (Group, Unary, Percent, Binary, Function)):
        raise UnsupportedExpression(f"legacy formula graph cannot bind {type(expression).__name__}")
    for name in ("expression", "operand", "left", "right"):
        child = getattr(expression, name, None)
        if child is not None:
            yield from _expression_cells(child)
    for argument in getattr(expression, "arguments", ()):
        yield from _expression_cells(argument)


def _defined_names(workbook):
    result = {}
    for definition in workbook.defined_names.values():
        try:
            destinations = list(definition.destinations)
        except (AttributeError, TypeError):
            continue
        if len(destinations) != 1:
            continue
        sheet, address = destinations[0]
        address = address.replace("$", "")
        if ":" not in address:
            result[definition.name] = CellIdentity(sheet, address)
    return result
