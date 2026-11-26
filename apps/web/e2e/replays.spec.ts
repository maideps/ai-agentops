// feat-009 (FR-015, FR-013): the replay UI works with no backend, no key and no model; every
// request stays on the local static server. Screenshots of each view are gate evidence.
import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

type Entry = { id: string; title: string };
const index = JSON.parse(
  readFileSync(path.join(__dirname, "..", "..", "..", "fixtures", "replays", "index.json"), "utf-8"),
) as { replays: Entry[] };
const PROVIDERS = /openai|anthropic|googleapis|groq|langfuse|litellm/i;

function guardNetwork(page: Page): string[] {
  const outside: string[] = [];
  page.on("request", (request) => {
    const host = new URL(request.url()).hostname;
    if (host !== "127.0.0.1" && host !== "localhost") outside.push(request.url());
  });
  // Block anything that is not the local static site, including model providers and the API.
  void page.route("**/*", (route) => {
    const url = new URL(route.request().url());
    const local = url.hostname === "127.0.0.1" && url.port === "4173";
    return local ? route.continue() : route.abort("blockedbyclient");
  });
  return outside;
}

test("catalog lists every recorded run, with no request leaving the machine", async ({ page }) => {
  const outside = guardNetwork(page);

  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Recorded runs" })).toBeVisible();
  await expect(page.getByTestId("replay-card")).toHaveCount(index.replays.length);
  await expect(page.getByRole("note")).toContainText("No model, API key or backend is called");
  await page.screenshot({ path: "test-results/shots/00-catalog.png", fullPage: true });
  expect(outside).toEqual([]);
});

for (const [n, entry] of index.replays.entries()) {
  test(`replay ${entry.id} shows its report, evidence, decisions and trace`, async ({ page }) => {
    const outside = guardNetwork(page);

    await page.goto(`/replays/${entry.id}/`);

    await expect(page.getByRole("heading", { level: 1, name: entry.title })).toBeVisible();
    for (const name of ["Report", "Policy decisions", "Trace"]) {
      await expect(page.getByRole("heading", { level: 2, name: new RegExp(`^${name}`) })).toBeVisible();
    }
    await expect(page.getByTestId("trace-id")).toHaveText(/^[0-9a-f]{32}$/);
    expect(await page.getByTestId("decision").count()).toBeGreaterThan(0);
    await page.screenshot({
      path: `test-results/shots/${String(n + 1).padStart(2, "0")}-${entry.id}.png`,
      fullPage: true,
    });
    expect(outside).toEqual([]);
    expect(outside.filter((url) => PROVIDERS.test(url))).toEqual([]);
  });
}

test("a citation jumps to the evidence it cites", async ({ page }) => {
  guardNetwork(page);
  await page.goto("/replays/sample-q3-declines/");

  const citation = page.locator(".citation", { hasText: "doc-a-returns-policy#1" }).first();
  await citation.click();

  await expect(page).toHaveURL(/#ev-doc-a-returns-policy-1$/);
  await expect(page.locator("#ev-doc-a-returns-policy-1")).toContainText("receipt");
});

test("the approval replay shows the bound proposal and the single ticket", async ({ page }) => {
  guardNetwork(page);
  await page.goto("/replays/approved-ticket/");

  await expect(page.getByRole("heading", { level: 2, name: "Approval", exact: true })).toBeVisible();
  await expect(page.getByTestId("action-result")).toHaveText(/^ticket SBX-[0-9A-F]{12} created$/);
});

test("the viewer replay shows the permission denial", async ({ page }) => {
  guardNetwork(page);
  await page.goto("/replays/viewer-denied/");

  await expect(page.getByTestId("decision").filter({ hasText: "PERMISSION_DENIED" })).toHaveCount(1);
  await expect(page.getByTestId("status")).toContainText("abstained");
  // feat-024: the gap the gateway recorded is stated above the report.
  await expect(page.getByTestId("evidence-gaps")).toContainText("sales data (get_sales_summary");
});

test("a run without a denied source shows no evidence gap", async ({ page }) => {
  guardNetwork(page);
  await page.goto("/replays/sample-q3-declines/");

  await expect(page.getByTestId("status")).toContainText("completed");
  await expect(page.getByTestId("evidence-gaps")).toHaveCount(0);
});
