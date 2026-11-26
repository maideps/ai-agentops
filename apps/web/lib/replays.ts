// Build-time access to the recorded replays in fixtures/replays (the single source of truth).
// Nothing here runs in the browser: pages are rendered to static HTML at build time.
import { readFileSync } from "node:fs";
import path from "node:path";

const REPLAYS_DIR = path.join(process.cwd(), "..", "..", "fixtures", "replays");

export type IndexEntry = { id: string; file: string; title: string; description: string };

export type PolicyDecision = {
  subject: string;
  decision: "allow" | "deny";
  reason_code: string;
  policy_version: string;
};

export type Evidence = { id: string; kind: string; source_uri: string; text: string };

export type DeclineRow = {
  product_id: number;
  product_name: string;
  region: string;
  from_revenue: string;
  to_revenue: string;
  change: string;
  citations: string[];
};

export type RunDetail = {
  run_id: string;
  thread_id: string;
  trace_id: string;
  tenant_id: string;
  user_id: string;
  task_text: string;
  status: string;
  abstain_reason: string | null;
  report: { summary: string; findings: { claim: string; citations: string[] }[] } | null;
  analytics: {
    from_quarter: string;
    to_quarter: string;
    total_from: string;
    total_to: string;
    declines: DeclineRow[];
  } | null;
  evidence: Evidence[];
  // feat-023: sources the user's role kept from the run (absent in replays recorded before it).
  evidence_gaps?: { tool: string; source: string; reason_code: string }[];
  context: { included_evidence_ids: string[]; dropped_evidence_ids: string[]; estimated_tokens: number };
  policy_decisions: PolicyDecision[];
  errors: { code: string; message: string }[];
  llm_provider: string;
  llm_model: string;
  llm_calls: number;
  tool_calls_executed: number;
  prompt_tokens: number;
  completion_tokens: number;
  proposed_action: {
    tool: string;
    arguments: Record<string, unknown>;
    approval_id: string;
    action_hash: string;
    policy_version: string;
    expires_at: string;
  } | null;
  action_result: { ticket_id: string; status: string; approval_id?: string } | null;
};

export function listReplays(): IndexEntry[] {
  const index = JSON.parse(readFileSync(path.join(REPLAYS_DIR, "index.json"), "utf-8"));
  return index.replays as IndexEntry[];
}

export function loadReplay(id: string): { entry: IndexEntry; detail: RunDetail } {
  const entry = listReplays().find((item) => item.id === id);
  if (!entry) throw new Error(`unknown replay ${id}`);
  const detail = JSON.parse(readFileSync(path.join(REPLAYS_DIR, entry.file), "utf-8")) as RunDetail;
  return { entry, detail };
}

/** A stable HTML id for an evidence item (evidence ids contain ':' and '#'). */
export function evidenceAnchor(id: string): string {
  return "ev-" + id.replace(/[^A-Za-z0-9_-]/g, "-");
}
