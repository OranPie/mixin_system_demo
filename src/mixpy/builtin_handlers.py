from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional, Tuple

from .model import TYPE, At
from .handlers import Match, register_handler
from .registry import InjectorSpec
from .location_utils import _dotted_name_from_attribute
from .selector import CallSelector

def _self_expr(fn: ast.FunctionDef) -> ast.expr:
    if fn.args.args:
        return ast.Name(id=fn.args.args[0].arg, ctx=ast.Load())
    return ast.Constant(value=None)

def _fn_pos_args(fn: ast.FunctionDef) -> List[ast.arg]:
    return list(fn.args.posonlyargs) + list(fn.args.args)

def _fn_user_args_exprs(fn: ast.FunctionDef) -> List[ast.expr]:
    args = _fn_pos_args(fn)
    if args and args[0].arg == "self":
        args = args[1:]
    return [ast.Name(id=a.arg, ctx=ast.Load()) for a in args]

def _build_args_list_expr(fn: ast.FunctionDef) -> ast.expr:
    elts: List[ast.expr] = _fn_user_args_exprs(fn)
    if fn.args.vararg is not None:
        elts.append(ast.Starred(value=ast.Call(func=ast.Name(id="list", ctx=ast.Load()),
                                               args=[ast.Name(id=fn.args.vararg.arg, ctx=ast.Load())],
                                               keywords=[]),
                                ctx=ast.Load()))
    return ast.List(elts=elts, ctx=ast.Load())

def _build_kwargs_dict_expr(fn: ast.FunctionDef) -> ast.expr:
    if fn.args.kwarg is not None:
        return ast.Call(func=ast.Name(id="dict", ctx=ast.Load()),
                        args=[ast.Name(id=fn.args.kwarg.arg, ctx=ast.Load())],
                        keywords=[])
    return ast.Dict(keys=[], values=[])

def _dispatch_call_args_for_fn(fn: ast.FunctionDef) -> Tuple[List[ast.expr], List[ast.keyword]]:
    # positional: self, then user args, then *vararg if present
    args: List[ast.expr] = [_self_expr(fn), *_fn_user_args_exprs(fn)]
    if fn.args.vararg is not None:
        args.append(ast.Starred(value=ast.Name(id=fn.args.vararg.arg, ctx=ast.Load()), ctx=ast.Load()))
    keywords: List[ast.keyword] = []
    if fn.args.kwarg is not None:
        keywords.append(ast.keyword(arg=None, value=ast.Name(id=fn.args.kwarg.arg, ctx=ast.Load())))
    return args, keywords

def _inj_key(target: str, method: str, type_name: str, at_name: Any) -> ast.Tuple:
    return ast.Tuple(elts=[
        ast.Constant(value=target),
        ast.Constant(value=method),
        ast.Constant(value=type_name),
        ast.Constant(value=str(at_name)),
    ], ctx=ast.Load())

def _get_injectors_call(target: str, method: str, type_name: str, at_name: Any) -> ast.Call:
    return ast.Call(
        func=ast.Attribute(value=ast.Name(id="__mixin_injectors__", ctx=ast.Load()), attr="get", ctx=ast.Load()),
        args=[_inj_key(target, method, type_name, at_name), ast.List(elts=[], ctx=ast.Load())],
        keywords=[]
    )

