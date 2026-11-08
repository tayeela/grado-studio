//! Безопасный вычислитель выражений метрик — порт core/compute/grado_compute/expressions.py.
//!
//! Язык: арифметика (+ - * / // % **), унарные +-, сравнения (в том числе цепочкой),
//! and/or (возвращают операнд, как в Python), вызовы функций FUNCS. Строк, атрибутов,
//! индексов, лямбд, ключевых аргументов нет — всё это отклоняется на разборе.
//! Семантика арифметики — Python: int произвольной точности, int/int → float,
//! // и % — «напольные», ** с пределами против бомб.

use crate::decimal::{round_half_up, py_float_repr, Value};
use num_bigint::BigInt;
use num_traits::{Signed, ToPrimitive, Zero};
use std::collections::BTreeSet;
use std::fmt::Write as _;

/// Пределы против выражений-бомб (как в Python-версии).
pub const MAX_EXPR_LEN: usize = 500;
pub const MAX_EXPR_DEPTH: i64 = 50;
pub const MAX_POW_EXP: f64 = 64.0;
pub const MAX_POW_BASE: f64 = 1e15;

pub const FUNCS: [&str; 10] = [
    "min", "max", "abs", "round", "floor", "ceil", "sqrt", "clamp", "where", "div",
];

#[derive(Debug)]
pub enum ExprError {
    /// Отклонено разбором или пределами (как ExpressionError в Python).
    Msg(String),
}

impl std::fmt::Display for ExprError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ExprError::Msg(m) => write!(f, "{m}"),
        }
    }
}

impl From<String> for ExprError {
    fn from(m: String) -> Self {
        ExprError::Msg(m)
    }
}

impl std::error::Error for ExprError {}

fn err<T>(msg: impl Into<String>) -> Result<T, ExprError> {
    Err(ExprError::Msg(msg.into()))
}

// ---------- Лексер ----------

#[derive(Clone, Debug, PartialEq)]
enum Tok {
    Int(String),   // цифры (bigint на разборе, как литерал Python)
    Float(f64),
    Ident(String),
    Op(String), // + - * / // % ** ( ) , == != <= >= < >
}

fn lex(src: &str) -> Result<Vec<Tok>, ExprError> {
    let b: Vec<char> = src.chars().collect();
    let mut toks = Vec::new();
    let mut i = 0;
    while i < b.len() {
        let c = b[i];
        match c {
            ' ' | '\t' | '\n' | '\r' => i += 1,
            '#' => {
                while i < b.len() && b[i] != '\n' {
                    i += 1;
                }
            }
            '0'..='9' => {
                let start = i;
                let mut has_dot = false;
                let mut has_exp = false;
                while i < b.len()
                    && (b[i].is_ascii_digit()
                        || b[i] == '_'
                        || (b[i] == '.' && !has_dot && !has_exp)
                        || ((b[i] == 'e' || b[i] == 'E') && !has_exp && i > start))
                {
                    if b[i] == '.' {
                        has_dot = true;
                    } else if b[i] == 'e' || b[i] == 'E' {
                        has_exp = true;
                        if i + 1 < b.len() && (b[i + 1] == '+' || b[i + 1] == '-') {
                            i += 1;
                        }
                    }
                    i += 1;
                }
                // e/E не может съесть следующий Ident: "2e" без цифр — ошибка, как в Python
                let raw: String = b[start..i].iter().collect();
                let clean = raw.replace('_', "");
                if has_dot || has_exp {
                    let v: f64 = clean
                        .parse()
                        .map_err(|_| ExprError::Msg(format!("плохое число {raw:?}")))?;
                    toks.push(Tok::Float(v));
                } else {
                    toks.push(Tok::Int(clean));
                }
            }
            'a'..='z' | 'A'..='Z' | '_' => {
                let start = i;
                while i < b.len() && (b[i].is_alphanumeric() || b[i] == '_') {
                    i += 1;
                }
                toks.push(Tok::Ident(b[start..i].iter().collect()));
            }
            _ => {
                let two: String = b[i..(i + 2).min(b.len())].iter().collect();
                let op = match two.as_str() {
                    "//" | "**" | "==" | "!=" | "<=" | ">=" => two,
                    _ => {
                        let one = c.to_string();
                        match one.as_str() {
                            "+" | "-" | "*" | "/" | "%" | "(" | ")" | "," | "<" | ">" => one,
                            _ => {
                                return err(format!(
                                    "недопустимый символ {c:?} в выражении"
                                ))
                            }
                        }
                    }
                };
                i += op.chars().count();
                toks.push(Tok::Op(op));
            }
        }
    }
    Ok(toks)
}

