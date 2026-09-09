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


class ManualVerificationRequired(XueqiuCollectorError):
    """Raised when a human must complete a visible verification challenge."""


class CdpNotAvailable(XueqiuCollectorError):
    """Raised when the requested existing Edge CDP endpoint cannot be attached."""


class NetworkUnavailable(XueqiuCollectorError):
    """Raised when no usable target page or network response is available."""


class NoContent(XueqiuCollectorError):
    pass


class BrowserDependencyMissing(XueqiuCollectorError):
    pass
