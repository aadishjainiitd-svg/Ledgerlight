'use client';
/* Last-resort error boundary. Self-contained and light only (it replaces the root layout when it renders). */
export default function GlobalError({ reset }) {
  return (
    <html lang="en" style={{ colorScheme: 'light' }}>
      <body style={{ margin: 0, background: '#f3f5f9', color: '#0e1a2e', fontFamily: 'Inter, system-ui, -apple-system, "Segoe UI", sans-serif' }}>
        <div style={{ maxWidth: 520, margin: '15vh auto 0', padding: 28, background: '#fff', border: '1px solid #e1e6ef', borderRadius: 12 }}>
          <h1 style={{ margin: 0, fontSize: 24 }}>Something went wrong</h1>
          <p style={{ color: '#4b5a74' }}>Ledgerlight hit an unexpected error. Nothing was changed. Try again, or reload the page.</p>
          <button type="button" onClick={() => reset()} style={{ background: '#2c55d9', color: '#fff', border: 0, borderRadius: 8, padding: '8px 14px', fontWeight: 600, cursor: 'pointer' }}>Try again</button>
        </div>
      </body>
    </html>
  );
}
