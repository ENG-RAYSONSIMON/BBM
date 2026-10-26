"""Request-scoped actor: who is acting and from which IP, for the audit log
(FR-20).

Set only by TenantJWTAuthentication, next to the active business, and
cleared per request by TenantContextMiddleware. Services read it instead of
having the request passed down to them.
"""

import ipaddress
from contextvars import ContextVar
from dataclasses import dataclass

from rest_framework.throttling import BaseThrottle


@dataclass(frozen=True)
class Actor:
    user: object
    ip: str | None


_current_actor: ContextVar[Actor | None] = ContextVar("current_actor", default=None)


def client_ip(request):
    """The client IP as the throttles see it (NUM_PROXIES aware), or None if
    it isn't a single valid address."""
    ident = BaseThrottle().get_ident(request)
    try:
        return str(ipaddress.ip_address(ident))
    except ValueError:
        return None


def get_current_actor():
    return _current_actor.get()


def set_current_actor(actor):
    return _current_actor.set(actor)


def reset_current_actor(token):
    _current_actor.reset(token)