def _mk_ci_ctor(type_member: str, target: str, method: str, at_name: Any) -> ast.Call:
    return ast.Call(
        func=ast.Attribute(value=ast.Name(id="mixpy_runtime", ctx=ast.Load()), attr="CallbackInfo", ctx=ast.Load()),
        args=[],
        keywords=[
            ast.keyword(arg="type", value=ast.Attribute(
                value=ast.Attribute(value=ast.Name(id="mixpy_model", ctx=ast.Load()), attr="TYPE", ctx=ast.Load()),
                attr=type_member, ctx=ast.Load()
            )),
            ast.keyword(arg="target", value=ast.Constant(value=target)),
            ast.keyword(arg="method", value=ast.Constant(value=method)),
            ast.keyword(arg="at_name", value=ast.Constant(value=str(at_name))),
            ast.keyword(arg="trace_id", value=ast.Call(
                func=ast.Name(id="str", ctx=ast.Load()),
                args=[ast.Call(
                    func=ast.Attribute(value=ast.Attribute(value=ast.Name(id="mixpy_runtime", ctx=ast.Load()), attr="time", ctx=ast.Load()), attr="time_ns", ctx=ast.Load()),
                    args=[], keywords=[]
                )],
                keywords=[]
            )),
        ]
    )

def _mk_dispatch_stmt(injectors_expr: ast.expr, ci_name: str, ctx_expr: ast.expr, cb_args: List[ast.expr], cb_keywords: Optional[List[ast.keyword]] = None, *, is_async: bool = False) -> ast.Expr:
    dispatch_attr = "async_dispatch_injectors" if is_async else "dispatch_injectors"
    call = ast.Call(
        func=ast.Attribute(value=ast.Name(id="mixpy_runtime", ctx=ast.Load()), attr=dispatch_attr, ctx=ast.Load()),
        args=[injectors_expr, ast.Name(id=ci_name, ctx=ast.Load()), ctx_expr, *cb_args],
        keywords=cb_keywords or []
    )
    if is_async:
        return ast.Expr(value=ast.Await(value=call))
    return ast.Expr(value=call)

def _mk_if_cancel_return(ci_name: str) -> ast.If:
    return ast.If(
        test=ast.Attribute(value=ast.Name(id=ci_name, ctx=ast.Load()), attr="is_cancelled", ctx=ast.Load()),
        body=[ast.Return(value=ast.Attribute(value=ast.Name(id=ci_name, ctx=ast.Load()), attr="result", ctx=ast.Load()))],
        orelse=[]
    )

def _mk_if_value_set_assign(ci_name: str, var_name: str) -> ast.If:
    return ast.If(
        test=ast.Attribute(value=ast.Name(id=ci_name, ctx=ast.Load()), attr="value_set", ctx=ast.Load()),
        body=[ast.Assign(targets=[ast.Name(id=var_name, ctx=ast.Store())],
                         value=ast.Attribute(value=ast.Name(id=ci_name, ctx=ast.Load()), attr="new_value", ctx=ast.Load()))],
        orelse=[]
    )

def _mk_if_value_set_return(ci_name: str) -> ast.If:
    return ast.If(
        test=ast.Attribute(value=ast.Name(id=ci_name, ctx=ast.Load()), attr="value_set", ctx=ast.Load()),
        body=[ast.Return(value=ast.Attribute(value=ast.Name(id=ci_name, ctx=ast.Load()), attr="new_value", ctx=ast.Load()))],
        orelse=[]
    )