// ---------- AST ----------

#[derive(Clone, Debug)]
pub enum Node {
    Int(BigInt),
    Float(f64),
    Bool(bool),
    Name(String),
    Unary(char, Box<Node>),            // '-' | '+'
    Bin(char, Box<Node>, Box<Node>),   // '+' '-' '*' '/' '%' '**'
    FloorDiv(Box<Node>, Box<Node>),
    Mod(Box<Node>, Box<Node>),
    Cmp(Vec<CmpOp>, Vec<Node>),        // цепочка: a < b < c (одна оценка середины)
    And(Box<Node>, Box<Node>),
    Or(Box<Node>, Box<Node>),
    Call(Func, Vec<Node>),
}

#[derive(Clone, Copy, Debug)]
pub enum CmpOp {
    Lt,
    Le,
    Gt,
    Ge,
    Eq,
    Ne,
}

#[derive(Clone, Copy, Debug)]
pub enum Func {
    Min,
    Max,
    Abs,
    Round,
    Floor,
    Ceil,
    Sqrt,
    Clamp,
    Where,
    Div,
}

fn func_by_name(s: &str) -> Option<Func> {
    Some(match s {
        "min" => Func::Min,
        "max" => Func::Max,
        "abs" => Func::Abs,
        "round" => Func::Round,
        "floor" => Func::Floor,
        "ceil" => Func::Ceil,
        "sqrt" => Func::Sqrt,
        "clamp" => Func::Clamp,
        "where" => Func::Where,
        "div" => Func::Div,
        _ => return None,
    })
}

// ---------- Парсер (приоритеты как в Python) ----------

struct P {
    toks: Vec<Tok>,
    pos: usize,
    depth: i64,
}

const MAX_PARSE_DEPTH: i64 = 500; // защита стека рекурсии парсера; смысловая граница — глубина AST в parse()

impl P {
    fn peek(&self) -> Option<&Tok> {
        self.toks.get(self.pos)
    }
    fn eat_op(&mut self, op: &str) -> bool {
        if matches!(self.peek(), Some(Tok::Op(o)) if o == op) {
            self.pos += 1;
            true
        } else {
            false
        }
    }
    fn enter(&mut self) -> Result<(), ExprError> {
        self.depth += 1;
        if self.depth > MAX_PARSE_DEPTH {
            return err(format!("вложенность выражения больше {MAX_EXPR_DEPTH}"));
        }
        Ok(())
    }
    fn leave(&mut self) {
        self.depth -= 1;
    }

    fn expr(&mut self) -> Result<Node, ExprError> {
        self.enter()?;
        let r = self.or_expr();
        self.leave();
        r
    }

    fn or_expr(&mut self) -> Result<Node, ExprError> {
        let mut left = self.and_expr()?;
        while self.eat_op_keyword("or") {
            let right = self.and_expr()?;
            left = Node::Or(Box::new(left), Box::new(right));
        }
        Ok(left)
    }
    fn eat_op_keyword(&mut self, kw: &str) -> bool {
        if matches!(self.peek(), Some(Tok::Ident(s)) if s == kw) {
            self.pos += 1;
            true
        } else {
            false
        }
    }

    fn and_expr(&mut self) -> Result<Node, ExprError> {
        let mut left = self.cmp_expr()?;
        while self.eat_op_keyword("and") {
            let right = self.cmp_expr()?;
            left = Node::And(Box::new(left), Box::new(right));
        }
        Ok(left)
    }

    fn cmp_expr(&mut self) -> Result<Node, ExprError> {
        let first = self.arith()?;
        let mut ops = Vec::new();
        let mut operands = vec![first];
        loop {
            let op = match self.peek() {
                Some(Tok::Op(o)) => match o.as_str() {
                    "<" => CmpOp::Lt,
                    "<=" => CmpOp::Le,
                    ">" => CmpOp::Gt,
                    ">=" => CmpOp::Ge,
                    "==" => CmpOp::Eq,
                    "!=" => CmpOp::Ne,
                    _ => break,
                },
                _ => break,
            };
            self.pos += 1;
            ops.push(op);
            operands.push(self.arith()?);
        }
        if ops.is_empty() {
            Ok(operands.pop().unwrap())
        } else {
            Ok(Node::Cmp(ops, operands))
        }
    }

