from __future__ import annotations


class LobsterRouterError(RuntimeError):
    pass


class LobsterRouterConfigError(LobsterRouterError):
    pass


class LobsterRouterRequestError(LobsterRouterError):
    pass


class LobsterRouterHTTPError(LobsterRouterError):
    pass


class LobsterRouterParseError(LobsterRouterError):
    pass