class HeadHandler:
    type = TYPE.HEAD

    def find(self, fn: ast.FunctionDef, at: At) -> List[Match]:
        return [Match(node=fn.body[0] if fn.body else fn, parent=fn, field="body", index=0, at=at)]

    def instrument(self, fn: ast.FunctionDef, matches: List[Match], injectors: List[InjectorSpec], target: str) -> None:
        if not matches:
            return
        is_async = isinstance(fn, ast.AsyncFunctionDef)
        method = fn.name
        at_name = "HEAD"
        inj_var = "_mixin_inj_head"
        ci_name = "_mixin_ci_head"
        # Fast-path: assign injector list once, skip dispatch when empty
        inj_assign = ast.Assign(
            targets=[ast.Name(id=inj_var, ctx=ast.Store())],
            value=_get_injectors_call(target, method, "HEAD", at_name=at_name),
        )
        ci_assign = ast.Assign(targets=[ast.Name(id=ci_name, ctx=ast.Store())], value=_mk_ci_ctor("HEAD", target, method, at_name))

        ctx = ast.Dict(
            keys=[ast.Constant("self"), ast.Constant("args"), ast.Constant("kwargs"), ast.Constant("locals")],
            values=[
                _self_expr(fn),
                _build_args_list_expr(fn),
                _build_kwargs_dict_expr(fn),
                ast.Call(func=ast.Name(id="locals", ctx=ast.Load()), args=[], keywords=[]),
            ]
        )
        cb_args, cb_keywords = _dispatch_call_args_for_fn(fn)
        dispatch = _mk_dispatch_stmt(ast.Name(id=inj_var, ctx=ast.Load()), ci_name, ctx, cb_args, cb_keywords, is_async=is_async)
        guard = _mk_if_cancel_return(ci_name)
        fast_path_if = ast.If(
            test=ast.Name(id=inj_var, ctx=ast.Load()),
            body=[ci_assign, dispatch, guard],
            orelse=[],
        )
        fn.body.insert(0, fast_path_if)
        fn.body.insert(0, inj_assign)

class ParameterHandler:
    type = TYPE.PARAMETER

    def find(self, fn: ast.FunctionDef, at: At) -> List[Match]:
        out: List[Match] = []
        want = str(at.name)
        for i, a in enumerate(fn.args.args):
            if a.arg == want:
                out.append(Match(node=a, parent=fn.args, field="args", index=i, at=at))
        return out

    def instrument(self, fn: ast.FunctionDef, matches: List[Match], injectors: List[InjectorSpec], target: str) -> None:
        if not matches:
            return
        is_async = isinstance(fn, ast.AsyncFunctionDef)
        method = fn.name

        for m in sorted(matches, key=lambda x: x.index or 0, reverse=True):
            param_name = str(m.at.name)
            inj_var = f"_mixin_inj_param_{param_name}"
            ci_name = f"_mixin_ci_param_{param_name}"
            inj_assign = ast.Assign(
                targets=[ast.Name(id=inj_var, ctx=ast.Store())],
                value=_get_injectors_call(target, method, "PARAMETER", at_name=param_name),
            )
            ci_assign = ast.Assign(targets=[ast.Name(id=ci_name, ctx=ast.Store())], value=_mk_ci_ctor("PARAMETER", target, method, param_name))

            ctx = ast.Dict(
                keys=[ast.Constant("self"), ast.Constant("args"), ast.Constant("kwargs"), ast.Constant("locals"),
                      ast.Constant("param"), ast.Constant("value")],
                values=[
                    _self_expr(fn),
                    _build_args_list_expr(fn),
                    _build_kwargs_dict_expr(fn),
                    ast.Call(func=ast.Name(id="locals", ctx=ast.Load()), args=[], keywords=[]),
                    ast.Constant(param_name),
                    ast.Name(id=param_name, ctx=ast.Load()),
                ]
            )
            # pass the full function signature to injector, like HEAD/TAIL
            cb_args, cb_keywords = _dispatch_call_args_for_fn(fn)
            dispatch = _mk_dispatch_stmt(ast.Name(id=inj_var, ctx=ast.Load()), ci_name, ctx, cb_args, cb_keywords, is_async=is_async)
            guard = _mk_if_cancel_return(ci_name)
            maybe_set = _mk_if_value_set_assign(ci_name, param_name)

            fast_path_if = ast.If(
                test=ast.Name(id=inj_var, ctx=ast.Load()),
                body=[ci_assign, dispatch, guard, maybe_set],
                orelse=[],
            )
            fn.body.insert(0, fast_path_if)
            fn.body.insert(0, inj_assign)