    fn arith(&mut self) -> Result<Node, ExprError> {
        let mut left = self.term()?;
        loop {
            if self.eat_op("+") {
                left = Node::Bin('+', Box::new(left), Box::new(self.term()?));
            } else if self.eat_op("-") {
                left = Node::Bin('-', Box::new(left), Box::new(self.term()?));
            } else {
                return Ok(left);
            }
        }
    }

    fn term(&mut self) -> Result<Node, ExprError> {
        let mut left = self.unary()?;
        loop {
            if self.eat_op("*") {
                left = Node::Bin('*', Box::new(left), Box::new(self.unary()?));
            } else if self.eat_op("/") {
                left = Node::Bin('/', Box::new(left), Box::new(self.unary()?));
            } else if self.eat_op("//") {
                left = Node::FloorDiv(Box::new(left), Box::new(self.unary()?));
            } else if self.eat_op("%") {
                left = Node::Mod(Box::new(left), Box::new(self.unary()?));
            } else {
                return Ok(left);
            }
        }
    }

    fn unary(&mut self) -> Result<Node, ExprError> {
        if self.eat_op("-") {
            return Ok(Node::Unary('-', Box::new(self.unary()?)));
        }
        if self.eat_op("+") {
            return Ok(Node::Unary('+', Box::new(self.unary()?)));
        }
        self.power()
    }

    fn power(&mut self) -> Result<Node, ExprError> {
        let base = self.primary()?;
        if self.eat_op("**") {
            // правая часть — полный унарный уровень: 2 ** -1 работает, -2 ** 2 = -(2**2)
            let exp = self.unary()?;
            return Ok(Node::Bin('^', Box::new(base), Box::new(exp)));
        }
        Ok(base)
    }

    fn primary(&mut self) -> Result<Node, ExprError> {
        match self.peek().cloned() {
            Some(Tok::Int(digits)) => {
                self.pos += 1;
                let v: BigInt = digits
                    .parse()
                    .map_err(|_| ExprError::Msg("плохой целый литерал".into()))?;
                Ok(Node::Int(v))
            }
            Some(Tok::Float(v)) => {
                self.pos += 1;
                Ok(Node::Float(v))
            }
            Some(Tok::Ident(name)) => {
                self.pos += 1;
                if self.eat_op("(") {
                    let f = func_by_name(&name).ok_or_else(|| {
                        ExprError::Msg(format!("недопустимый вызов функции в выражении: {name:?}"))
                    })?;
                    let mut args = Vec::new();
                    if !self.eat_op(")") {
                        loop {
                            args.push(self.expr()?);
                            if self.eat_op(",") {
                                continue;
                            }
                            if self.eat_op(")") {
                                break;
                            }
                            return err("ожидалась , или ) в вызове");
                        }
                    }
                    Ok(Node::Call(f, args))
                } else {
                    Ok(Node::Name(name))
                }
            }
            Some(Tok::Op(o)) if o == "(" => {
                self.pos += 1;
                let inner = self.expr()?;
                if !self.eat_op(")") {
                    return err("ожидалась )");
                }
                Ok(inner)
            }
            other => err(format!("неожиданный элемент {other:?}")),
        }
    }
}

// ---------- Разбор и имена ----------

/// Глубина AST без рекурсии — как _depth в Python-версии (глубокое дерево само было бы бомбой).
fn ast_depth(root: &Node) -> i64 {
    let mut deepest = 0i64;
    let mut stack = vec![(root, 1i64)];
    while let Some((n, d)) = stack.pop() {
        deepest = deepest.max(d);
        if d > MAX_EXPR_DEPTH {
            break;
        }
        match n {
            Node::Int(_) | Node::Float(_) | Node::Bool(_) | Node::Name(_) => {}
            Node::Unary(_, a) => stack.push((a.as_ref(), d + 1)),
            Node::Bin(_, a, b) | Node::And(a, b) | Node::Or(a, b) => {
                stack.push((a.as_ref(), d + 1));
                stack.push((b.as_ref(), d + 1));
            }
            Node::FloorDiv(a, b) | Node::Mod(a, b) => {
                stack.push((a.as_ref(), d + 1));
                stack.push((b.as_ref(), d + 1));
            }
            Node::Cmp(_, xs) => {
                for x in xs {
                    stack.push((x, d + 1));
                }
            }
            Node::Call(_, args) => {
                for a in args {
                    stack.push((a, d + 1));
                }
            }
        }
    }
    deepest
}

