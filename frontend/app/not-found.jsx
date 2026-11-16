import Link from 'next/link';

export const metadata = { title: 'Page not found · Ledgerlight' };

export default function NotFound() {
  return (
    <div className="page" data-testid="not-found">
      <div className="card" style={{ maxWidth: 560, margin: '48px auto 0' }}>
        <div className="card-b stack" style={{ padding: '28px 28px 30px' }}>
          <div className="upper">Error 404</div>
          <h1 style={{ fontSize: 26, fontWeight: 800 }}>This page is not in the ledger</h1>
          <p className="sec">The address may be mistyped, or the run or invoice it pointed to no longer exists.</p>
          <div className="row wrap">
            <Link className="btn primary" href="/">Back to the dashboard</Link>
            <Link className="btn" href="/runs">Open the live run</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
