"""OctoPrint-specific ASGI reverse proxy.

Extends bitbang's ReverseProxyASGI with OctoPrint cookie name rewriting.
OctoPrint appends the port to cookie names (e.g. csrf_token_P5000).
When accessed via BitBang (port 443), the JS looks for _P443. We rewrite
cookie names in both directions to bridge the mismatch.
"""

from bitbang.proxy import ReverseProxyASGI


class OctoPrintProxy(ReverseProxyASGI):
    """ASGI reverse proxy with OctoPrint cookie rewriting."""

    def __init__(self, target="localhost:5000"):
        super().__init__(target)

        from urllib.parse import urlparse
        parsed = urlparse(self.target)
        target_port = str(parsed.port or 80)
        self._suffix_target = f"_P{target_port}"
        self._suffix_remote = "_P443"

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return

        # Rewrite cookie names in request headers: _P443 -> _P5000
        rewritten_headers = []
        for k, v in scope.get("headers", []):
            name = k.decode()
            value = v.decode()
            if name.lower() == "cookie":
                value = value.replace(self._suffix_remote, self._suffix_target)
            rewritten_headers.append((k, value.encode()))
        scope = dict(scope, headers=rewritten_headers)

        # Wrap send to rewrite Set-Cookie in responses: _P5000 -> _P443
        original_send = send
        async def rewriting_send(message):
            if message["type"] == "http.response.start":
                headers = []
                for k, v in message.get("headers", []):
                    name = k.decode()
                    value = v.decode()
                    if name.lower() == "set-cookie":
                        value = value.replace(self._suffix_target, self._suffix_remote)
                    headers.append((k, value.encode()))
                message = dict(message, headers=headers)
            await original_send(message)

        await super().__call__(scope, receive, rewriting_send)