/// Разобрать и провалидировать выражение (пределы длины/глубины — как в Python-версии).
pub fn parse(expr: &str) -> Result<Node, ExprError> {
    if expr.len() > MAX_EXPR_LEN {
        return err(format!("выражение длиннее {MAX_EXPR_LEN} символов"));
    }
    let toks = lex(expr)?;
    if toks.is_empty() {
        return err(format!("пустое выражение {expr:?}"));
    }
    let mut p = P {
        toks,
        pos: 0,
        depth: 0,
    };
    let node = p.expr()?;
    if p.pos != p.toks.len() {
        return err(format!("лишний текст после выражения: {:?}", &p.toks[p.pos..]));
    }
    if ast_depth(&node) > MAX_EXPR_DEPTH {
        return err(format!("вложенность выражения больше {MAX_EXPR_DEPTH}"));
    }
    Ok(node)
}

/// Множество имён-зависимостей (имена функций не считаются — как в Python-версии).
pub fn names(node: &Node) -> BTreeSet<String> {
    let mut out = BTreeSet::new();
    collect(node, &mut out);
    out
}

fn collect(node: &Node, out: &mut BTreeSet<String>) {
    match node {
        Node::Name(n) => {
            if !FUNCS.contains(&n.as_str()) {
                out.insert(n.clone());
            }
        }
        Node::Int(_) | Node::Float(_) | Node::Bool(_) => {}
        Node::Unary(_, a) | Node::FloorDiv(a, _) | Node::Mod(a, _) => collect(a, out),
        Node::Bin(_, a, b) | Node::And(a, b) | Node::Or(a, b) => {
            collect(a, out);
            collect(b, out);
        }
        Node::Cmp(_, xs) => {
            for x in xs {
                collect(x, out);
            }
        }
        Node::Call(_, args) => {
            for a in args {
                collect(a, out);
            }
        }
    }
}

// ---------- Вычисление ----------

/// Вычислить выражение по словарю значений (проверка имён — до вычисления, как в Python-версии).
pub fn evaluate(node: &Node, values: &dyn Fn(&str) -> Option<Value>) -> Result<Value, ExprError> {
    for n in names(node) {
        if values(&n).is_none() {
            return err(format!("неизвестные имена {:?}", vec![n]));
        }
    }
    ev(node, values)
}

fn py_div(a: f64, b: f64) -> Result<Value, ExprError> {
    if b == 0.0 {
        return err("деление на ноль");
    }
    Ok(Value::Float(a / b))
}

/// Напольное деление как в Python: int//int → int, иначе float с floor.
fn py_floordiv(a: &Value, b: &Value) -> Result<Value, ExprError> {
    if let (Value::Int(x), Value::Int(y)) = (a, b) {
        if y.is_zero() {
            return err("деление на ноль");
        }
        // floor-деление bigint: Rust / режет к нулю — поправляем остатком
        let q = x / y;
        let r = x % y;
        return Ok(Value::Int(if !r.is_zero() && r.is_negative() != y.is_negative() {
            q - BigInt::from(1)
        } else {
            q
        }));
    }
    let (x, y) = (a.as_f64()?, b.as_f64()?);
    if y == 0.0 {
        return err("деление на ноль");
    }
    Ok(Value::Float((x / y).floor()))
}

/// Напольный модуль как в Python: знак делителя.
fn py_mod(a: &Value, b: &Value) -> Result<Value, ExprError> {
    if let (Value::Int(x), Value::Int(y)) = (a, b) {
        if y.is_zero() {
            return err("деление на ноль");
        }
        let r = x % y;
        return Ok(Value::Int(if !r.is_zero() && r.is_negative() != y.is_negative() {
            r + y
        } else {
            r
        }));
    }
    let (x, y) = (a.as_f64()?, b.as_f64()?);
    if y == 0.0 {
        return err("деление на ноль");
    }
    Ok(Value::Float(x - (x / y).floor() * y))
}

