import { evidenceAnchor, listReplays, loadReplay } from "@/lib/replays";

export const dynamicParams = false;

export function generateStaticParams() {
  return listReplays().map((entry) => ({ id: entry.id }));
}

function Citation({ id }: { id: string }) {
  return (
    <a className="citation" href={`#${evidenceAnchor(id)}`}>
      {id}
    </a>
  );
}

export default async function ReplayPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { entry, detail } = loadReplay(id);
  const denied = detail.policy_decisions.filter((d) => d.decision === "deny");
  const gaps = detail.evidence_gaps ?? [];
  return (
    <article>
      <p>
        <a href="/">All runs</a>
      </p>
      <h1>{entry.title}</h1>
      <p className="lede">{entry.description}</p>
      <dl className="facts">
        <dt>Status</dt>
        <dd data-testid="status">
          <span className={`status status-${detail.status}`}>{detail.status}</span>
          {detail.abstain_reason ? ` (${detail.abstain_reason})` : null}
        </dd>
        <dt>Task</dt>
        <dd>{detail.task_text}</dd>
        <dt>Principal</dt>
        <dd>
          {detail.user_id} in {detail.tenant_id}
        </dd>
      </dl>

      {gaps.length ? (
        <section aria-labelledby="gaps" className="gaps" data-testid="evidence-gaps">
          <h2 id="gaps">Not available to this user</h2>
          <p>
            The answer could not use{" "}
            {gaps.map((g) => `${g.source} (${g.tool}, ${g.reason_code})`).join(", ")}: the user&apos;s
            role may not use {gaps.length === 1 ? "this source" : "these sources"}.
          </p>
        </section>
      ) : null}

      <section aria-labelledby="report">
        <h2 id="report">Report</h2>
        {detail.report ? (
          <>
            <p>{detail.report.summary}</p>
            <ol className="findings">
              {detail.report.findings.map((finding, i) => (
                <li key={i} data-testid="finding">
                  {finding.claim}{" "}
                  <span className="cites">
                    {finding.citations.map((c) => (
                      <Citation key={c} id={c} />
                    ))}
                  </span>
                </li>
              ))}
            </ol>
          </>
        ) : (
          <p data-testid="no-report">
            No report: the run ended with status {detail.status}
            {detail.abstain_reason ? ` (${detail.abstain_reason})` : ""}.
          </p>
        )}
      </section>

      {detail.analytics ? (
        <section aria-labelledby="analytics">
          <h2 id="analytics">
            Sales declines {detail.analytics.from_quarter} to {detail.analytics.to_quarter}
          </h2>
          <table>
            <thead>
              <tr>
                <th>Product</th>
                <th>Region</th>
                <th>From</th>
                <th>To</th>
                <th>Change</th>
              </tr>
            </thead>
            <tbody>
              {detail.analytics.declines.map((row) => (
                <tr key={`${row.product_id}-${row.region}`}>
                  <td>{row.product_name}</td>
                  <td>{row.region}</td>
                  <td>{row.from_revenue}</td>
                  <td>{row.to_revenue}</td>
                  <td>{row.change}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      <section aria-labelledby="evidence">
        <h2 id="evidence">Evidence ({detail.evidence.length})</h2>
        <ul className="evidence">
          {detail.evidence.map((item) => (
            <li key={item.id} id={evidenceAnchor(item.id)} data-testid="evidence">
              <code>{item.id}</code>
              {detail.context.dropped_evidence_ids.includes(item.id) ? (
                <em> (dropped by the context budget)</em>
              ) : null}
              <blockquote>{item.text}</blockquote>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="policy">
        <h2 id="policy">
          Policy decisions ({detail.policy_decisions.length}, {denied.length} denied)
        </h2>
        <table>
          <thead>
            <tr>
              <th>Subject</th>
              <th>Decision</th>
              <th>Reason</th>
              <th>Policy version</th>
            </tr>
          </thead>
          <tbody>
            {detail.policy_decisions.map((d, i) => (
              <tr key={i} className={`decision-${d.decision}`} data-testid="decision">
                <td>
                  <code>{d.subject}</code>
                </td>
                <td>{d.decision}</td>
                <td>{d.reason_code}</td>
                <td>{d.policy_version}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {detail.proposed_action ? (
        <section aria-labelledby="approval">
          <h2 id="approval">Approval</h2>
          <dl className="facts">
            <dt>Proposed action</dt>
            <dd>
              <code>{detail.proposed_action.tool}</code>:{" "}
              {String(detail.proposed_action.arguments.title ?? "")}
            </dd>
            <dt>Action hash</dt>
            <dd>
              <code>{detail.proposed_action.action_hash}</code>
            </dd>
            <dt>Approval</dt>
            <dd>
              <code>{detail.proposed_action.approval_id}</code> (policy{" "}
              {detail.proposed_action.policy_version})
            </dd>
            <dt>Result</dt>
            <dd data-testid="action-result">
              {detail.action_result
                ? `ticket ${detail.action_result.ticket_id} ${detail.action_result.status}`
                : "not executed"}
            </dd>
          </dl>
        </section>
      ) : null}

      <section aria-labelledby="trace">
        <h2 id="trace">Trace</h2>
        <dl className="facts">
          <dt>Trace id</dt>
          <dd data-testid="trace-id">
            <code>{detail.trace_id}</code>
          </dd>
          <dt>Run / thread</dt>
          <dd>
            <code>{detail.run_id}</code> / <code>{detail.thread_id}</code>
          </dd>
          <dt>Model</dt>
          <dd>
            {detail.llm_provider} / {detail.llm_model}: {detail.llm_calls} calls,{" "}
            {detail.prompt_tokens + detail.completion_tokens} tokens (estimate)
          </dd>
          <dt>Tool calls</dt>
          <dd>{detail.tool_calls_executed}</dd>
          {detail.errors.length ? (
            <>
              <dt>Errors</dt>
              <dd>{detail.errors.map((e) => e.code).join(", ")}</dd>
            </>
          ) : null}
        </dl>
      </section>
    </article>
  );
}
