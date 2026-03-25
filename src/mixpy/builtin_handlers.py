from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from .model import TYPE, At
from .handlers import Match, register_handler
from .registry import InjectorSpec
from .location_utils import _dotted_name_from_attribute
from .selector import CallSelector

if TYPE_CHECKING:
    from .ast_index import ASTIndex

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

    def find(self, fn: ast.FunctionDef, at: At, index: Optional[ASTIndex] = None) -> List[Match]:
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

    def find(self, fn: ast.FunctionDef, at: At, index: Optional[ASTIndex] = None) -> List[Match]:
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

    def find(self, fn: ast.FunctionDef, at: At, index: Optional[ASTIndex] = None) -> List[Match]:
        if index is not None:
            return [
                Match(node=node, parent=index.get_parent(node), field=None, index=None, at=at)
                for node in index.all_returns
            ]
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

    def find(self, fn: ast.FunctionDef, at: At, index: Optional[ASTIndex] = None) -> List[Match]:
        if index is not None:
            return [
                Match(node=node, parent=index.get_parent(node), field=None, index=None, at=at)
                for node in index.all_constants
                if node.value == at.name
            ]
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

    @staticmethod
    def _call_parts(n: ast.AST) -> Optional[Tuple[str, ...]]:
        if isinstance(n, ast.Name):
            return (n.id,)
        if isinstance(n, ast.Attribute):
            parts: List[str] = []
            cur = n
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                parts.append(cur.id)
                return tuple(reversed(parts))
        return None

    @staticmethod
    def _resolve_starstar(kw_value: ast.AST) -> Tuple[Dict[str, ast.AST], bool]:
        if isinstance(kw_value, ast.Dict):
            out: Dict[str, ast.AST] = {}
            for k, v in zip(kw_value.keys, kw_value.values):
                if not isinstance(k, ast.Constant) or not isinstance(k.value, str):
                    return {}, True
                out[k.value] = v
            return out, False
        return {}, True

    def _match_call(self, node: ast.Call, at: At) -> bool:
        parts = self._call_parts(node.func)
        dotted = ".".join(parts) if parts else None
        if isinstance(at.selector, CallSelector):
            kw: Dict[str, ast.AST] = {}
            has_unknown = False
            for k in node.keywords:
                if k.arg is None:
                    extra, unk = self._resolve_starstar(k.value)
                    kw.update(extra)
                    has_unknown = has_unknown or unk
                else:
                    kw[k.arg] = k.value
            return at.selector.match(parts, node.args, kw, has_unresolved_starstar=has_unknown)
        return dotted == str(at.name)

    def find(self, fn: ast.FunctionDef, at: At, index: Optional[ASTIndex] = None) -> List[Match]:
        if index is not None:
            matches: List[Match] = []
            for node in index.all_calls:
                if self._match_call(node, at):
                    matches.append(Match(node=node, parent=index.get_parent(node), field=None, index=None, at=at))
            return matches

        matches = []

        class Finder(ast.NodeVisitor):
            def __init__(self_f): self_f.parents=[]
            def generic_visit(self_f, node):
                self_f.parents.append(node)
                super().generic_visit(node)
                self_f.parents.pop()
            def visit_Call(self_f, node: ast.Call):
                if self._match_call(node, at):
                    parent = self_f.parents[-1] if self_f.parents else None
                    matches.append(Match(node=node, parent=parent, field=None, index=None, at=at))
                self_f.generic_visit(node)

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

    @staticmethod
    def _attr_dotted(n: ast.AST) -> Optional[str]:
        parts = _dotted_name_from_attribute(n)
        return ".".join(parts) if parts else None

    def find(self, fn: ast.FunctionDef, at: At, index: Optional[ASTIndex] = None) -> List[Match]:
        matches: List[Match] = []
        target_name = str(at.name)

        if index is not None:
            for node in index.get_nodes(ast.Assign):
                for idx, t in enumerate(node.targets):
                    if isinstance(t, ast.Attribute) and self._attr_dotted(t) == target_name:
                        matches.append(Match(node=node, parent=index.get_parent(node), field="targets", index=idx, at=at))
            for node in index.get_nodes(ast.AnnAssign):
                t = node.target
                if isinstance(t, ast.Attribute) and self._attr_dotted(t) == target_name:
                    matches.append(Match(node=node, parent=index.get_parent(node), field="target", index=None, at=at))
            for node in index.get_nodes(ast.AugAssign):
                t = node.target
                if isinstance(t, ast.Attribute) and self._attr_dotted(t) == target_name:
                    matches.append(Match(node=node, parent=index.get_parent(node), field="target", index=None, at=at))
            return matches

        class Finder(ast.NodeVisitor):
            def __init__(self): self.parents=[]
            def generic_visit(self, node):
                self.parents.append(node)
                super().generic_visit(node)
                self.parents.pop()
            def visit_Assign(self, node: ast.Assign):
                for idx, t in enumerate(node.targets):
                    if isinstance(t, ast.Attribute) and AttributeHandler._attr_dotted(t) == target_name:
                        matches.append(Match(node=node, parent=self.parents[-1] if self.parents else None, field="targets", index=idx, at=at))
                self.generic_visit(node)
            def visit_AnnAssign(self, node: ast.AnnAssign):
                t = node.target
                if isinstance(t, ast.Attribute) and AttributeHandler._attr_dotted(t) == target_name:
                    matches.append(Match(node=node, parent=self.parents[-1] if self.parents else None, field="target", index=None, at=at))
                self.generic_visit(node)
            def visit_AugAssign(self, node: ast.AugAssign):
                t = node.target
                if isinstance(t, ast.Attribute) and AttributeHandler._attr_dotted(t) == target_name:
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

    def find(self, fn: ast.FunctionDef, at: At, index: Optional[ASTIndex] = None) -> List[Match]:
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

    def find(self, fn: ast.FunctionDef, at: At, index: Optional[ASTIndex] = None) -> List[Match]:
        if index is not None:
            return [
                Match(node=node, parent=index.get_parent(node), field=None, index=None, at=at)
                for node in index.all_yields
            ]
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