class TailHandler:
    type = TYPE.TAIL

    def find(self, fn: ast.FunctionDef, at: At) -> List[Match]:
        out: List[Match] = []
        class Finder(ast.NodeVisitor):
            def __init__(self): self.parents=[]
            def generic_visit(self, node):
                self.parents.append(node)
                super().generic_visit(node)
                self.parents.pop()
            def visit_Return(self, node: ast.Return):
                parent = self.parents[-1] if self.parents else None
                out.append(Match(node=node, parent=parent, field=None, index=None, at=at))
        Finder().visit(fn)
        return out

    def instrument(self, fn: ast.FunctionDef, matches: List[Match], injectors: List[InjectorSpec], target: str) -> None:
        is_async = isinstance(fn, ast.AsyncFunctionDef)
        method = fn.name
        at_name = "TAIL"
        inj_var = "_mixin_inj_tail"
        inj_assign = ast.Assign(
            targets=[ast.Name(id=inj_var, ctx=ast.Store())],
            value=_get_injectors_call(target, method, "TAIL", at_name=at_name),
        )
        inj_expr = ast.Name(id=inj_var, ctx=ast.Load())
        self_expr = _self_expr(fn)

        class RewriteReturns(ast.NodeTransformer):
            def visit_Return(self, node: ast.Return):
                rv = node.value if node.value is not None else ast.Constant(value=None)
                ci_name = "_mixin_ci_tail"
                ci_assign = ast.Assign(targets=[ast.Name(id=ci_name, ctx=ast.Store())], value=_mk_ci_ctor("TAIL", target, method, at_name))

                ctx = ast.Dict(
                    keys=[ast.Constant("self"), ast.Constant("args"), ast.Constant("kwargs"), ast.Constant("locals"),
                          ast.Constant("return_value"), ast.Constant("value")],
                    values=[
                        self_expr,
                        _build_args_list_expr(fn),
                        _build_kwargs_dict_expr(fn),
                        ast.Call(func=ast.Name(id="locals", ctx=ast.Load()), args=[], keywords=[]),
                        rv,
                        rv,
                    ]
                )
                cb_args, cb_keywords = _dispatch_call_args_for_fn(fn)
                dispatch = _mk_dispatch_stmt(inj_expr, ci_name, ctx, cb_args, cb_keywords, is_async=is_async)
                guard = _mk_if_cancel_return(ci_name)
                value_set_guard = _mk_if_value_set_return(ci_name)
                fast_path_if = ast.If(
                    test=inj_expr,
                    body=[ci_assign, dispatch, guard, value_set_guard],
                    orelse=[],
                )
                return ast.If(test=ast.Constant(value=True), body=[fast_path_if, node], orelse=[])

        fn.body = [RewriteReturns().visit(s) for s in fn.body]
        fn.body.insert(0, inj_assign)

        # implicit tail at end
        ci_name = "_mixin_ci_tail_end"
        ci_assign = ast.Assign(targets=[ast.Name(id=ci_name, ctx=ast.Store())], value=_mk_ci_ctor("TAIL", target, method, at_name))
        ctx = ast.Dict(
            keys=[ast.Constant("self"), ast.Constant("args"), ast.Constant("kwargs"), ast.Constant("locals"),
                  ast.Constant("return_value"), ast.Constant("value")],
            values=[
                self_expr,
                _build_args_list_expr(fn),
                _build_kwargs_dict_expr(fn),
                ast.Call(func=ast.Name(id="locals", ctx=ast.Load()), args=[], keywords=[]),
                ast.Constant(value=None),
                ast.Constant(value=None),
            ]
        )
        cb_args, cb_keywords = _dispatch_call_args_for_fn(fn)
        dispatch = _mk_dispatch_stmt(inj_expr, ci_name, ctx, cb_args, cb_keywords, is_async=is_async)
        guard = _mk_if_cancel_return(ci_name)
        value_set_guard = _mk_if_value_set_return(ci_name)
        fast_path_end = ast.If(
            test=inj_expr,
            body=[ci_assign, dispatch, guard, value_set_guard],
            orelse=[],
        )
        fn.body.append(fast_path_end)