/// Возведение в степень с пределами Python-версии: |показатель| ≤ 64, основание конечно и ≤ 1e15.
fn py_pow(a: &Value, b: &Value) -> Result<Value, ExprError> {
    let bf = b.as_f64()?;
    if bf.abs() > MAX_POW_EXP {
        return err(format!(
            "показатель степени {} вне предела ±{}",
            py_float_repr(bf),
            MAX_POW_EXP as i64
        ));
    }
    if let Value::Float(base) = a {
        if !base.is_finite() {
            return err("основание степени должно быть конечным числом");
        }
    }
    let af = a.as_f64()?;
    if af.abs() > MAX_POW_BASE {
        return err(format!(
            "основание степени {} вне предела ±{:.6}",
            py_float_repr(af),
            MAX_POW_BASE
        ));
    }
    // int ** int(неотрицательный показатель) — точный bigint, как int в Python
    if let (Value::Int(x), Value::Int(y)) = (a, b) {
        if !y.is_negative() {
            let e = y
                .to_u32()
                .ok_or_else(|| ExprError::Msg("показатель степени слишком велик".into()))?;
            return Ok(Value::Int(x.pow(e)));
        }
        // отрицательный показатель → float, как в Python
        return Ok(Value::Float(x.to_f64().unwrap_or(f64::NAN).powf(bf)));
    }
    Ok(Value::Float(af.powf(bf)))
}

fn cmp_values(op: CmpOp, a: &Value, b: &Value) -> Result<bool, ExprError> {
    match (a, b) {
        (Value::Str(x), Value::Str(y)) => Ok(match op {
            CmpOp::Lt => x < y,
            CmpOp::Le => x <= y,
            CmpOp::Gt => x > y,
            CmpOp::Ge => x >= y,
            CmpOp::Eq => x == y,
            CmpOp::Ne => x != y,
        }),
        _ => {
            let (x, y) = (a.as_f64()?, b.as_f64()?);
            Ok(match op {
                CmpOp::Lt => x < y,
                CmpOp::Le => x <= y,
                CmpOp::Gt => x > y,
                CmpOp::Ge => x >= y,
                CmpOp::Eq => x == y,
                CmpOp::Ne => x != y,
            })
        }
    }
}

fn ev(node: &Node, values: &dyn Fn(&str) -> Option<Value>) -> Result<Value, ExprError> {
    match node {
        Node::Int(i) => Ok(Value::Int(i.clone())),
        Node::Float(f) => Ok(Value::Float(*f)),
        Node::Bool(b) => Ok(Value::Bool(*b)),
        Node::Name(n) => values(n)
            .ok_or_else(|| ExprError::Msg(format!("неизвестное имя {n:?}"))),
        Node::Unary('-', a) => match ev(a, values)? {
            Value::Int(i) => Ok(Value::Int(-i)),
            Value::Float(f) => Ok(Value::Float(-f)),
            Value::Bool(b) => Ok(Value::Int(-BigInt::from(b as i32))),
            Value::Str(_) => err("унарный минус у строки"),
        },
        Node::Unary('+', a) => match ev(a, values)? {
            Value::Str(_) => err("унарный плюс у строки"),
            other => Ok(other),
        },
        Node::Bin('^', a, b) => py_pow(&ev(a, values)?, &ev(b, values)?), // обе ветви уже вычислены — как у where()
        Node::Bin('+', a, b) => arith('+', &ev(a, values)?, &ev(b, values)?),
        Node::Bin('-', a, b) => arith('-', &ev(a, values)?, &ev(b, values)?),
        Node::Bin('*', a, b) => arith('*', &ev(a, values)?, &ev(b, values)?),
        Node::Bin('/', a, b) => py_div(ev(a, values)?.as_f64()?, ev(b, values)?.as_f64()?),
        Node::FloorDiv(a, b) => py_floordiv(&ev(a, values)?, &ev(b, values)?),
        Node::Mod(a, b) => py_mod(&ev(a, values)?, &ev(b, values)?),
        Node::Cmp(ops, xs) => {
            let mut left = ev(&xs[0], values)?;
            for (op, right) in ops.iter().zip(xs[1..].iter()) {
                let rv = ev(right, values)?;
                if !cmp_values(*op, &left, &rv)? {
                    return Ok(Value::Bool(false));
                }
                left = rv;
            }
            Ok(Value::Bool(true))
        }
        Node::And(a, b) => {
            let x = ev(a, values)?;
            if x.truthy() {
                ev(b, values)
            } else {
                Ok(x)
            }
        }
        Node::Or(a, b) => {
            let x = ev(a, values)?;
            if x.truthy() {
                Ok(x)
            } else {
                ev(b, values)
            }
        }
        Node::Call(f, args) => {
            let mut vals = Vec::with_capacity(args.len());
            for a in args {
                vals.push(ev(a, values)?);
            }
            call(*f, &vals)
        }
        _ => unreachable!("узлы порождаются только парсером этого модуля"),
    }
}

