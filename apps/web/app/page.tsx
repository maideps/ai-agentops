import { listReplays, loadReplay } from "@/lib/replays";

export default function CatalogPage() {
  const replays = listReplays().map((entry) => ({ entry, detail: loadReplay(entry.id).detail }));
  return (
    <>
      <h1>Recorded runs</h1>
      <p className="lede">
        Each run asked the platform to analyze synthetic sales data and company documents. Open
        one to see the report, the evidence it cites, every policy decision and the trace id.
      </p>
      <ul className="catalog">
        {replays.map(({ entry, detail }) => (
          <li key={entry.id} data-testid="replay-card">
            <a href={`/replays/${entry.id}/`}>
              <span className="title">{entry.title}</span>
              <span className={`status status-${detail.status}`}>{detail.status}</span>
            </a>
            <p>{entry.description}</p>
            <p className="meta">
              {detail.tenant_id} · {detail.user_id} · trace <code>{detail.trace_id}</code>
            </p>
          </li>
        ))}
      </ul>
    </>
  );
}