class AwaitHandler:
    """Intercept ``await`` expressions in async functions.

    Callbacks receive the awaitable via ``ci.get_context()['awaitable']`` and
    can mutate the result with ``ci.set_value(x)`` or cancel with
    ``ci.cancel(result=x)`` to skip the await entirely.
    """

    type = TYPE.AWAIT

    def find(self, fn: ast.FunctionDef, at: At, index: Optional[ASTIndex] = None) -> List[Match]:
        target_name = str(at.name) if at.name else None
        if index is not None:
            nodes = index.all_awaits
        else:
            nodes = [n for n in ast.walk(fn) if isinstance(n, ast.Await)]

        matches: List[Match] = []
        for node in nodes:
            name = self._await_name(node)
            if target_name and name != target_name:
                continue
            parent = index.get_parent(node) if index else None
            matches.append(Match(node=node, parent=parent, field=None, index=None, at=at))
        return matches

    def _await_name(self, node: ast.Await) -> Optional[str]:
        """Extract name of the awaited expression."""
        expr = node.value
        if isinstance(expr, ast.Call):
            return self._call_name(expr.func)
        if isinstance(expr, ast.Name):
            return expr.id
        if isinstance(expr, ast.Attribute):
            parts = _dotted_name_from_attribute(expr)
            return ".".join(parts) if parts else None
        return None

    def _call_name(self, func_node: ast.expr) -> Optional[str]:
        if isinstance(func_node, ast.Name):
            return func_node.id
        if isinstance(func_node, ast.Attribute):
            parts = _dotted_name_from_attribute(func_node)
            return ".".join(parts) if parts else None
        return None

    def instrument(self, fn: ast.FunctionDef, matches: List[Match], injectors: List[InjectorSpec], target: str) -> None:
        if not matches:
            return
        method = fn.name
        self_expr = _self_expr(fn)
        match_nodes: Dict[int, Match] = {id(m.node): m for m in matches}

        class Rewriter(ast.NodeTransformer):
            def visit_Await(self, node: ast.Await) -> ast.AST:  # type: ignore[override]
                if id(node) not in match_nodes:
                    return node
                m = match_nodes[id(node)]
                at_name = str(m.at.name) if m.at.name else "AWAIT"
                # Replace:  await <expr>
                # With:     await mixpy_runtime.eval_await(..., <expr>)
                new_value = ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id="mixpy_runtime", ctx=ast.Load()),
                        attr="eval_await",
                        ctx=ast.Load(),
                    ),
                    args=[
                        ast.Name(id="__mixin_injectors__", ctx=ast.Load()),
                        ast.Constant(value=target),
                        ast.Constant(value=method),
                        ast.Constant(value=at_name),
                        self_expr,
                        node.value,  # the original awaitable (not yet awaited)
                    ],
                    keywords=[],
                )
                return ast.Await(value=new_value)

        fn.body = [Rewriter().visit(s) for s in fn.body]