fn arith(op: char, a: &Value, b: &Value) -> Result<Value, ExprError> {
    // bool — подтип int в Python: True + 1 = 2 (int)
    let a = norm_bool(a);
    let b = norm_bool(b);
    // int op int — точный bigint; иначе float (int теряет точность свыше 2^53, как в Python)
    if let (Value::Int(x), Value::Int(y)) = (&a, &b) {
        return match op {
            '+' => Ok(Value::Int(x + y)),
            '-' => Ok(Value::Int(x - y)),
            '*' => Ok(Value::Int(x * y)),
            _ => unreachable!(),
        };
    }
    let (x, y) = (a.as_f64()?, b.as_f64()?);
    Ok(Value::Float(match op {
        '+' => x + y,
        '-' => x - y,
        '*' => x * y,
        _ => unreachable!(),
    }))
}

fn norm_bool(v: &Value) -> Value {
    match v {
        Value::Bool(b) => Value::Int(BigInt::from(*b as i32)),
        other => other.clone(),
    }
}

fn need(args: &[Value], n: usize, name: &str) -> Result<(), ExprError> {
    if args.len() != n {
        return err(format!(
            "{name}() принимает {n} аргумент(ов), получено {}",
            args.len()
        ));
    }
    Ok(())
}

fn call(f: Func, args: &[Value]) -> Result<Value, ExprError> {
    match f {
        // min/max возвращают сам операнд-победитель (int остаётся int, как в Python);
        // один аргумент в Python — TypeError (ожидается iterable)
        Func::Min | Func::Max => {
            if args.len() < 2 {
                return err(format!(
                    "{}() требует не меньше двух аргументов, получено {}",
                    if matches!(f, Func::Min) { "min" } else { "max" },
                    args.len()
                ));
            }
            let mut best = &args[0];
            for v in &args[1..] {
                let (x, y) = (best.as_f64()?, v.as_f64()?);
                let take = if matches!(f, Func::Min) { y < x } else { y > x };
                if take {
                    best = v;
                }
            }
            Ok(best.clone())
        }
        Func::Abs => {
            need(args, 1, "abs")?;
            match &args[0] {
                Value::Int(i) => Ok(Value::Int(i.abs())),
                Value::Float(x) => Ok(Value::Float(x.abs())),
                Value::Bool(b) => Ok(Value::Int(BigInt::from(*b as i32))),
                Value::Str(_) => err("abs() у строки"),
            }
        }
        Func::Round => {
            if args.is_empty() || args.len() > 2 {
                return err(format!(
                    "round() принимает 1 или 2 аргумента, получено {}",
                    args.len()
                ));
            }
            let x = args[0].as_f64()?;
            let n = match args.get(1) {
                Some(v) => v
                    .as_f64()?
                    .to_i32()
                    .ok_or_else(|| ExprError::Msg("n округления слишком велик".into()))?,
                None => 0,
            };
            round_half_up(x, n).map_err(ExprError::Msg)
        }
        Func::Floor | Func::Ceil => {
            need(args, 1, if matches!(f, Func::Floor) { "floor" } else { "ceil" })?;
            let x = args[0].as_f64()?;
            // math.floor/ceil в Python возвращают int; Display f64 всегда без экспоненты,
            // поэтому точное целое читаем прямо из десятичной записи
            if x.is_nan() || x.is_infinite() {
                return err("floor/ceil от нечислового значения");
            }
            let whole = if matches!(f, Func::Floor) { x.floor() } else { x.ceil() };
            let txt = format!("{whole}").replace(".0", "");
            let big: BigInt = txt
                .parse()
                .map_err(|_| ExprError::Msg(format!("{whole} не целое")))?;
            Ok(Value::Int(big))
        }
        Func::Sqrt => {
            need(args, 1, "sqrt")?;
            let x = args[0].as_f64()?;
            if x < 0.0 {
                return err("sqrt от отрицательного числа");
            }
            Ok(Value::Float(x.sqrt()))
        }
        // clamp(x, lo, hi) = max(lo, min(hi, x)) — тоже возвращает операнд
        Func::Clamp => {
            need(args, 3, "clamp")?;
            let inner = if args[2].as_f64()? < args[0].as_f64()? {
                &args[2]
            } else {
                &args[0]
            };
            if args[1].as_f64()? > inner.as_f64()? {
                Ok(args[1].clone())
            } else {
                Ok(inner.clone())
            }
        }
        Func::Where => {
            need(args, 3, "where")?;
            if args[0].truthy() {
                Ok(args[1].clone())
            } else {
                Ok(args[2].clone())
            }
        }
        Func::Div => {
            need(args, 2, "div")?;
            let b = &args[1];
            if !b.truthy() {
                return Ok(Value::Float(0.0));
            }
            py_div(args[0].as_f64()?, b.as_f64()?)
        }
    }
}

