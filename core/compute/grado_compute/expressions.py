"""Безопасный вычислитель выражений метрик.

Язык выражений: арифметика (+ - * / // % **), унарный минус, сравнения,
логические and/or, тернарный where(cond, a, b) и вызовы функций из FUNCS.
Имена разрешаются через переданный словарь значений. Доступ к атрибутам,
индексам и встроенным функциям Python запрещён на этапе разбора.
"""

import ast
import math

def round_half_up(x, n=0):
    """Математическое округление: 2,5 → 3, 0,0005 → 0,001. Встроенный round() в Python банковский (2,5 → 2)
    и вдобавок ошибается на двоичном представлении (round(2.675, 2) = 2.67) — считаем через десятичную запись."""
    from decimal import ROUND_HALF_UP, Decimal
    q = Decimal(1).scaleb(-int(n))
    r = Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP)
    return int(r) if int(n) <= 0 else float(r)


FUNCS = {
    "min": min,
    "max": max,
    "abs": abs,
    "round": round_half_up,
    "floor": math.floor,
    "ceil": math.ceil,
    "sqrt": math.sqrt,
    "clamp": lambda x, lo, hi: max(lo, min(hi, x)),
    "where": lambda cond, a, b: a if cond else b,
    # where() вычисляет обе ветви — деление через div(), чтобы нулевой знаменатель давал 0, а не исключение
    "div": lambda a, b: a / b if b else 0.0,
}

_ALLOWED_NODES = (
    ast.Expression,
    ast.BinOp, ast.UnaryOp, ast.Compare, ast.BoolOp, ast.IfExp,
    ast.Call, ast.Name, ast.Constant, ast.Load,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd,
    ast.Gt, ast.GtE, ast.Lt, ast.LtE, ast.Eq, ast.NotEq,
    ast.And, ast.Or,
)


class ExpressionError(ValueError):
    pass


def parse(expr):
    """Разбирает и валидирует выражение, возвращает ast.Expression."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise ExpressionError(f"синтаксическая ошибка в выражении {expr!r}: {e}") from None
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ExpressionError(
                f"недопустимая конструкция {type(node).__name__} в выражении {expr!r}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCS:
                raise ExpressionError(f"недопустимый вызов функции в выражении {expr!r}")
            if node.keywords:
                raise ExpressionError(f"именованные аргументы запрещены: {expr!r}")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float, bool)):
            raise ExpressionError(f"недопустимая константа {node.value!r} в {expr!r}")
    return tree


def names(expr):
    """Множество имён-зависимостей выражения (без имён функций)."""
    tree = parse(expr) if isinstance(expr, str) else expr
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id not in FUNCS}


def evaluate(expr, values):
    """Вычисляет выражение по словарю значений."""
    tree = parse(expr) if isinstance(expr, str) else expr
    missing = names(tree) - values.keys()
    if missing:
        raise ExpressionError(f"неизвестные имена {sorted(missing)}")
    code = compile(tree, "<metric>", "eval")
    return eval(code, {"__builtins__": {}, **FUNCS}, dict(values))