class AttrReadHandler:
    """Intercept attribute reads (Load context), e.g. ``x = self.hp``."""

    type = TYPE.ATTR_READ

    @staticmethod
    def _dotted_name(node: ast.AST) -> Optional[str]:
        parts = _dotted_name_from_attribute(node)
        return ".".join(parts) if parts else None

    def find(self, fn: ast.FunctionDef, at: At, index: Optional[ASTIndex] = None) -> List[Match]:
        matches: List[Match] = []
        target_name = str(at.name) if at.name else None

        nodes = index.all_attr_reads if index else [
            n for n in ast.walk(fn)
            if isinstance(n, ast.Attribute) and isinstance(getattr(n, 'ctx', None), ast.Load)
        ]

        for node in nodes:
            dotted = self._dotted_name(node)
            if dotted is None:
                continue
            if target_name and dotted != target_name:
                continue
            parent = index.get_parent(node) if index else None
            matches.append(Match(node=node, parent=parent, field=None, index=None, at=at))

        return matches

    def instrument(self, fn: ast.FunctionDef, matches: List[Match], injectors: List[InjectorSpec], target: str) -> None:
        if not matches:
            return
        at_name = injectors[0].at.name
        method = fn.name
        self_expr = _self_expr(fn)
        match_ids = {id(m.node) for m in matches}

        class Rewriter(ast.NodeTransformer):
            def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
                node = self.generic_visit(node)
                if id(node) not in match_ids:
                    return node
                # Replace self.hp with eval_attr_read(..., self.hp)
                original_read = ast.Attribute(
                    value=node.value, attr=node.attr, ctx=ast.Load()
                )
                return ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id="mixpy_runtime", ctx=ast.Load()),
                        attr="eval_attr_read",
                        ctx=ast.Load(),
                    ),
                    args=[
                        ast.Name(id="__mixin_injectors__", ctx=ast.Load()),
                        ast.Constant(value=target),
                        ast.Constant(value=method),
                        ast.Constant(value=str(at_name)),
                        self_expr,
                        original_read,
                    ],
                    keywords=[],
                )

        fn.body = [Rewriter().visit(s) for s in fn.body]


