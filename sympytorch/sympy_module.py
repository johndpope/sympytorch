import functools as ft
import sympy
import torch


def _reduce(fn):
    def fn_(*args):
        return ft.reduce(fn, args)
    return fn_


_func_lookup = {
    sympy.Mul: _reduce(torch.mul),
    sympy.Add: _reduce(torch.add),
    sympy.div: torch.div,
    sympy.Abs: torch.abs,
    sympy.sign: torch.sign,
    # Note: May raise error for ints.
    sympy.ceiling: torch.ceil,
    sympy.floor: torch.floor,
    sympy.log: torch.log,
    sympy.exp: torch.exp,
    sympy.sqrt: torch.sqrt,
    sympy.cos: torch.cos,
    sympy.acos: torch.acos,
    sympy.sin: torch.sin,
    sympy.asin: torch.asin,
    sympy.tan: torch.tan,
    sympy.atan: torch.atan,
    sympy.atan2: torch.atan2,
    # Note: Also may give NaN for complex results.
    sympy.cosh: torch.cosh,
    sympy.acosh: torch.acosh,
    sympy.sinh: torch.sinh,
    sympy.asinh: torch.asinh,
    sympy.tanh: torch.tanh,
    sympy.atanh: torch.atanh,
    sympy.Pow: torch.pow,
    sympy.re: torch.real,
    sympy.im: torch.imag,
    sympy.arg: torch.angle,
    # Note: May raise error for ints and complexes
    sympy.erf: torch.erf,
    sympy.loggamma: torch.lgamma,
    sympy.Eq: torch.eq,
    sympy.Ne: torch.ne,
    sympy.StrictGreaterThan: torch.gt,
    sympy.StrictLessThan: torch.lt,
    sympy.LessThan: torch.le,
    sympy.GreaterThan: torch.ge,
    sympy.And: torch.logical_and,
    sympy.Or: torch.logical_or,
    sympy.Not: torch.logical_not,
    sympy.Max: torch.max,
    sympy.Min: torch.min,
    # Matrices
    sympy.MatAdd: torch.add,
    sympy.HadamardProduct: torch.mul,
    sympy.Trace: torch.trace,
    # Note: May raise error for integer matrices.
    sympy.Determinant: torch.det,
}


class _Node(torch.nn.Module):
    def __init__(self, *, expr, _memodict, **kwargs):
        super().__init__(**kwargs)

        if issubclass(expr.func, sympy.Float):
            self._node_type = sympy.Float
            self._value = torch.nn.Parameter(torch.tensor(float(expr)))
            self._func = lambda: self._value
            self._args = ()
        elif issubclass(expr.func, sympy.Integer):
            # Can get here if expr is one of the Integer special cases,
            # e.g. NegativeOne
            self._node_type = sympy.Integer
            self._value = int(expr)
            self._func = lambda: self._value
            self._args = ()
        elif issubclass(expr.func, sympy.Symbol):
            self._node_type = sympy.Symbol
            self._name = expr.name
            self._func = lambda value: value
            self._args = ((lambda memodict: memodict[expr.name]),)
        else:
            self._node_type = expr.func
            self._func = _func_lookup[expr.func]
            args = []
            for arg in expr.args:
                try:
                    arg_ = _memodict[arg]
                except KeyError:
                    arg_ = type(self)(expr=arg, _memodict=_memodict)
                    _memodict[arg] = arg_
                args.append(arg_)
            self._args = torch.nn.ModuleList(args)

    def sympy(self, _memodict):
        if issubclass(self._node_type, sympy.Float):
            return self._node_type(self._value.item())
        elif issubclass(self._node_type, sympy.Integer):
            return self._node_type(self._value)
        elif issubclass(self._node_type, sympy.Symbol):
            return self._node_type(self._name)
        else:
            args = []
            for arg in self._args:
                try:
                    arg_ = _memodict[arg]
                except KeyError:
                    arg_ = arg.sympy(_memodict)
                    _memodict[arg] = arg_
                args.append(arg_)
            return self._node_type(*args)

    def forward(self, memodict):
        args = []
        for arg in self._args:
            try:
                arg_ = memodict[arg]
            except KeyError:
                arg_ = arg(memodict)
                memodict[arg] = arg_
            args.append(arg_)
        return self._func(*args)


class SymPyModule(torch.nn.Module):
    def __init__(self, *, expressions, **kwargs):
        super().__init__(**kwargs)

        _memodict = {}
        self._nodes = torch.nn.ModuleList(
            [_Node(expr=expr, _memodict=_memodict) for expr in expressions]
        )

    def sympy(self):
        _memodict = {}
        return [node.sympy(_memodict) for node in self._nodes]

    def forward(self, **symbols):
        return torch.stack([node(symbols) for node in self._nodes], dim=-1)

