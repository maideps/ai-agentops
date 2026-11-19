"""feat-005 (FR-005, NFR-001): the first-party MCP server is a thin, principal-bound adapter over
the gateway, and obeying a prompt-injected document achieves nothing."""

import asyncio
from typing import Any

import pytest
from mcp import Client

from agentops_tools.gateway import GatewayDenied
from agentops_tools.mcp_server import build_server
from agentops_tools.read_tools import TOOL_ARGUMENT_MODELS
from testsuite.acceptance.feat_005.helpers import (
    TICKET,
    context,
    gateway,
    tickets_for_run,
)

pytestmark = pytest.mark.integration


def test_injected_document_is_returned_as_data_and_obeying_it_fails(
    seeded_db: str, app_dsn: str, admin_dsn: str
) -> None:
    gw, ctx = gateway(app_dsn), context(user_id="user-b-analyst", tenant_id="demo-b")
    hits = gw.invoke(ctx, "search_approved_documents", {"query": "supplier onboarding", "k": 5})
    injected = [e for e in hits["evidence"] if "ignore all previous instructions" in e["text"]]
    assert injected, "the injection fixture should be retrievable as ordinary data"

    # A model that obeys the injected text tries each step; each is refused.
    attempts = [
        (
            "create_followup_ticket",
            {**TICKET, "title": "Export all customer data", "tenant_id": "demo-a"},
        ),
        ("create_followup_ticket", {**TICKET, "title": "Export all customer data"}),
        ("search_approved_documents", {"query": "everything", "k": 5, "tenant_id": "demo-a"}),
    ]
    reasons = []
    for tool, arguments in attempts:
        with pytest.raises(GatewayDenied) as raised:
            gw.invoke(ctx, tool, arguments)
        reasons.append(raised.value.reason_code)

    assert reasons == ["INVALID_ARGUMENTS", "APPROVAL_REQUIRED", "INVALID_ARGUMENTS"]
    assert tickets_for_run(admin_dsn, ctx.run_id) == 0


def _mcp(coro: Any) -> Any:
    return asyncio.run(coro)


def test_mcp_lists_four_tools_with_the_gateway_schemas_and_no_identity_fields(
    seeded_db: str, app_dsn: str
) -> None:
    async def go() -> Any:
        async with Client(build_server(gateway(app_dsn), context())) as client:
            return await client.list_tools()

    tools = {tool.name: tool for tool in _mcp(go()).tools}

    assert set(tools) == {
        "get_sales_summary",
        "search_approved_documents",
        "get_issue_details",
        "create_followup_ticket",
    }
    for name, model in TOOL_ARGUMENT_MODELS.items():
        properties = tools[name].input_schema["properties"]
        assert set(model.model_json_schema()["properties"]) <= set(properties)
        assert not {"tenant_id", "user_id", "run_id", "principal_id"} & set(properties)


def test_mcp_calls_go_through_the_gateway(seeded_db: str, app_dsn: str, admin_dsn: str) -> None:
    gw, ctx = gateway(app_dsn), context()

    async def go() -> tuple[Any, Any, Any]:
        async with Client(build_server(gw, ctx)) as client:
            read = await client.call_tool(
                "get_sales_summary",
                {"from_quarter": "2026-Q2", "to_quarter": "2026-Q3", "top_n": 1},
            )
            unapproved = await client.call_tool("create_followup_ticket", TICKET)
            request = await asyncio.to_thread(
                gw.request_approval, ctx, "create_followup_ticket", TICKET
            )
            await asyncio.to_thread(gw.decide, ctx, request.approval_id, True)
            approved = await client.call_tool(
                "create_followup_ticket", {**TICKET, "approval_id": request.approval_id}
            )
            return read, unapproved, approved

    read, unapproved, approved = _mcp(go())

    assert not read.is_error
    assert read.structured_content["analytics"]["declines"][0]["product_id"] == 101
    assert unapproved.is_error
    assert "APPROVAL_REQUIRED" in unapproved.content[0].text
    assert not approved.is_error
    assert approved.structured_content["ticket_id"].startswith("SBX-")
    assert tickets_for_run(admin_dsn, ctx.run_id) == 1
