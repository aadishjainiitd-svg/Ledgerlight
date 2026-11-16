/* Light-only error page. Replaces Next built-in pages-router error page (it ships a prefers-color-scheme: dark rule).
   Used as pages/_error and swapped in for next/dist/pages/_error by next.config.mjs. */
function ErrorPage({ statusCode }) {
  return (
    <div style={{ minHeight: '100vh', background: '#f3f5f9', color: '#0e1a2e', fontFamily: 'Inter, system-ui, -apple-system, "Segoe UI", sans-serif', colorScheme: 'light' }}>
      <div style={{ maxWidth: 520, margin: '0 auto', padding: '15vh 16px 0' }}>
        <div style={{ padding: 28, background: '#fff', border: '1px solid #e1e6ef', borderRadius: 12 }}>
          <h1 style={{ margin: 0, fontSize: 24 }}>{statusCode === 404 ? 'This page is not in the ledger' : 'Something went wrong'}</h1>
          <p style={{ color: '#4b5a74' }}>{statusCode ? `Error ${statusCode}. ` : ''}Nothing was changed.</p>
          <a href="/" style={{ color: '#1d3fae', fontWeight: 600 }}>Back to the dashboard</a>
        </div>
      </div>
    </div>
  );
}
ErrorPage.getInitialProps = ({ res, err }) => ({ statusCode: res ? res.statusCode : err ? err.statusCode : 404 });
export default ErrorPage;