class WithHandler:
    """Intercept ``with`` and ``async with`` context manager statements.

    Callbacks receive ``ci.get_context()['event']`` (``"enter"`` or ``"exit"``)
    and ``ci.get_context()['context_name']``.  Cancelling on ``"enter"`` skips
    the entire ``with`` block.
    """

    type = TYPE.WITH

    # -- find ------------------------------------------------------------------

    def find(self, fn: ast.FunctionDef, at: At, index: Optional['ASTIndex'] = None) -> List[Match]:
        target_name = str(at.name) if at.name else None
        if index is not None:
            nodes = index.all_withs
        else:
            nodes = [n for n in ast.walk(fn) if isinstance(n, (ast.With, ast.AsyncWith))]

        matches: List[Match] = []
        for node in nodes:
            for item in node.items:
                name = self._with_name(item)
                if target_name and name != target_name:
                    continue
                matches.append(Match(node=node, parent=None, field=None, index=None, at=at))
                break  # one match per With statement
        return matches

    @staticmethod
    def _with_name(item: ast.withitem) -> Optional[str]:
        """Extract the context-expression name from a ``withitem``."""
        expr = item.context_expr
        if isinstance(expr, ast.Call):
            if isinstance(expr.func, ast.Name):
                return expr.func.id
            if isinstance(expr.func, ast.Attribute):
                parts: List[str] = []
                cur: ast.expr = expr.func
                while isinstance(cur, ast.Attribute):
                    parts.append(cur.attr)
                    cur = cur.value
                if isinstance(cur, ast.Name):
                    parts.append(cur.id)
                    return ".".join(reversed(parts))
        if isinstance(expr, ast.Name):
            return expr.id
        if item.optional_vars and isinstance(item.optional_vars, ast.Name):
            return item.optional_vars.id
        return None

    # -- instrument ------------------------------------------------------------

    def instrument(self, fn: ast.FunctionDef, matches: List[Match],
                   injectors: List[InjectorSpec], target: str) -> None:
        if not matches:
            return

        at_name = injectors[0].at.name
        method = fn.name
        self_expr = _self_expr(fn)
        is_async = isinstance(fn, ast.AsyncFunctionDef)
        match_nodes = {id(m.node) for m in matches}

        # Counter for unique variable names across all with-sites
        counter = [0]

        def _context_name_for(node: ast.With | ast.AsyncWith) -> str:
            for item in node.items:
                n = WithHandler._with_name(item)
                if n:
                    return n
            return "unknown"

        def _make_replacement(node: ast.With | ast.AsyncWith, idx: int) -> List[ast.stmt]:
            """Build the replacement statement list for one with-node."""
            ctx_name = _context_name_for(node)
            inj_var = f"_mixin_inj_with_{idx}"
            ci_enter = f"_mixin_ci_with_enter_{idx}"
            ci_exit = f"_mixin_ci_with_exit_{idx}"

            # _mixin_inj_with_N = __mixin_injectors__.get(key, [])
            inj_assign = ast.Assign(
                targets=[ast.Name(id=inj_var, ctx=ast.Store())],
                value=_get_injectors_call(target, method, "WITH", str(at_name)),
            )

            def _mk_with_ci(ci_name: str, event: str) -> List[ast.stmt]:
                """Create CI + set ctx + dispatch for an enter/exit event."""
                ci_assign = ast.Assign(
                    targets=[ast.Name(id=ci_name, ctx=ast.Store())],
                    value=_mk_ci_ctor("WITH", target, method, str(at_name)),
                )
                ctx_dict = ast.Dict(
                    keys=[
                        ast.Constant("self"), ast.Constant("args"),
                        ast.Constant("kwargs"), ast.Constant("locals"),
                        ast.Constant("event"), ast.Constant("context_name"),
                    ],
                    values=[
                        self_expr,
                        _build_args_list_expr(fn),
                        _build_kwargs_dict_expr(fn),
                        ast.Call(func=ast.Name(id="locals", ctx=ast.Load()), args=[], keywords=[]),
                        ast.Constant(value=event),
                        ast.Constant(value=ctx_name),
                    ],
                )
                dispatch = _mk_dispatch_stmt(
                    ast.Name(id=inj_var, ctx=ast.Load()),
                    ci_name, ctx_dict, [self_expr], is_async=is_async,
                )
                return [ci_assign, dispatch]

            # Enter callback (inside if _mixin_inj_with_N:)
            enter_stmts = _mk_with_ci(ci_enter, "enter")
            enter_if = ast.If(
                test=ast.Name(id=inj_var, ctx=ast.Load()),
                body=enter_stmts,
                orelse=[],
            )

            # Exit callback (inside if _mixin_inj_with_N:)
            exit_stmts = _mk_with_ci(ci_exit, "exit")
            exit_if = ast.If(
                test=ast.Name(id=inj_var, ctx=ast.Load()),
                body=exit_stmts,
                orelse=[],
            )

            # Guard: if not (inj_var and ci_enter.is_cancelled):
            #     <original with> ... <exit callback>
            guard_test = ast.BoolOp(
                op=ast.And(),
                values=[
                    ast.Name(id=inj_var, ctx=ast.Load()),
                    ast.Attribute(
                        value=ast.Name(id=ci_enter, ctx=ast.Load()),
                        attr="is_cancelled", ctx=ast.Load(),
                    ),
                ],
            )
            guarded_body: List[ast.stmt] = [node, exit_if]
            guard_if = ast.If(
                test=ast.UnaryOp(op=ast.Not(), operand=guard_test),
                body=guarded_body,
                orelse=[],
            )

            result: List[ast.stmt] = [inj_assign, enter_if, guard_if]
            for s in result:
                ast.copy_location(s, node)
                ast.fix_missing_locations(s)
            return result

        def _rewrite_body(body: List[ast.stmt]) -> List[ast.stmt]:
            """Recursively replace matched with-nodes in a statement list."""
            new_body: List[ast.stmt] = []
            for stmt in body:
                # Recurse into sub-blocks first
                for attr in ("body", "orelse", "finalbody", "handlers"):
                    sub = getattr(stmt, attr, None)
                    if isinstance(sub, list):
                        setattr(stmt, attr, _rewrite_body(sub))
                # For ExceptHandler, also recurse into its body
                if isinstance(stmt, ast.ExceptHandler) and hasattr(stmt, "body"):
                    stmt.body = _rewrite_body(stmt.body)

                if isinstance(stmt, (ast.With, ast.AsyncWith)) and id(stmt) in match_nodes:
                    idx = counter[0]
                    counter[0] += 1
                    new_body.extend(_make_replacement(stmt, idx))
                else:
                    new_body.append(stmt)
            return new_body

        fn.body = _rewrite_body(fn.body)


