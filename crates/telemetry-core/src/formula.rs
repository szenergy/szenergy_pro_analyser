use std::collections::{HashMap, HashSet};

#[derive(Debug, Clone, PartialEq)]
enum Token {
    Number(f64),
    Ident(String),
    Plus,
    Minus,
    Star,
    Slash,
    Power, // ** or ^
    LParen,
    RParen,
    Comma,
    Dot,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum MathConst {
    Pi,
    E,
    Nan,
    Inf,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum MathFunc {
    Abs,
    Sqrt,
    Cbrt,
    Exp,
    Log,
    Log10,
    Log2,
    Power,
    Hypot,
    Round,
    Floor,
    Ceil,
    Sign,
    Sin,
    Cos,
    Tan,
    Asin,
    Acos,
    Atan,
    Atan2,
    Deg2Rad,
    Rad2Deg,
    Max,
    Min,
    Clip,
}

impl MathFunc {
    fn from_name(name: &str) -> Option<Self> {
        match name {
            "abs" => Some(Self::Abs),
            "sqrt" => Some(Self::Sqrt),
            "cbrt" => Some(Self::Cbrt),
            "exp" => Some(Self::Exp),
            "log" => Some(Self::Log),
            "log10" => Some(Self::Log10),
            "log2" => Some(Self::Log2),
            "power" | "pow" => Some(Self::Power),
            "hypot" => Some(Self::Hypot),
            "round" => Some(Self::Round),
            "floor" => Some(Self::Floor),
            "ceil" => Some(Self::Ceil),
            "sign" => Some(Self::Sign),
            "sin" => Some(Self::Sin),
            "cos" => Some(Self::Cos),
            "tan" => Some(Self::Tan),
            "arcsin" | "asin" => Some(Self::Asin),
            "arccos" | "acos" => Some(Self::Acos),
            "arctan" | "atan" => Some(Self::Atan),
            "arctan2" | "atan2" => Some(Self::Atan2),
            "deg2rad" => Some(Self::Deg2Rad),
            "rad2deg" => Some(Self::Rad2Deg),
            "maximum" | "max" => Some(Self::Max),
            "minimum" | "min" => Some(Self::Min),
            "clip" => Some(Self::Clip),
            _ => None,
        }
    }

    fn arity(self) -> usize {
        match self {
            Self::Abs
            | Self::Sqrt
            | Self::Cbrt
            | Self::Exp
            | Self::Log
            | Self::Log10
            | Self::Log2
            | Self::Round
            | Self::Floor
            | Self::Ceil
            | Self::Sign
            | Self::Sin
            | Self::Cos
            | Self::Tan
            | Self::Asin
            | Self::Acos
            | Self::Atan
            | Self::Deg2Rad
            | Self::Rad2Deg => 1,
            Self::Power | Self::Hypot | Self::Atan2 | Self::Max | Self::Min => 2,
            Self::Clip => 3,
        }
    }

    fn name(self) -> &'static str {
        match self {
            Self::Abs => "abs",
            Self::Sqrt => "sqrt",
            Self::Cbrt => "cbrt",
            Self::Exp => "exp",
            Self::Log => "log",
            Self::Log10 => "log10",
            Self::Log2 => "log2",
            Self::Power => "power",
            Self::Hypot => "hypot",
            Self::Round => "round",
            Self::Floor => "floor",
            Self::Ceil => "ceil",
            Self::Sign => "sign",
            Self::Sin => "sin",
            Self::Cos => "cos",
            Self::Tan => "tan",
            Self::Asin => "asin",
            Self::Acos => "acos",
            Self::Atan => "atan",
            Self::Atan2 => "atan2",
            Self::Deg2Rad => "deg2rad",
            Self::Rad2Deg => "rad2deg",
            Self::Max => "maximum",
            Self::Min => "minimum",
            Self::Clip => "clip",
        }
    }
}

impl MathConst {
    fn from_name(name: &str) -> Option<Self> {
        match name {
            "pi" => Some(Self::Pi),
            "e" => Some(Self::E),
            "nan" => Some(Self::Nan),
            "inf" => Some(Self::Inf),
            _ => None,
        }
    }

