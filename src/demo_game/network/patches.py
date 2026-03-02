"""MixPy networking demo patches.

Demonstrates using INVOKE, HEAD, EXCEPTION, and ATTRIBUTE injectors
on simulated HTTP and socket clients.
"""
import mixpy
from mixpy import (
    mixin, inject, At, TYPE, OP, Loc, When,
    CallSelector, QualifiedSelector, ArgAny, ArgConst, ArgName,
    at_head, at_exception, at_invoke,
)

# ---------------------------------------------------------------------------
# HTTP Client patches
# ---------------------------------------------------------------------------

@mixin(target="demo_game.network.client.HTTPClient")
class HTTPClientPatch:

    @inject(
        method="get",
        at=At(type=TYPE.HEAD, name=None, location=Loc(condition=When("args[0]", OP.EQ, "/blocked"))),
    )
    def block_path(self, ci, path, *args, **kw):
        from demo_game.network.client import Response
        ci.cancel(result=Response(status=403, body="Forbidden"))

    @inject(
        method="post",
        at=At(type=TYPE.PARAMETER, name="body", location=Loc(condition=When("value", OP.EQ, ""))),
    )
    def default_empty_body(self, ci, *args, **kw):
        ci.set_value("{}")

    @inject(
        method="fetch",
        at=at_exception(),
    )
    def retry_on_error(self, ci):
        exc = ci.get_context().get("exception")
        if isinstance(exc, (ConnectionError, OSError)):
            from demo_game.network.client import Response
            ci.cancel(result=Response(status=503, body="Service Unavailable (injected fallback)"))

    @inject(
        method="get",
        at=At(type=TYPE.INVOKE, name="self.request_log.append",
              selector=CallSelector(func=QualifiedSelector.of("self", "request_log", "append"), args=(ArgAny(),))),
    )
    def enrich_request_log(self, ci, entry):
        enriched = dict(entry)
        enriched["_mixpy"] = True
        ci.cancel(result=self.request_log.append(enriched))


# ---------------------------------------------------------------------------
# Socket Client patches
# ---------------------------------------------------------------------------

@mixin(target="demo_game.network.client.SocketClient")
class SocketClientPatch:

    @inject(
        method="send",
        at=At(type=TYPE.HEAD, name=None),
    )
    def log_send(self, ci, data, *args, **kw):
        # Non-cancelling: just observe
        pass

    @inject(
        method="send",
        at=At(type=TYPE.PARAMETER, name="data",
              location=Loc(condition=When("value", OP.EQ, b""))),
    )
    def reject_empty_send(self, ci, *args, **kw):
        raise ValueError("Cannot send empty bytes over socket")

    @inject(
        method="send",
        at=at_exception(),
    )
    def handle_send_error(self, ci):
        exc = ci.get_context().get("exception")
        if isinstance(exc, ConnectionError):
            ci.cancel(result=-1)