class SubscriptHandler:
    """Intercept subscript operations (``obj[key]``), both reads and writes."""

    type = TYPE.SUBSCRIPT

    def find(self, fn: ast.FunctionDef, at: At, index: Optional[ASTIndex] = None) -> List[Match]:
        target_name = str(at.name) if at.name else None
        nodes = index.all_subscripts if index else [
            n for n in ast.walk(fn) if isinstance(n, ast.Subscript)
        ]
        matches: List[Match] = []
        for node in nodes:
            name = self._subscript_name(node)
            if target_name and name != target_name:
                continue
            parent = index.get_parent(node) if index else None
            matches.append(Match(node=node, parent=parent, field=None, index=None, at=at))
        return matches

    @staticmethod
    def _subscript_name(node: ast.Subscript) -> Optional[str]:
        """Extract name of the object being subscripted."""
        value = node.value
        if isinstance(value, ast.Name):
            return value.id
        if isinstance(value, ast.Attribute):
            parts: List[str] = []
            cur: ast.expr = value
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                parts.append(cur.id)
                return ".".join(reversed(parts))
        return None

    def instrument(self, fn: ast.FunctionDef, matches: List[Match], injectors: List[InjectorSpec], target: str) -> None:
        if not matches:
            return
        at_name = injectors[0].at.name
        method = fn.name
        self_expr = _self_expr(fn)
        match_ids = {id(m.node) for m in matches}

        class Rewriter(ast.NodeTransformer):
            def visit_Assign(self_, node: ast.Assign) -> ast.AST:
                # Handle write case: target[key] = value
                node = self_.generic_visit(node)
                new_targets = []
                write_sub = None
                for t in node.targets:
                    if isinstance(t, ast.Subscript) and id(t) in match_ids:
                        write_sub = t
                        match_ids.discard(id(t))
                    new_targets.append(t)
                if write_sub is not None:
                    new_value = ast.Call(
                        func=ast.Attribute(
                            value=ast.Name(id="mixpy_runtime", ctx=ast.Load()),
                            attr="eval_subscript_write",
                            ctx=ast.Load(),
                        ),
                        args=[
                            ast.Name(id="__mixin_injectors__", ctx=ast.Load()),
                            ast.Constant(value=target),
                            ast.Constant(value=method),
                            ast.Constant(value=str(at_name)),
                            self_expr,
                            write_sub.value,
                            write_sub.slice,
                            node.value,
                        ],
                        keywords=[],
                    )
                    return ast.Assign(targets=new_targets, value=new_value)
                return node

            def visit_Subscript(self_, node: ast.Subscript) -> ast.AST:
                node = self_.generic_visit(node)
                if id(node) not in match_ids:
                    return node
                if not isinstance(getattr(node, 'ctx', None), ast.Load):
                    return node
                # Read case: replace obj[key] with eval_subscript_read(...)
                return ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id="mixpy_runtime", ctx=ast.Load()),
                        attr="eval_subscript_read",
                        ctx=ast.Load(),
                    ),
                    args=[
                        ast.Name(id="__mixin_injectors__", ctx=ast.Load()),
                        ast.Constant(value=target),
                        ast.Constant(value=method),
                        ast.Constant(value=str(at_name)),
                        self_expr,
                        node.value,
                        node.slice,
                    ],
                    keywords=[],
                )

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
    register_handler(WithHandler())
    register_handler(AwaitHandler())
    register_handler(AttrReadHandler())
    register_handler(SubscriptHandler())
