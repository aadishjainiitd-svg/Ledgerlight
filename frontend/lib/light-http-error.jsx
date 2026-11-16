/* Light-only stand-in for next/dist/client/components/http-access-fallback/error-fallback
   (the original inlines a prefers-color-scheme: dark rule). Swapped in by next.config.mjs. */
export function HTTPAccessErrorFallback({ status, message }) {
  return (
    <>
      <title>{`${status}: ${message}`}</title>
      <div style={{ minHeight: '100vh', background: '#f3f5f9', color: '#0e1a2e', fontFamily: 'Inter, system-ui, -apple-system, "Segoe UI", sans-serif', display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center', flexDirection: 'column' }}>
        <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700 }}>{status}</h1>
        <h2 style={{ margin: '8px 0 0', fontSize: 14, fontWeight: 400, color: '#4b5a74' }}>{message}</h2>
      </div>
    </>
  );
}
export default HTTPAccessErrorFallback;