class ConstHandler:
    type = TYPE.CONST

    def find(self, fn: ast.FunctionDef, at: At) -> List[Match]:
        matches: List[Match] = []
        class Finder(ast.NodeVisitor):
            def __init__(self): self.parents=[]
            def generic_visit(self, node):
                self.parents.append(node)
                super().generic_visit(node)
                self.parents.pop()
            def visit_Constant(self, node: ast.Constant):
                if node.value == at.name:
                    parent = self.parents[-1] if self.parents else None
                    matches.append(Match(node=node, parent=parent, field=None, index=None, at=at))
        Finder().visit(fn)
        return matches

    def instrument(self, fn: ast.FunctionDef, matches: List[Match], injectors: List[InjectorSpec], target: str) -> None:
        if not matches:
            return
        at_name = injectors[0].at.name
        method = fn.name
        self_expr = _self_expr(fn)
        match_nodes = {m.node for m in matches}

        class Rewriter(ast.NodeTransformer):
            def visit_Constant(self, node: ast.Constant):
                if node in match_nodes:
                    return ast.Call(
                        func=ast.Attribute(value=ast.Name(id="mixpy_runtime", ctx=ast.Load()), attr="eval_const", ctx=ast.Load()),
                        args=[
                            ast.Name(id="__mixin_injectors__", ctx=ast.Load()),
                            ast.Constant(value=target),
                            ast.Constant(value=method),
                            ast.Constant(value=str(at_name)),
                            self_expr,
                            ast.Constant(value=node.value),
                        ],
                        keywords=[]
                    )
                return node

        fn.body = [Rewriter().visit(s) for s in fn.body]

