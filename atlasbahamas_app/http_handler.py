"""Composed HTTP handler built from modular mixins."""
from http.server import BaseHTTPRequestHandler

from .handlers import (
    BaseHandlerMixin,
    AuthHandlerMixin,
    PublicHandlerMixin,
    MessagesHandlerMixin,
    NotificationsHandlerMixin,
    TenantHandlerMixin,
    LandlordHandlerMixin,
    ManagerHandlerMixin,
    AdminHandlerMixin,
    PropertyManagerHandlerMixin,
)


class H(
    BaseHandlerMixin,
    AuthHandlerMixin,
    PublicHandlerMixin,
    MessagesHandlerMixin,
    NotificationsHandlerMixin,
    TenantHandlerMixin,
    LandlordHandlerMixin,
    ManagerHandlerMixin,
    AdminHandlerMixin,
    PropertyManagerHandlerMixin,
    BaseHTTPRequestHandler,
):
    """Main request handler assembled from modular mixins."""
    server_version = "AtlasBahamas/1.0"


