"""Zoho Catalyst QuickML client (GLM 4.7 text).

All model calls in DRISHTI go through this package — feature code never
touches HTTP or tokens directly. Auto-refreshes the OAuth access token on
expiry using the refresh token (see zoho.py).
"""

from .zoho import ZohoLLM, chat_text  # noqa: F401