class InvokeHandler:
    type = TYPE.INVOKE

    def find(self, fn: ast.FunctionDef, at: At) -> List[Match]:
        matches: List[Match] = []

        def call_parts(n: ast.AST) -> Optional[Tuple[str, ...]]:
            if isinstance(n, ast.Name):
                return (n.id,)
            if isinstance(n, ast.Attribute):
                parts=[]
                cur=n
                while isinstance(cur, ast.Attribute):
                    parts.append(cur.attr)
                    cur=cur.value
                if isinstance(cur, ast.Name):
                    parts.append(cur.id)
                    return tuple(reversed(parts))
            return None

        def resolve_starstar(kw_value: ast.AST) -> Tuple[Dict[str, ast.AST], bool]:
            # If **{ "k": expr } literal, we can resolve keys; otherwise unknown.
            if isinstance(kw_value, ast.Dict):
                out: Dict[str, ast.AST] = {}
                for k, v in zip(kw_value.keys, kw_value.values):
                    if not isinstance(k, ast.Constant) or not isinstance(k.value, str):
                        return {}, True
                    out[k.value] = v
                return out, False
            return {}, True

        class Finder(ast.NodeVisitor):
            def __init__(self): self.parents=[]
            def generic_visit(self, node):
                self.parents.append(node)
                super().generic_visit(node)
                self.parents.pop()
            def visit_Call(self, node: ast.Call):
                parts = call_parts(node.func)
                dotted = ".".join(parts) if parts else None

                ok = False
                if isinstance(at.selector, CallSelector):
                    kw: Dict[str, ast.AST] = {}
                    has_unknown = False
                    for k in node.keywords:
                        if k.arg is None:
                            extra, unk = resolve_starstar(k.value)
                            kw.update(extra)
                            has_unknown = has_unknown or unk
                        else:
                            kw[k.arg] = k.value
                    ok = at.selector.match(parts, node.args, kw, has_unresolved_starstar=has_unknown)
                else:
                    ok = (dotted == str(at.name))

                if ok:
                    parent = self.parents[-1] if self.parents else None
                    matches.append(Match(node=node, parent=parent, field=None, index=None, at=at))
                self.generic_visit(node)

        Finder().visit(fn)
        return matches

    def instrument(self, fn: ast.FunctionDef, matches: List[Match], injectors: List[InjectorSpec], target: str) -> None:
        if not matches:
            return
        at_name = injectors[0].at.name
        method = fn.name
        self_expr = _self_expr(fn)
        match_nodes = {m.node for m in matches}

        class Rewriter(ast.NodeTransformer):
            def visit_Call(self, node: ast.Call):
                node = self.generic_visit(node)
                if node in match_nodes:
                    call_original = ast.Lambda(
                        args=ast.arguments(
                            posonlyargs=[],
                            args=[],
                            vararg=ast.arg(arg="_mixin_args"),
                            kwonlyargs=[],
                            kw_defaults=[],
                            kwarg=ast.arg(arg="_mixin_kwargs"),
                            defaults=[],
                        ),
                        body=ast.Call(
                            func=node.func,
                            args=[
                                ast.Starred(value=ast.Name(id="_mixin_args", ctx=ast.Load()), ctx=ast.Load())
                            ],
                            keywords=[ast.keyword(arg=None, value=ast.Name(id="_mixin_kwargs", ctx=ast.Load()))],
                        ),
                    )

                    args_list = ast.List(elts=list(node.args), ctx=ast.Load())

                    # Build merged kwargs dict to preserve **kwargs keys for runtime dispatch/conditions.
                    explicit = ast.Dict(
                        keys=[ast.Constant(value=k.arg) for k in node.keywords if k.arg is not None],
                        values=[k.value for k in node.keywords if k.arg is not None]
                    )
                    starstars = [k.value for k in node.keywords if k.arg is None]
                    if starstars:
                        kwargs_expr = ast.Call(
                            func=ast.Attribute(value=ast.Name(id="mixpy_runtime", ctx=ast.Load()), attr="merge_kwargs", ctx=ast.Load()),
                            args=[explicit, *starstars],
                            keywords=[]
                        )
                    else:
                        kwargs_expr = explicit

                    return ast.Call(
                        func=ast.Attribute(value=ast.Name(id="mixpy_runtime", ctx=ast.Load()), attr="eval_invoke", ctx=ast.Load()),
                        args=[
                            ast.Name(id="__mixin_injectors__", ctx=ast.Load()),
                            ast.Constant(value=target),
                            ast.Constant(value=method),
                            ast.Constant(value=str(at_name)),
                            self_expr,
                            call_original,
                            args_list,
                            kwargs_expr,
                        ],
                        keywords=[]
                    )
                return node

        fn.body = [Rewriter().visit(s) for s in fn.body]

