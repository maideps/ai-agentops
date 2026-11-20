"""Phase 1 demo identity (spec section 9): one configured bearer token stands for one configured
demo user. No token configured means every mutation is refused."""

import secrets

from agentops_api.problems import ProblemError
from agentops_api.settings import Settings


def demo_principal(settings: Settings, authorization: str | None) -> tuple[str, str]:
    """The (tenant_id, user_id) of the demo user, or a 401/503 problem."""
    expected = settings.demo_api_token.get_secret_value() if settings.demo_api_token else ""
    if not expected or not settings.demo_tenant_id or not settings.demo_user_id:
        raise ProblemError(503, "AUTH_NOT_CONFIGURED", "mutations are disabled: no demo identity")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme != "Bearer" or not secrets.compare_digest(token.encode(), expected.encode()):
        raise ProblemError(401, "UNAUTHENTICATED", "a valid bearer token is required")
    return settings.demo_tenant_id, settings.demo_user_id