    fn value(self) -> f64 {
        match self {
            Self::Pi => std::f64::consts::PI,
            Self::E => std::f64::consts::E,
            Self::Nan => f64::NAN,
            Self::Inf => f64::INFINITY,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum BinOp {
    Add,
    Sub,
    Mul,
    Div,
    Pow,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum UnaryOp {
    Plus,
    Minus,
}

#[derive(Debug, Clone)]
enum Expr {
    Number(f64),
    Var(String),
    Unary {
        op: UnaryOp,
        expr: Box<Expr>,
    },
    Binary {
        op: BinOp,
        left: Box<Expr>,
        right: Box<Expr>,
    },
    Call {
        func: MathFunc,
        args: Vec<Expr>,
    },
}

fn tokenize(input: &str) -> Result<Vec<Token>, String> {
    let bytes = input.as_bytes();
    let len = bytes.len();
    let mut i = 0;
    let mut tokens = Vec::new();

    while i < len {
        let b = bytes[i];
        if b.is_ascii_whitespace() {
            i += 1;
            continue;
        }

        if b == b'\'' || b == b'"' {
            return Err("String literals are not permitted in formulas.".to_string());
        }

        // Handle prefixed string literals like f"...", b"...", r"..."
        if (b == b'f' || b == b'F' || b == b'b' || b == b'B' || b == b'r' || b == b'R')
            && i + 1 < len
            && (bytes[i + 1] == b'\'' || bytes[i + 1] == b'"')
        {
            return Err("String and byte literals are not permitted in formulas.".to_string());
        }

        // Numbers: starts with ASCII digit or '.' followed by ASCII digit
        if b.is_ascii_digit() || (b == b'.' && i + 1 < len && bytes[i + 1].is_ascii_digit()) {
            let start = i;
            let mut has_dot = false;
            if b == b'.' {
                has_dot = true;
                i += 1;
            }
            while i < len && bytes[i].is_ascii_digit() {
                i += 1;
            }
            if !has_dot && i < len && bytes[i] == b'.' {
                i += 1;
                while i < len && bytes[i].is_ascii_digit() {
                    i += 1;
                }
            }
            // Reject multiple dots in a number (e.g. 1.2.3)
            if i < len && bytes[i] == b'.' {
                return Err(format!("Syntax Error: invalid numeric literal near '{}'", &input[start..=i]));
            }
            if i < len && (bytes[i] == b'e' || bytes[i] == b'E') {
                i += 1;
                if i < len && (bytes[i] == b'+' || bytes[i] == b'-') {
                    i += 1;
                }
                let exp_digits_start = i;
                while i < len && bytes[i].is_ascii_digit() {
                    i += 1;
                }
                if i == exp_digits_start {
                    return Err(format!(
                        "Syntax Error: invalid exponent in numeric literal '{}'",
                        &input[start..i]
                    ));
                }
            }
            // Reject trailing identifier characters directly attached to number (e.g. 12abc)
            if i < len && (bytes[i].is_ascii_alphabetic() || bytes[i] == b'_') {
                return Err(format!(
                    "Syntax Error: invalid numeric literal near '{}'",
                    &input[start..=i]
                ));
            }
            let num_str = &input[start..i];
            let val: f64 = num_str
                .parse()
                .map_err(|_| format!("Syntax Error: invalid numeric literal '{}'", num_str))?;
            tokens.push(Token::Number(val));
            continue;
        }

        // Identifiers
        if b.is_ascii_alphabetic() || b == b'_' {
            let start = i;
            i += 1;
            while i < len && (bytes[i].is_ascii_alphanumeric() || bytes[i] == b'_') {
                i += 1;
            }
            let ident = &input[start..i];
            if ident.starts_with('_') {
                return Err(format!(
                    "Variable name '{}' starting with underscore is not permitted.",
                    ident
                ));
            }
            tokens.push(Token::Ident(ident.to_string()));
            continue;
        }

        match b {
            b'+' => {
                tokens.push(Token::Plus);
                i += 1;
            }
            b'-' => {
                tokens.push(Token::Minus);
                i += 1;
            }
            b'*' => {
                if i + 1 < len && bytes[i + 1] == b'*' {
                    tokens.push(Token::Power);
                    i += 2;
                } else {
                    tokens.push(Token::Star);
                    i += 1;
                }
            }
            b'/' => {
                tokens.push(Token::Slash);
                i += 1;
            }
            b'^' => {
                tokens.push(Token::Power);
                i += 1;
            }
            b'(' => {
                tokens.push(Token::LParen);
                i += 1;
            }
            b')' => {
                tokens.push(Token::RParen);
                i += 1;
            }
            b',' => {
                tokens.push(Token::Comma);
                i += 1;
            }
            b'.' => {
                tokens.push(Token::Dot);
                i += 1;
            }
            _ => {
                let ch = input[i..].chars().next().unwrap_or('?');
                return Err(format!("Syntax Error: unexpected character '{}'", ch));
            }
        }
    }

    Ok(tokens)
}

struct Parser<'a> {
    tokens: &'a [Token],
    pos: usize,
}

impl<'a> Parser<'a> {
    fn new(tokens: &'a [Token]) -> Self {
        Self { tokens, pos: 0 }
    }

    fn peek(&self) -> Option<&Token> {
        self.tokens.get(self.pos)
    }

    fn next(&mut self) -> Option<&Token> {
        let tok = self.tokens.get(self.pos);
        if tok.is_some() {
            self.pos += 1;
        }
        tok
    }

    fn parse_expr(&mut self) -> Result<Expr, String> {
        self.parse_add()
    }

    fn parse_add(&mut self) -> Result<Expr, String> {
        let mut left = self.parse_mul()?;
        while let Some(tok) = self.peek() {
            let op = match tok {
                Token::Plus => BinOp::Add,
                Token::Minus => BinOp::Sub,
                _ => break,
            };
            self.pos += 1;
            let right = self.parse_mul()?;
            left = Expr::Binary {
                op,
                left: Box::new(left),
                right: Box::new(right),
            };
        }
        Ok(left)
    }

    fn parse_mul(&mut self) -> Result<Expr, String> {
        let mut left = self.parse_unary()?;
        while let Some(tok) = self.peek() {
            let op = match tok {
                Token::Star => BinOp::Mul,
                Token::Slash => BinOp::Div,
                _ => break,
            };
            self.pos += 1;
            let right = self.parse_unary()?;
            left = Expr::Binary {
                op,
                left: Box::new(left),
                right: Box::new(right),
            };
        }
        Ok(left)
    }

    fn parse_unary(&mut self) -> Result<Expr, String> {
        match self.peek() {
            Some(Token::Plus) => {
                self.pos += 1;
                let expr = self.parse_unary()?;
                Ok(Expr::Unary {
                    op: UnaryOp::Plus,
                    expr: Box::new(expr),
                })
            }
            Some(Token::Minus) => {
                self.pos += 1;
                let expr = self.parse_unary()?;
                Ok(Expr::Unary {
                    op: UnaryOp::Minus,
                    expr: Box::new(expr),
                })
            }
            _ => self.parse_power(),
        }
    }

    // Power binds tighter than unary on the left (-2**2 == -4), and right-associatively
    // calls parse_unary on the right (2**-2 == 0.25, 2**3**2 == 512).
    fn parse_power(&mut self) -> Result<Expr, String> {
        let base = self.parse_primary()?;
        if matches!(self.peek(), Some(Token::Power)) {
            self.pos += 1;
            let exp = self.parse_unary()?;
            Ok(Expr::Binary {
                op: BinOp::Pow,
                left: Box::new(base),
                right: Box::new(exp),
            })
        } else {
            Ok(base)
        }
    }

    fn parse_primary(&mut self) -> Result<Expr, String> {
        match self.next().cloned() {
            Some(Token::Number(n)) => Ok(Expr::Number(n)),
            Some(Token::LParen) => {
                let expr = self.parse_expr()?;
                match self.next() {
                    Some(Token::RParen) => Ok(expr),
                    _ => Err("Syntax Error: expected closing ')'".to_string()),
                }
            }
            Some(Token::Ident(ident)) => {
                // Handle `np.<member>` or reject attribute access on other identifiers
                if matches!(self.peek(), Some(Token::Dot)) {
                    self.pos += 1;
                    let member = match self.next().cloned() {
                        Some(Token::Ident(m)) => m,
                        _ => {
                            return Err(format!(
                                "Syntax Error: expected attribute name after '{}.'",
                                ident
                            ))
                        }
                    };
                    if ident != "np" {
                        return Err(format!(
                            "Attribute access '{}.{}' is not permitted in formulas.",
                            ident, member
                        ));
                    }
                    // Reject chained attribute access like np.linalg.norm
                    if matches!(self.peek(), Some(Token::Dot)) {
                        return Err(format!(
                            "Nested attribute access 'np.{}...' is not permitted in formulas.",
                            member
                        ));
                    }
                    return self.resolve_np_member(&member);
                }

                if ident == "np" {
                    return Err("'np' module cannot be used as a numeric value.".to_string());
                }

                // Function call
                if matches!(self.peek(), Some(Token::LParen)) {
                    let func = MathFunc::from_name(&ident)
                        .ok_or_else(|| format!("Unknown function '{}'", ident))?;
                    return self.parse_call(func);
                }

                // Constant or Variable
                if let Some(c) = MathConst::from_name(&ident) {
                    return Ok(Expr::Number(c.value()));
                }
                if MathFunc::from_name(&ident).is_some() {
                    return Err(format!(
                        "Syntax Error: function '{}' must be called with parentheses",
                        ident
                    ));
                }
                Ok(Expr::Var(ident))
            }
            Some(other) => Err(format!("Syntax Error: unexpected token '{:?}'", other)),
            None => Err("Syntax Error: unexpected end of formula".to_string()),
        }
    }

    fn resolve_np_member(&mut self, member: &str) -> Result<Expr, String> {
        if matches!(self.peek(), Some(Token::LParen)) {
            let func = MathFunc::from_name(member)
                .ok_or_else(|| format!("Unknown function 'np.{}'", member))?;
            self.parse_call(func)
        } else if let Some(c) = MathConst::from_name(member) {
            Ok(Expr::Number(c.value()))
        } else if MathFunc::from_name(member).is_some() {
            Err(format!(
                "Syntax Error: function 'np.{}' must be called with parentheses",
                member
            ))
        } else {
            Err(format!("Unknown numpy member 'np.{}'", member))
        }
    }

    fn parse_call(&mut self, func: MathFunc) -> Result<Expr, String> {
        // Consume '('
        match self.next() {
            Some(Token::LParen) => {}
            _ => return Err("Syntax Error: expected '('".to_string()),
        }

        let mut args = Vec::new();
        if !matches!(self.peek(), Some(Token::RParen)) {
            loop {
                args.push(self.parse_expr()?);
                match self.peek() {
                    Some(Token::Comma) => {
                        self.pos += 1;
                    }
                    Some(Token::RParen) => break,
                    _ => {
                        return Err(format!(
                            "Syntax Error: expected ',' or ')' in call to '{}'",
                            func.name()
                        ))
                    }
                }
            }
        }
        // Consume ')'
        self.pos += 1;

        let expected_arity = func.arity();
        if args.len() != expected_arity {
            return Err(format!(
                "Function '{}' expects {} argument(s), got {}",
                func.name(),
                expected_arity,
                args.len()
            ));
        }

        Ok(Expr::Call { func, args })
    }
}

fn parse_formula(formula: &str) -> Result<Expr, String> {
    let trimmed = formula.trim();
    if trimmed.is_empty() {
        return Err("Formula cannot be empty.".to_string());
    }
    let tokens = tokenize(trimmed)?;
    let mut parser = Parser::new(&tokens);
    let expr = parser.parse_expr()?;
    if parser.pos < tokens.len() {
        return Err(format!(
            "Syntax Error: unexpected trailing token '{:?}'",
            tokens[parser.pos]
        ));
    }
    Ok(expr)
}

fn collect_vars(expr: &Expr, seen: &mut HashSet<String>, out: &mut Vec<String>) {
    match expr {
        Expr::Number(_) => {}
        Expr::Var(name) => {
            if seen.insert(name.clone()) {
                out.push(name.clone());
            }
        }
        Expr::Unary { expr, .. } => collect_vars(expr, seen, out),
        Expr::Binary { left, right, .. } => {
            collect_vars(left, seen, out);
            collect_vars(right, seen, out);
        }
        Expr::Call { args, .. } => {
            for arg in args {
                collect_vars(arg, seen, out);
            }
        }
    }
}

pub fn extract_variables(formula: &str) -> Result<Vec<String>, String> {
    if formula.trim().is_empty() {
        return Ok(Vec::new());
    }
    let expr = parse_formula(formula)?;
    let mut seen = HashSet::new();
    let mut vars = Vec::new();
    collect_vars(&expr, &mut seen, &mut vars);
    Ok(vars)
}

pub fn validate_formula(formula: &str, expected_vars: Option<&[String]>) -> Result<(), String> {
    let expr = parse_formula(formula)?;
    if let Some(expected) = expected_vars {
        let mut seen = HashSet::new();
        let mut used = Vec::new();
        collect_vars(&expr, &mut seen, &mut used);
        for var in used {
            if !expected.iter().any(|e| e == &var) {
                return Err(format!(
                    "Unknown variable '{}'. Only defined inputs and standard math functions are allowed.",
                    var
                ));
            }
        }
    }
    Ok(())
}

enum EvalVal {
    Scalar(f64),
    Array(Vec<f64>),
}

#[inline]
fn np_sign(x: f64) -> f64 {
    if x.is_nan() {
        f64::NAN
    } else if x > 0.0 {
        1.0
    } else if x < 0.0 {
        -1.0
    } else {
        0.0
    }
}

#[inline]
fn np_max(a: f64, b: f64) -> f64 {
    if a.is_nan() || b.is_nan() {
        f64::NAN
    } else if a >= b {
        a
    } else {
        b
    }
}

#[inline]
fn np_min(a: f64, b: f64) -> f64 {
    if a.is_nan() || b.is_nan() {
        f64::NAN
    } else if a <= b {
        a
    } else {
        b
    }
}

#[inline]
fn np_clip(x: f64, lo: f64, hi: f64) -> f64 {
    if x.is_nan() || lo.is_nan() || hi.is_nan() {
        f64::NAN
    } else {
        let clamped_lo = if x < lo { lo } else { x };
        if clamped_lo > hi {
            hi
        } else {
            clamped_lo
        }
    }
}

#[inline]
fn apply_unary_scalar(op: UnaryOp, v: f64) -> f64 {
    match op {
        UnaryOp::Plus => v,
        UnaryOp::Minus => -v,
    }
}

#[inline]
fn apply_bin_scalar(op: BinOp, l: f64, r: f64) -> f64 {
    match op {
        BinOp::Add => l + r,
        BinOp::Sub => l - r,
        BinOp::Mul => l * r,
        BinOp::Div => l / r,
        BinOp::Pow => l.powf(r),
    }
}

#[inline]
fn apply_func1_scalar(func: MathFunc, x: f64) -> f64 {
    match func {
        MathFunc::Abs => x.abs(),
        MathFunc::Sqrt => x.sqrt(),
        MathFunc::Cbrt => x.cbrt(),
        MathFunc::Exp => x.exp(),
        MathFunc::Log => x.ln(),
        MathFunc::Log10 => x.log10(),
        MathFunc::Log2 => x.log2(),
        MathFunc::Round => x.round(),
        MathFunc::Floor => x.floor(),
        MathFunc::Ceil => x.ceil(),
        MathFunc::Sign => np_sign(x),
        MathFunc::Sin => x.sin(),
        MathFunc::Cos => x.cos(),
        MathFunc::Tan => x.tan(),
        MathFunc::Asin => x.asin(),
        MathFunc::Acos => x.acos(),
        MathFunc::Atan => x.atan(),
        MathFunc::Deg2Rad => x.to_radians(),
        MathFunc::Rad2Deg => x.to_degrees(),
        _ => unreachable!(),
    }
}

#[inline]
fn apply_func2_scalar(func: MathFunc, a: f64, b: f64) -> f64 {
    match func {
        MathFunc::Power => a.powf(b),
        MathFunc::Hypot => a.hypot(b),
        MathFunc::Atan2 => a.atan2(b),
        MathFunc::Max => np_max(a, b),
        MathFunc::Min => np_min(a, b),
        _ => unreachable!(),
    }
}

fn eval_expr(
    expr: &Expr,
    inputs: &HashMap<String, &[f64]>,
    target_len: usize,
) -> Result<EvalVal, String> {
    match expr {
        Expr::Number(n) => Ok(EvalVal::Scalar(*n)),
        Expr::Var(name) => {
            let slice = inputs.get(name).ok_or_else(|| {
                format!("Unknown variable '{}'.", name)
            })?;
            if target_len == 0 {
                return Ok(EvalVal::Array(Vec::new()));
            }
            if slice.is_empty() {
                return Err(format!("Input array for variable '{}' is empty.", name));
            }
            if slice.len() == 1 {
                Ok(EvalVal::Scalar(slice[0]))
            } else if slice.len() == target_len {
                Ok(EvalVal::Array(slice.to_vec()))
            } else {
                Err(format!(
                    "Mismatched input length for variable '{}': expected {}, got {}",
                    name,
                    target_len,
                    slice.len()
                ))
            }
        }
        Expr::Unary { op, expr } => {
            let val = eval_expr(expr, inputs, target_len)?;
            match val {
                EvalVal::Scalar(s) => Ok(EvalVal::Scalar(apply_unary_scalar(*op, s))),
                EvalVal::Array(mut arr) => {
                    if *op == UnaryOp::Minus {
                        for x in &mut arr {
                            *x = -*x;
                        }
                    }
                    Ok(EvalVal::Array(arr))
                }
            }
        }
        Expr::Binary { op, left, right } => {
            let lval = eval_expr(left, inputs, target_len)?;
            let rval = eval_expr(right, inputs, target_len)?;
            match (lval, rval) {
                (EvalVal::Scalar(l), EvalVal::Scalar(r)) => {
                    Ok(EvalVal::Scalar(apply_bin_scalar(*op, l, r)))
                }
                (EvalVal::Array(mut la), EvalVal::Scalar(r)) => {
                    for x in &mut la {
                        *x = apply_bin_scalar(*op, *x, r);
                    }
                    Ok(EvalVal::Array(la))
                }
                (EvalVal::Scalar(l), EvalVal::Array(mut ra)) => {
                    for x in &mut ra {
                        *x = apply_bin_scalar(*op, l, *x);
                    }
                    Ok(EvalVal::Array(ra))
                }
                (EvalVal::Array(mut la), EvalVal::Array(ra)) => {
                    for (x, r) in la.iter_mut().zip(ra.iter()) {
                        *x = apply_bin_scalar(*op, *x, *r);
                    }
                    Ok(EvalVal::Array(la))
                }
            }
        }
        Expr::Call { func, args } => match func.arity() {
            1 => {
                let v = eval_expr(&args[0], inputs, target_len)?;
                match v {
                    EvalVal::Scalar(s) => Ok(EvalVal::Scalar(apply_func1_scalar(*func, s))),
                    EvalVal::Array(mut arr) => {
                        for x in &mut arr {
                            *x = apply_func1_scalar(*func, *x);
                        }
                        Ok(EvalVal::Array(arr))
                    }
                }
            }
            2 => {
                let a = eval_expr(&args[0], inputs, target_len)?;
                let b = eval_expr(&args[1], inputs, target_len)?;
                match (a, b) {
                    (EvalVal::Scalar(x), EvalVal::Scalar(y)) => {
                        Ok(EvalVal::Scalar(apply_func2_scalar(*func, x, y)))
                    }
                    (EvalVal::Array(mut xa), EvalVal::Scalar(y)) => {
                        for x in &mut xa {
                            *x = apply_func2_scalar(*func, *x, y);
                        }
                        Ok(EvalVal::Array(xa))
                    }
                    (EvalVal::Scalar(x), EvalVal::Array(mut ya)) => {
                        for y in &mut ya {
                            *y = apply_func2_scalar(*func, x, *y);
                        }
                        Ok(EvalVal::Array(ya))
                    }
                    (EvalVal::Array(mut xa), EvalVal::Array(ya)) => {
                        for (x, y) in xa.iter_mut().zip(ya.iter()) {
                            *x = apply_func2_scalar(*func, *x, *y);
                        }
                        Ok(EvalVal::Array(xa))
                    }
                }
            }
            3 => {
                // clip(x, lo, hi)
                let vx = eval_expr(&args[0], inputs, target_len)?;
                let vlo = eval_expr(&args[1], inputs, target_len)?;
                let vhi = eval_expr(&args[2], inputs, target_len)?;

                match (vx, vlo, vhi) {
                    (EvalVal::Scalar(x), EvalVal::Scalar(lo), EvalVal::Scalar(hi)) => {
                        Ok(EvalVal::Scalar(np_clip(x, lo, hi)))
                    }
                    (EvalVal::Array(mut xa), EvalVal::Scalar(lo), EvalVal::Scalar(hi)) => {
                        for x in &mut xa {
                            *x = np_clip(*x, lo, hi);
                        }
                        Ok(EvalVal::Array(xa))
                    }
                    (vx, vlo, vhi) => {
                        let mut out = vec![0.0; target_len];
                        let xs = match &vx {
                            EvalVal::Scalar(_) => None,
                            EvalVal::Array(a) => Some(a.as_slice()),
                        };
                        let x_scalar = match &vx {
                            EvalVal::Scalar(s) => *s,
                            _ => 0.0,
                        };
                        let los = match &vlo {
                            EvalVal::Scalar(_) => None,
                            EvalVal::Array(a) => Some(a.as_slice()),
                        };
                        let lo_scalar = match &vlo {
                            EvalVal::Scalar(s) => *s,
                            _ => 0.0,
                        };
                        let his = match &vhi {
                            EvalVal::Scalar(_) => None,
                            EvalVal::Array(a) => Some(a.as_slice()),
                        };
                        let hi_scalar = match &vhi {
                            EvalVal::Scalar(s) => *s,
                            _ => 0.0,
                        };
                        for i in 0..target_len {
                            let x = xs.map_or(x_scalar, |a| a[i]);
                            let lo = los.map_or(lo_scalar, |a| a[i]);
                            let hi = his.map_or(hi_scalar, |a| a[i]);
                            out[i] = np_clip(x, lo, hi);
                        }
                        Ok(EvalVal::Array(out))
                    }
                }
            }
            _ => unreachable!(),
        },
    }
}

pub fn evaluate_formula(
    formula: &str,
    inputs: &HashMap<String, &[f64]>,
    target_len: usize,
) -> Result<Vec<f64>, String> {
    let expr = parse_formula(formula)?;
    let val = eval_expr(&expr, inputs, target_len)?;
    if target_len == 0 {
        return Ok(Vec::new());
    }
    match val {
        EvalVal::Scalar(s) => Ok(vec![s; target_len]),
        EvalVal::Array(arr) => Ok(arr),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_abs_diff_eq;

    #[test]
    fn test_extract_variables() {
        assert_eq!(extract_variables("").unwrap(), Vec::<String>::new());
        assert_eq!(extract_variables("100.0 + 25.0").unwrap(), Vec::<String>::new());
        assert_eq!(extract_variables("A * 3.6").unwrap(), vec!["A"]);
        assert_eq!(extract_variables("sqrt(A**2 + B**2)").unwrap(), vec!["A", "B"]);
        assert_eq!(
            extract_variables("np.clip(A, 0, 100) + np.abs(D) * np.pi + e").unwrap(),
            vec!["A", "D"]
        );
        assert_eq!(extract_variables("A + B + A").unwrap(), vec!["A", "B"]);
    }

    #[test]
    fn test_validate_formula_valid_and_invalid() {
        let vars = vec!["A".to_string(), "B".to_string()];
        assert!(validate_formula("A * 3.6", Some(&vars)).is_ok());
        assert!(validate_formula("sqrt(A**2 + B**2)", Some(&vars)).is_ok());
        assert!(validate_formula("np.sqrt(A^2 + B^2)", Some(&vars)).is_ok());
        assert!(validate_formula("clip(A, 0, 100)", Some(&vars)).is_ok());

        // Empty
        assert!(validate_formula("", None).is_err());
        assert!(validate_formula("   ", None).is_err());

        // Syntax errors
        assert!(validate_formula("A * +", None).is_err());
        assert!(validate_formula("(A + B", None).is_err());
        assert!(validate_formula("1.2.3", None).is_err());
        assert!(validate_formula("1e", None).is_err());

        // Unknown variables & functions
        assert!(validate_formula("A + B + C", Some(&vars)).is_err());
        assert!(validate_formula("where(A > 0, 1, 0)", Some(&vars)).is_err());
        assert!(validate_formula("where(A, 1, 0)", None).is_err());

        // Disallowed strings and underscore identifiers
        assert!(validate_formula("'hello'", None).is_err());
        assert!(validate_formula("A + \"km/h\"", Some(&vars)).is_err());
        assert!(validate_formula("f\"val: {A}\"", Some(&vars)).is_err());
        assert!(validate_formula("_private + 1", None).is_err());
        assert!(validate_formula("A._private_attr", Some(&vars)).is_err());
        assert!(validate_formula("A.foo", Some(&vars)).is_err());
        assert!(validate_formula("np._secret(A)", Some(&vars)).is_err());
        assert!(validate_formula("[1, 2, 3]", None).is_err());

        // Arity errors
        assert!(validate_formula("sqrt(A, B)", Some(&vars)).is_err());
        assert!(validate_formula("clip(A, 0)", Some(&vars)).is_err());
        assert!(validate_formula("sqrt + 1", Some(&vars)).is_err());
    }

    #[test]
    fn test_evaluate_arithmetic_and_precedence() {
        let a = [10.0, 20.0, 30.0];
        let b = [2.0, 4.0, 5.0];
        let mut inputs = HashMap::new();
        inputs.insert("A".to_string(), a.as_slice());
        inputs.insert("B".to_string(), b.as_slice());

        let res = evaluate_formula("A + B * 2", &inputs, 3).unwrap();
        assert_abs_diff_eq!(res.as_slice(), [14.0, 28.0, 40.0].as_slice());

        // Right-associative power and unary precedence
        let two = [2.0];
        let mut pow_inputs = HashMap::new();
        pow_inputs.insert("A".to_string(), two.as_slice());
        let r1 = evaluate_formula("A ** 3 ** 2", &pow_inputs, 1).unwrap();
        assert_abs_diff_eq!(r1[0], 512.0);
        let r2 = evaluate_formula("A ^ 3 ^ 2", &pow_inputs, 1).unwrap();
        assert_abs_diff_eq!(r2[0], 512.0);
        let r3 = evaluate_formula("-A ** 2", &pow_inputs, 1).unwrap();
        assert_abs_diff_eq!(r3[0], -4.0);
        let r4 = evaluate_formula("(-A) ** 2", &pow_inputs, 1).unwrap();
        assert_abs_diff_eq!(r4[0], 4.0);
        let r5 = evaluate_formula("A ** -2", &pow_inputs, 1).unwrap();
        assert_abs_diff_eq!(r5[0], 0.25);

        // Scientific notation
        let s = evaluate_formula("1.5e-3 * 1000", &HashMap::new(), 2).unwrap();
        assert_abs_diff_eq!(s.as_slice(), [1.5, 1.5].as_slice());
    }

    #[test]
    fn test_evaluate_math_functions_and_np_aliases() {
        let a = [9.0, 16.0, 25.0];
        let b = [-5.0, 0.0, 15.0];
        let mut inputs = HashMap::new();
        inputs.insert("A".to_string(), a.as_slice());
        inputs.insert("B".to_string(), b.as_slice());

        let r_sqrt = evaluate_formula("np.sqrt(A)", &inputs, 3).unwrap();
        assert_abs_diff_eq!(r_sqrt.as_slice(), [3.0, 4.0, 5.0].as_slice());

        let r_sign = evaluate_formula("np.sign(B)", &inputs, 3).unwrap();
        assert_abs_diff_eq!(r_sign.as_slice(), [-1.0, 0.0, 1.0].as_slice());

        let r_clip = evaluate_formula("np.clip(B, -2, 8)", &inputs, 3).unwrap();
        assert_abs_diff_eq!(r_clip.as_slice(), [-2.0, 0.0, 8.0].as_slice());

        let r_max = evaluate_formula("np.maximum(A, 15)", &inputs, 3).unwrap();
        assert_abs_diff_eq!(r_max.as_slice(), [15.0, 16.0, 25.0].as_slice());

        let r_min = evaluate_formula("min(A, 15)", &inputs, 3).unwrap();
        assert_abs_diff_eq!(r_min.as_slice(), [9.0, 15.0, 15.0].as_slice());

        let r_trig = evaluate_formula("sin(deg2rad(90)) + cos(0) + rad2deg(pi)", &HashMap::new(), 1).unwrap();
        assert_abs_diff_eq!(r_trig[0], 182.0, epsilon = 1e-10);

        let r_more = evaluate_formula(
            "cbrt(27) + exp(0) + log(e) + log10(100) + log2(8) + power(2, 3) + pow(3, 2) + hypot(3, 4) + round(2.6) + floor(2.9) + ceil(2.1) + tan(0) + arcsin(0) + arccos(1) + arctan(0) + arctan2(1, 1) * 0",
            &HashMap::new(),
            1,
        )
        .unwrap();
        assert_abs_diff_eq!(r_more[0], 3.0 + 1.0 + 1.0 + 2.0 + 3.0 + 8.0 + 9.0 + 5.0 + 3.0 + 2.0 + 3.0, epsilon = 1e-10);
    }

    #[test]
    fn test_zero_division_and_scalar_broadcast() {
        let a = [10.0, 0.0, -20.0];
        let b = [0.0, 0.0, 2.0];
        let mut inputs = HashMap::new();
        inputs.insert("A".to_string(), a.as_slice());
        inputs.insert("B".to_string(), b.as_slice());

        let res = evaluate_formula("A / B", &inputs, 3).unwrap();
        assert!(res[0].is_infinite() && res[0].is_sign_positive());
        assert!(res[1].is_nan());
        assert_abs_diff_eq!(res[2], -10.0);

        let scalar = evaluate_formula("pi * 2", &HashMap::new(), 4).unwrap();
        assert_eq!(scalar.len(), 4);
        assert_abs_diff_eq!(scalar[0], std::f64::consts::TAU);
        assert_abs_diff_eq!(scalar[3], std::f64::consts::TAU);
    }
}