class AttributeHandler:
    type = TYPE.ATTRIBUTE

    def find(self, fn: ast.FunctionDef, at: At) -> List[Match]:
        matches: List[Match] = []
        target_name = str(at.name)

        def attr_dotted(n: ast.AST) -> Optional[str]:
            parts = _dotted_name_from_attribute(n)
            return ".".join(parts) if parts else None

        class Finder(ast.NodeVisitor):
            def __init__(self): self.parents=[]
            def generic_visit(self, node):
                self.parents.append(node)
                super().generic_visit(node)
                self.parents.pop()
            def visit_Assign(self, node: ast.Assign):
                for idx, t in enumerate(node.targets):
                    if isinstance(t, ast.Attribute) and attr_dotted(t) == target_name:
                        matches.append(Match(node=node, parent=self.parents[-1] if self.parents else None, field="targets", index=idx, at=at))
                self.generic_visit(node)
            def visit_AnnAssign(self, node: ast.AnnAssign):
                t = node.target
                if isinstance(t, ast.Attribute) and attr_dotted(t) == target_name:
                    matches.append(Match(node=node, parent=self.parents[-1] if self.parents else None, field="target", index=None, at=at))
                self.generic_visit(node)
            def visit_AugAssign(self, node: ast.AugAssign):
                t = node.target
                if isinstance(t, ast.Attribute) and attr_dotted(t) == target_name:
                    matches.append(Match(node=node, parent=self.parents[-1] if self.parents else None, field="target", index=None, at=at))
                self.generic_visit(node)

        Finder().visit(fn)
        return matches

    def instrument(self, fn: ast.FunctionDef, matches: List[Match], injectors: List[InjectorSpec], target: str) -> None:
        if not matches:
            return
        at_name = injectors[0].at.name
        method = fn.name
        self_expr = _self_expr(fn)
        match_nodes = {m.node for m in matches}

        class Rewriter(ast.NodeTransformer):
            def visit_Assign(self, node: ast.Assign):
                node = self.generic_visit(node)
                if node in match_nodes:
                    new_value = ast.Call(
                        func=ast.Attribute(value=ast.Name(id="mixpy_runtime", ctx=ast.Load()), attr="eval_attr_write", ctx=ast.Load()),
                        args=[
                            ast.Name(id="__mixin_injectors__", ctx=ast.Load()),
                            ast.Constant(value=target),
                            ast.Constant(value=method),
                            ast.Constant(value=str(at_name)),
                            self_expr,
                            node.value,
                        ],
                        keywords=[]
                    )
                    return ast.Assign(targets=node.targets, value=new_value)
                return node

            def visit_AnnAssign(self, node: ast.AnnAssign):
                node = self.generic_visit(node)
                if node in match_nodes and node.value is not None:
                    new_value = ast.Call(
                        func=ast.Attribute(value=ast.Name(id="mixpy_runtime", ctx=ast.Load()), attr="eval_attr_write", ctx=ast.Load()),
                        args=[
                            ast.Name(id="__mixin_injectors__", ctx=ast.Load()),
                            ast.Constant(value=target),
                            ast.Constant(value=method),
                            ast.Constant(value=str(at_name)),
                            self_expr,
                            node.value,
                        ],
                        keywords=[]
                    )
                    return ast.AnnAssign(target=node.target, annotation=node.annotation, value=new_value, simple=node.simple)
                return node

            def visit_AugAssign(self, node: ast.AugAssign):
                node = self.generic_visit(node)
                if node in match_nodes:
                    binop = ast.BinOp(left=node.target, op=node.op, right=node.value)
                    new_value = ast.Call(
                        func=ast.Attribute(value=ast.Name(id="mixpy_runtime", ctx=ast.Load()), attr="eval_attr_write", ctx=ast.Load()),
                        args=[
                            ast.Name(id="__mixin_injectors__", ctx=ast.Load()),
                            ast.Constant(value=target),
                            ast.Constant(value=method),
                            ast.Constant(value=str(at_name)),
                            self_expr,
                            binop,
                        ],
                        keywords=[]
                    )
                    return ast.Assign(targets=[node.target], value=new_value)
                return node

        fn.body = [Rewriter().visit(s) for s in fn.body]