/// Отладочная печать разобранного дерева (не используется движком, нужна тестам).
pub fn debug(node: &Node) -> String {
    let mut s = String::new();
    write_node(node, &mut s);
    s
}

fn write_node(node: &Node, s: &mut String) {
    match node {
        Node::Int(i) => {
            let _ = write!(s, "{i}");
        }
        Node::Float(f) => {
            let _ = write!(s, "{}", py_float_repr(*f));
        }
        Node::Bool(b) => {
            let _ = write!(s, "{}", if *b { "True" } else { "False" });
        }
        Node::Name(n) => {
            let _ = write!(s, "{n}");
        }
        Node::Unary(op, a) => {
            let _ = write!(s, "({op}");
            write_node(a, s);
            s.push(')');
        }
        Node::Bin(op, a, b) => {
            s.push('(');
            write_node(a, s);
            let txt = match op {
                '^' => "**",
                other => &other.to_string(),
            };
            let _ = write!(s, " {txt} ");
            write_node(b, s);
            s.push(')');
        }
        Node::FloorDiv(a, b) => {
            s.push('(');
            write_node(a, s);
            s.push_str(" // ");
            write_node(b, s);
            s.push(')');
        }
        Node::Mod(a, b) => {
            s.push('(');
            write_node(a, s);
            s.push_str(" % ");
            write_node(b, s);
            s.push(')');
        }
        Node::Cmp(ops, xs) => {
            s.push('(');
            write_node(&xs[0], s);
            for (op, x) in ops.iter().zip(xs[1..].iter()) {
                let txt = match op {
                    CmpOp::Lt => "<",
                    CmpOp::Le => "<=",
                    CmpOp::Gt => ">",
                    CmpOp::Ge => ">=",
                    CmpOp::Eq => "==",
                    CmpOp::Ne => "!=",
                };
                let _ = write!(s, " {txt} ");
                write_node(x, s);
            }
            s.push(')');
        }
        Node::And(a, b) => {
            s.push('(');
            write_node(a, s);
            s.push_str(" and ");
            write_node(b, s);
            s.push(')');
        }
        Node::Or(a, b) => {
            s.push('(');
            write_node(a, s);
            s.push_str(" or ");
            write_node(b, s);
            s.push(')');
        }
        Node::Call(f, args) => {
            let name = match f {
                Func::Min => "min",
                Func::Max => "max",
                Func::Abs => "abs",
                Func::Round => "round",
                Func::Floor => "floor",
                Func::Ceil => "ceil",
                Func::Sqrt => "sqrt",
                Func::Clamp => "clamp",
                Func::Where => "where",
                Func::Div => "div",
            };
            let _ = write!(s, "{name}(");
            for (i, a) in args.iter().enumerate() {
                if i > 0 {
                    s.push_str(", ");
                }
                write_node(a, s);
            }
            s.push(')');
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    fn eval(expr: &str, vars: &[(&str, Value)]) -> Result<Value, ExprError> {
        let node = parse(expr)?;
        let map: HashMap<String, Value> = vars
            .iter()
            .map(|(k, v)| (k.to_string(), v.clone()))
            .collect();
        evaluate(&node, &|n| map.get(n).cloned())
    }

    fn num(expr: &str, vars: &[(&str, f64)]) -> f64 {
        let vars: Vec<(&str, Value)> = vars
            .iter()
            .map(|(k, v)| (*k, Value::Float(*v)))
            .collect();
        eval(expr, &vars).unwrap().as_f64().unwrap()
    }

    #[test]
    fn arithmetic_python_semantics() {
        assert_eq!(eval("2 + 3 * 4", &[]).unwrap().py_repr(), "14");
        assert_eq!(eval("(a - b) / 2", &[("a", Value::Int(10.into())), ("b", Value::Int(4.into()))]).unwrap().py_repr(), "3.0");
        assert_eq!(eval("-a + 7", &[("a", Value::Int(2.into()))]).unwrap().py_repr(), "5");
        // деление с плавающей точкой
        assert_eq!(num("7 / 2", &[]), 3.5);
        // напольное деление и модуль со знаком делителя
        assert_eq!(eval("7 // 2", &[]).unwrap().py_repr(), "3");
        assert_eq!(eval("-7 // 2", &[]).unwrap().py_repr(), "-4");
        assert_eq!(eval("7 % 3", &[]).unwrap().py_repr(), "1");
        assert_eq!(eval("-7 % 3", &[]).unwrap().py_repr(), "2");
        assert_eq!(num("7.5 // 2", &[]), 3.0);
        assert_eq!(num("-7.5 % 2", &[]), 0.5);
        // приоритет ** выше унарного минуса, правоассоциативность
        assert_eq!(eval("-2 ** 2", &[]).unwrap().py_repr(), "-4");
        assert_eq!(eval("2 ** 3 ** 2", &[]).unwrap().py_repr(), "512");
        assert_eq!(eval("2 ** -1", &[]).unwrap().py_repr(), "0.5");
    }

    #[test]
    fn functions_match_python() {
        assert_eq!(num("round(2.567, 1)", &[]), 2.6);
        assert_eq!(eval("round(2.567, 1)", &[]).unwrap().py_repr(), "2.6");
        assert!(matches!(eval("round(2.5)", &[]).unwrap(), Value::Int(_)));
        assert_eq!(eval("where(x >= 5, x, 0)", &[("x", Value::Int(3.into()))]).unwrap().py_repr(), "0");
        assert_eq!(eval("where(x >= 5, x, 0)", &[("x", Value::Int(7.into()))]).unwrap().py_repr(), "7");
        assert_eq!(num("clamp(15, 0, 10)", &[]), 10.0);
        assert_eq!(num("max(min(3, 5), 1)", &[]), 3.0);
        assert_eq!(eval("floor(2.7)", &[]).unwrap().py_repr(), "2");
        assert_eq!(eval("ceil(2.1)", &[]).unwrap().py_repr(), "3");
        assert_eq!(num("sqrt(4)", &[]), 2.0);
        assert_eq!(num("4 ** 0.5", &[]), 2.0);
        assert_eq!(num("div(7, 0)", &[]), 0.0);
        assert_eq!(num("div(7, 2)", &[]), 3.5);
        // and/or возвращают операнд
        assert_eq!(eval("0 or 5", &[]).unwrap().py_repr(), "5");
        assert_eq!(eval("3 and 5", &[]).unwrap().py_repr(), "5");
        // цепочка сравнений: середина считается один раз
        assert_eq!(eval("1 < 2 < 3", &[]).unwrap().py_repr(), "True");
        assert_eq!(eval("1 < 2 > 5", &[]).unwrap().py_repr(), "False");
    }

    #[test]
    fn names_match_python() {
        let node = parse("a * b + round(c)").unwrap();
        let names = names(&node);
        let v: Vec<&String> = names.iter().collect();
        assert_eq!(v, [&"a".to_string(), &"b".to_string(), &"c".to_string()]);
    }

    #[test]
    fn missing_name_rejected() {
        assert!(eval("a + b", &[("a", Value::Int(1.into()))]).is_err());
    }

    #[test]
    fn rejects_unsafe() {
        for expr in [
            "__import__('os')", // одиночные кавычки — лексер не знает строк
            "().__class__",
            "[1,2][0]",
            "'abc'",
            "lambda: 1",
            "open('/etc/passwd')",
            "round(x, n=1)",
            "x @ y",
            "x | y",
            "not x",
            "x; y",
        ] {
            assert!(parse(expr).is_err(), "должно быть отклонено: {expr}");
        }
    }

    #[test]
    fn security_limits() {
        for expr in ["9**9**9", "2**65", "2**-65", "(2**60)**60**60"] {
            assert!(parse(expr).is_ok(), "разбор допустим: {expr}");
            let node = parse(expr).unwrap();
            assert!(evaluate(&node, &|_| None).is_err(), "вычисление отклонено: {expr}");
        }
        // int ** int с большим, но разрешённым показателем — точный bigint
        assert_eq!(eval("2 ** 60", &[]).unwrap().py_repr(), "1152921504606846976");
        assert!(parse(&format!("1{}", "+1".repeat(300))).is_err());
        assert!(parse(&format!("{}1", "-".repeat(100))).is_err());
        assert!(parse(&(format!("{}1{}", "abs(".repeat(60), ")".repeat(60)))).is_err());
        assert!(parse("1\u{0}+2").is_err());
        // нормальные степени работают
        assert_eq!(eval("x ** 2", &[("x", Value::Int(12.into()))]).unwrap().py_repr(), "144");
        assert_eq!(num("4 ** 0.5", &[]), 2.0);
    }
}
