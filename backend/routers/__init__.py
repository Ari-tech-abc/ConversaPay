"""
Backend routers package.
Exports all router modules for easy importing.
"""

from . import auth
from . import businesses
from . import products
from . import chat
from . import orders
from . import payments
from . import logs
from . import webhooks
from . import analytics
from . import widget
from . import dashboard
from . import admin
from . import installations
from . import team

__all__ = [
    'auth',
    'businesses',
    'products',
    'chat',
    'orders',
    'payments',
    'logs',
    'webhooks',
    'analytics',
    'widget',
    'dashboard',
    'admin',
    'installations',
    'team'
]
