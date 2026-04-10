import asyncio
import ssl as _ssl
import time
import warnings
from collections import Counter

from .errors import (
    ProxyConnError,
    ProxyEmptyRecvError,
    ProxyRecvError,
    ProxySendError,
    ProxyTimeoutError,
    ResolveError,
)

from .negotiators import NGTRS
from .resolver import Resolver
from .utils import log, parse_headers


_HTTP_PROTOS = {'HTTP', 'CONNECT:80', 'SOCKS4', 'SOCKS5'}
_HTTPS_PROTOS = {'HTTPS', 'SOCKS4', 'SOCKS5'}


class Proxy:
    """Proxy handler for testing and using proxy connections."""

    # -------------------------
    # CREATE PROXY (async)
    # -------------------------
    @classmethod
    async def create(cls, host, *args, **kwargs):
        loop = kwargs.pop('loop', None)
        resolver = kwargs.pop('resolver', Resolver(loop=loop))

        try:
            _host = await resolver.resolve(host)
            self = cls(_host, *args, **kwargs)
        except (ResolveError, ValueError) as e:
            log.error(f"{host}:{args[0]}: Error at creating: {e}")
            raise

        return self

    # -------------------------
    # INIT
    # -------------------------
    def __init__(self, host=None, port=None, types=(), timeout=8, verify_ssl=False):
        self.host = host

        if not Resolver.host_is_ip(self.host):
            raise ValueError("Host must be an IP address (use Proxy.create for domains)")

        self.port = int(port)

        if self.port > 65535:
            raise ValueError("Port cannot be greater than 65535")

        self.expected_types = set(types) & {
            'HTTP', 'HTTPS', 'CONNECT:80', 'CONNECT:25', 'SOCKS4', 'SOCKS5'
        }

        self._timeout = timeout
        self._ssl_context = True if verify_ssl else _ssl._create_unverified_context()

        self._types = {}
        self._is_working = False

        self.stat = {'requests': 0, 'errors': Counter()}

        self._ngtr = None
        self._geo = Resolver.get_ip_info(self.host)

        self._log = []
        self._runtimes = []

        self._schemes = ()
        self._closed = True

        self._reader = {'conn': None, 'ssl': None}
        self._writer = {'conn': None, 'ssl': None}