class ExceptionHandler:
    type = TYPE.EXCEPTION

    def find(self, fn: ast.FunctionDef, at: At) -> List[Match]:
        # One match representing the whole function body.
        return [Match(node=fn, parent=None, field="body", index=0, at=at)]

    def instrument(self, fn: ast.FunctionDef, matches: List[Match], injectors: List[InjectorSpec], target: str) -> None:
        if not matches:
            return
        is_async = isinstance(fn, ast.AsyncFunctionDef)
        method = fn.name
        at_name = "EXCEPTION"
        self_expr = _self_expr(fn)
        inj = _get_injectors_call(target, method, "EXCEPTION", at_name)
        ci_name = "_mixin_ci_exc"

        # Build the except handler:
        #   _mixin_ci_exc = CallbackInfo(...)
        #   _mixin_ci_exc._ctx = {"exception": _mixin_exc, ...}
        #   dispatch_injectors(injectors, _mixin_ci_exc, ctx, self)
        #   if _mixin_ci_exc.is_cancelled: return _mixin_ci_exc.result
        #   raise
        exc_var = "_mixin_exc"
        ci_assign = ast.Assign(
            targets=[ast.Name(id=ci_name, ctx=ast.Store())],
            value=_mk_ci_ctor("EXCEPTION", target, method, at_name),
        )
        ctx = ast.Dict(
            keys=[ast.Constant("self"), ast.Constant("args"), ast.Constant("kwargs"),
                  ast.Constant("locals"), ast.Constant("exception")],
            values=[
                self_expr,
                _build_args_list_expr(fn),
                _build_kwargs_dict_expr(fn),
                ast.Call(func=ast.Name(id="locals", ctx=ast.Load()), args=[], keywords=[]),
                ast.Name(id=exc_var, ctx=ast.Load()),
            ],
        )
        # EXCEPTION callbacks receive only self (like CONST); exception is in ci.get_context()["exception"]
        cb_args = [self_expr]
        dispatch = _mk_dispatch_stmt(inj, ci_name, ctx, cb_args, is_async=is_async)
        guard = _mk_if_cancel_return(ci_name)
        reraise = ast.Raise()  # bare `raise` re-raises current exception

        except_handler = ast.ExceptHandler(
            type=None,  # catches BaseException
            name=exc_var,
            body=[ci_assign, dispatch, guard, reraise],
        )
        try_node = ast.Try(
            body=list(fn.body),
            handlers=[except_handler],
            orelse=[],
            finalbody=[],
        )
        fn.body = [try_node]


class YieldHandler:
    """Intercept ``yield`` expressions in generator functions.

    Callbacks receive the yielded value via ``ci.get_context()['value']`` and
    can mutate it with ``ci.set_value(x)`` or substitute a different value
    with ``ci.cancel(result=x)``.
    """

    type = TYPE.YIELD

    def find(self, fn: ast.FunctionDef, at: At) -> List[Match]:
        matches: List[Match] = []

        class Finder(ast.NodeVisitor):
            def __init__(self):
                self.parents: List[ast.AST] = []

            def generic_visit(self, node: ast.AST) -> None:
                self.parents.append(node)
                super().generic_visit(node)
                self.parents.pop()

            def visit_Yield(self, node: ast.Yield) -> None:  # type: ignore[override]
                parent = self.parents[-1] if self.parents else None
                matches.append(Match(node=node, parent=parent, field=None, index=None, at=at))

        Finder().visit(fn)
        return matches

    def instrument(self, fn: ast.FunctionDef, matches: List[Match], injectors: List[InjectorSpec], target: str) -> None:
        if not matches:
            return
        at_name = "YIELD"
        method = fn.name
        self_expr = _self_expr(fn)
        match_nodes = {m.node for m in matches}

        class Rewriter(ast.NodeTransformer):
            def visit_Yield(self, node: ast.Yield) -> ast.AST:  # type: ignore[override]
                if node not in match_nodes:
                    return node
                yield_value = node.value if node.value is not None else ast.Constant(value=None)
                new_value = ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id="mixpy_runtime", ctx=ast.Load()),
                        attr="eval_yield",
                        ctx=ast.Load(),
                    ),
                    args=[
                        ast.Name(id="__mixin_injectors__", ctx=ast.Load()),
                        ast.Constant(value=target),
                        ast.Constant(value=method),
                        ast.Constant(value=at_name),
                        self_expr,
                        yield_value,
                    ],
                    keywords=[],
                )
                return ast.Yield(value=new_value)

        fn.body = [Rewriter().visit(s) for s in fn.body]


def install_builtin_handlers():
    register_handler(HeadHandler())
    register_handler(ParameterHandler())
    register_handler(TailHandler())
    register_handler(ConstHandler())
    register_handler(InvokeHandler())
    register_handler(AttributeHandler())
    register_handler(ExceptionHandler())
    register_handler(YieldHandler())
