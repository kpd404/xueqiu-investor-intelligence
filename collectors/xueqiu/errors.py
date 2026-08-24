class XueqiuCollectorError(RuntimeError):
    """Base class for expected Xueqiu collection failures."""


class AuthenticationRequired(XueqiuCollectorError):
    pass


class NavigationFailed(XueqiuCollectorError):
    pass


class ParseFailed(XueqiuCollectorError):
    pass


class RateLimitedOrBlocked(XueqiuCollectorError):
    pass


class NoContent(XueqiuCollectorError):
    pass


class BrowserDependencyMissing(XueqiuCollectorError):
    pass
