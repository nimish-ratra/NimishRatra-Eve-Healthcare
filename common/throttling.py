"""
Rate limiting policies for authentication, public catalog reads, and webhook callbacks.
"""

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class AuthRateThrottle(AnonRateThrottle):
    """Protects signup and login against brute-force credential stuffing."""

    scope = "auth"


class WebhookRateThrottle(AnonRateThrottle):
    """Rate limit for incoming webhook endpoints to absorb abnormal bursts without dropping legitimate retries."""

    scope = "webhook"


class BurstUserRateThrottle(UserRateThrottle):
    """Limits burst write operations from authenticated clients."""

    scope = "user_burst"
