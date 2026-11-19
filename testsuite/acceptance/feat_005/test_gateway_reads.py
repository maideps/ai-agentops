"""feat-005 (FR-005, NFR-001): read tools through the gateway: allowlist, role permissions,
strict arguments and the caller's tenant only."""

import pytest

from agentops_tools.gateway import GatewayDenied
from testsuite.acceptance.feat_005.helpers import context, events_for_run, gateway

pytestmark = pytest.mark.integration


def test_analyst_reads_sales_declines(seeded_db: str, app_dsn: str) -> None:
    result = gateway(app_dsn).invoke(
        context(), "get_sales_summary", {"from_quarter": "2026-Q2", "to_quarter": "2026-Q3"}
    )

    declines = result["analytics"]["declines"]
    assert [(row["product_id"], row["region"]) for row in declines] == [
        (101, "EMEA"),
        (102, "NA"),
        (103, "NA"),
    ]


def test_issue_details_are_tenant_scoped(seeded_db: str, app_dsn: str) -> None:
    gw = gateway(app_dsn)

    own = gw.invoke(context(), "get_issue_details", {"issue_id": "ISSUE-A-102"})
    with pytest.raises(GatewayDenied) as raised:
        gw.invoke(context(), "get_issue_details", {"issue_id": "ISSUE-B-201"})

    assert own["issue"]["title"] == "NA rain jacket price exception"
    assert raised.value.reason_code == "NOT_FOUND"


@pytest.mark.parametrize(
    ("ctx_kwargs", "tool", "arguments", "reason"),
    [
        (
            {"user_id": "user-a-viewer"},
            "get_sales_summary",
            {"from_quarter": "2026-Q2", "to_quarter": "2026-Q3"},
            "PERMISSION_DENIED",
        ),
        ({}, "run_sql", {"sql": "SELECT 1"}, "TOOL_NOT_ALLOWED"),
        (
            {},
            "get_sales_summary",
            {"from_quarter": "2026-Q2", "to_quarter": "2026-Q3", "tenant_id": "demo-b"},
            "INVALID_ARGUMENTS",
        ),
        (
            {},
            "get_sales_summary",
            {"from_quarter": "Q3; DROP TABLE x", "to_quarter": "2026-Q3"},
            "INVALID_ARGUMENTS",
        ),
        (
            {"user_id": "user-b-analyst"},
            "get_sales_summary",
            {"from_quarter": "2026-Q2", "to_quarter": "2026-Q3"},
            "UNKNOWN_PRINCIPAL",
        ),
    ],
)
def test_reads_fail_closed_and_are_logged(
    seeded_db: str,
    app_dsn: str,
    admin_dsn: str,
    ctx_kwargs: dict[str, str],
    tool: str,
    arguments: dict[str, object],
    reason: str,
) -> None:
    ctx = context(**ctx_kwargs)

    with pytest.raises(GatewayDenied) as raised:
        gateway(app_dsn).invoke(ctx, tool, arguments)

    assert raised.value.reason_code == reason
    assert events_for_run(admin_dsn, ctx.run_id) == [("tool_call", tool, "deny", reason)]
