'use client';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { API, ApiError, api, getApiRole } from '@/lib/api';
import { Chip, Empty, ErrorBanner, Ic, PageHead, Shimmer, useApi, useApp } from '@/lib/ui';

const MB = 1048576;
const fmtSize = (n) => (n >= MB ? (n / MB).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB');

/** Upload with real progress (fetch has no upload progress events). */
function uploadFiles(files, pace, useCache, onProgress) {
  return new Promise((resolve, reject) => {
    const fd = new FormData();
    files.forEach((f) => fd.append('files', f));
    fd.append('pace', pace); fd.append('use_cache', useCache ? 'true' : 'false');
    const x = new XMLHttpRequest();
    x.open('POST', API + '/api/runs');
    x.setRequestHeader('X-Ledgerlight-Role', getApiRole());
    x.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100)); };
    x.onload = () => {
      let d = null; try { d = JSON.parse(x.responseText); } catch { /* ignore */ }
      if (x.status >= 200 && x.status < 300) resolve(d);
      else if (d && d.rejected) resolve({ runs: [], rejected: d.rejected });
      else reject(new ApiError((d && d.error) || `Upload failed (${x.status})`, x.status));
    };
    x.onerror = () => reject(new ApiError("Can't reach the Ledgerlight server. Check that the backend is running.", 0));
    x.send(fd);
  });
}

export default function NewRun() {
  const router = useRouter();
  const params = useSearchParams();
  const focus = params.get('focus');
  const { settings, setSettings, toast, rememberRun } = useApp();
  const [expect, setExpect] = useState(false);
  const [queue, setQueue] = useState([]);
  const [over, setOver] = useState(false);
  const [starting, setStarting] = useState(null);
  const [err, setErr] = useState(null);
  const inputRef = useRef(null);
  const { data, error, loading, reload } = useApi('/api/samples?reveal=true');
  const samples = data ? data.samples : [];

  useEffect(() => {
    if (!focus || !data) return;
    const el = document.getElementById(`sample-${focus}`);
    if (el) el.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [focus, data]);

  function addFiles(list) {
    const next = [];
    [...list].slice(0, 10).forEach((f) => {
      const isPdf = /\.pdf$/i.test(f.name) || f.type === 'application/pdf';
      const big = f.size > 10 * MB;
      next.push({ id: Math.random().toString(36).slice(2), file: f, name: f.name, size: fmtSize(f.size), ok: isPdf && !big, status: isPdf && !big ? 'Waiting' : 'Rejected', err: !isPdf ? 'Only PDF files are supported.' : big ? 'File is larger than 10 MB.' : '', p: 0 });
    });
    setQueue((q) => [...q, ...next].slice(0, 10));
  }

  async function startSample(id) {
    setErr(null); setStarting(id);
    try {
      const r = await api('/api/runs', { method: 'POST', body: { sample_id: id, pace: settings.speed, use_cache: settings.cache } });
      const run = r.runs[0];
      if (!run) throw new ApiError((r.rejected && r.rejected[0] && r.rejected[0].error) || 'The sample could not be started.', 400);
      rememberRun(`/runs/${run.run_id}`);
      router.push(`/runs/${run.run_id}`);
    } catch (e) { setErr(e); setStarting(null); }
  }

  async function startQueue() {
    const ready = queue.filter((q) => q.ok && q.status === 'Waiting');
    if (!ready.length) return;
    setErr(null); setStarting('queue');
    setQueue((q) => q.map((x) => (x.ok ? { ...x, status: 'Uploading', p: 1 } : x)));
    try {
      const r = await uploadFiles(ready.map((x) => x.file), settings.speed, settings.cache, (p) => setQueue((q) => q.map((x) => (x.status === 'Uploading' ? { ...x, p } : x))));
      const rej = r.rejected || [];
      setQueue((q) => q.map((x) => { const bad = rej.find((j) => j.file_name === x.name); return bad ? { ...x, ok: false, status: 'Rejected', err: bad.error } : x.status === 'Uploading' ? { ...x, status: 'Started', p: 100 } : x; }));
      if (!r.runs.length) { setStarting(null); return; }
      try { sessionStorage.setItem('ll-batch', JSON.stringify(r.runs.map((x) => ({ id: x.run_id, name: x.file_name })))); } catch { /* ignore */ }
      rememberRun(`/runs/${r.runs[0].run_id}`);
      router.push(`/runs/${r.runs[0].run_id}`);
    } catch (e) { setErr(e); setStarting(null); setQueue((q) => q.map((x) => (x.status === 'Uploading' ? { ...x, status: 'Waiting', p: 0 } : x))); }
  }

  const ready = queue.some((q) => q.ok && q.status === 'Waiting');
  const speedLabel = { slow: 'Slow for demo', normal: 'Normal', fast: 'Fast' };

  return (
    <>
      <PageHead title="New run" sub="Drop an invoice or pick a sample. Ledgerlight reads it, checks it against vendor and PO data, and gives a decision with reasons. Nothing is paid or sent automatically.">
        <Link className="btn ghost" href="/">Recent runs <Ic n="arrow-r" c="sm" /></Link>
      </PageHead>
      <div className="stack" style={{ gap: 18 }}>
        <ErrorBanner error={err} />
        <label className={`drop ${over ? 'over' : ''}`} id="dropzone" htmlFor="file-in" data-testid="dropzone"
          onDragEnter={(e) => { e.preventDefault(); setOver(true); }} onDragOver={(e) => { e.preventDefault(); setOver(true); }}
          onDragLeave={(e) => { e.preventDefault(); setOver(false); }} onDrop={(e) => { e.preventDefault(); setOver(false); addFiles(e.dataTransfer.files); }}>
          <div className="ico"><Ic n="upload" c="lg" /></div>
          <h3>{over ? 'Drop to upload' : <>Drag an invoice PDF here or <span style={{ color: 'var(--accent-fg)', textDecoration: 'underline' }}>browse</span></>}</h3>
          <p className="sec small">Up to 10 PDFs, 10 MB and 10 pages each. Scanned images and phone photos work too.</p>
          <input id="file-in" ref={inputRef} type="file" accept="application/pdf" multiple hidden data-testid="file-input" onChange={(e) => { addFiles(e.target.files); e.target.value = ''; }} />
        </label>

        {queue.length ? (
          <div className="card flat" data-testid="upload-queue">
            <div className="card-h" style={{ paddingBottom: 6 }}><h3>Upload queue</h3><span className="muted small">{queue.filter((x) => x.ok).length} ready</span></div>
            {queue.map((f) => (
              <div className="q-item" key={f.id}>
                <span><Ic n={f.ok ? 'file' : 'warn'} c={f.ok ? '' : 'c-reject'} /></span>
                <div className="trunc"><div className="trunc"><b>{f.name}</b></div>{f.err ? <div className="tiny" style={{ color: 'var(--reject-fg)' }}>{f.err}</div> : null}</div>
                <div>{f.ok ? <div className="bar"><i style={{ width: `${f.p}%` }} /></div> : null}</div>
                <span className="small muted nowrap">{f.size}</span>
                <span className="row gap-s"><span className={`chip ${f.status === 'Rejected' ? 's-reject' : f.status === 'Started' ? 's-auto' : f.status === 'Uploading' ? 's-running' : 's-none'}`}>{f.status}</span>
                  <button className="icon-btn" onClick={() => setQueue((q) => q.filter((x) => x.id !== f.id))} aria-label={`Remove ${f.name}`}><Ic n="x" c="sm" /></button></span>
              </div>
            ))}
          </div>
        ) : null}

        <details className="card" style={{ padding: 0 }}>
          <summary style={{ padding: '13px 18px', cursor: 'pointer', fontWeight: 700, listStyle: 'none', display: 'flex', gap: 8, alignItems: 'center' }}><Ic n="sliders" />Options<span className="muted small" style={{ fontWeight: 500 }}>Speed: {speedLabel[settings.speed]} · Saved AI results: {settings.cache ? 'on' : 'off'}</span></summary>
          <div className="card-b row wrap gap-l" style={{ borderTop: '1px solid var(--line)' }}>
            <div className="field-l">Processing speed
              <div className="seg" role="group">{['slow', 'normal', 'fast'].map((s) => <button key={s} aria-pressed={settings.speed === s} onClick={() => setSettings({ speed: s })}>{speedLabel[s]}</button>)}</div></div>
            <label className="row" style={{ marginTop: 18 }}><button className="toggle" role="switch" aria-checked={settings.cache} onClick={() => setSettings({ cache: !settings.cache })} aria-label="Use saved AI results" /><span><b>Use saved AI results</b><br /><span className="small muted">Replays the stored extraction so a demo is repeatable and works offline.</span></span></label>
          </div>
        </details>

        <div className="row wrap">
          <div><h2 style={{ fontSize: 18 }}>Sample invoices</h2><p className="sec small">Seven invoices that cover every outcome. Pick one to watch it run.</p></div>
          <label className="row right small sec" style={{ cursor: 'pointer' }}><button className="toggle" role="switch" aria-checked={expect} onClick={() => setExpect((e) => !e)} aria-label="Show what to expect" data-testid="toggle-expect" />Show what to expect</label>
        </div>
        {error && !data ? <ErrorBanner error={error} onRetry={reload} /> : null}
        <div className="samples" data-testid="samples">
          {loading && !data ? Array.from({ length: 7 }).map((_, i) => <div key={i} className="card sample"><Shimmer h={128} /><Shimmer w="60%" /><Shimmer /></div>) : null}
          {samples.map((s) => {
            const scanned = s.tags.some((t) => /scan/i.test(t));
            return (
              <div className="card sample" key={s.id} id={`sample-${s.id}`} data-testid={`sample-${s.id}`} style={focus === s.id ? { boxShadow: '0 0 0 3px color-mix(in srgb, var(--accent) 35%, transparent)' } : undefined}>
                <div className="thumb"><img src={`${API}${s.thumbnail_url}?dpi=40`} alt={`Thumbnail of ${s.file}`} style={{ height: 118, width: 'auto', maxWidth: '100%' }} loading="lazy" /></div>
                <div className="row gap-s wrap"><span className="tag">{s.id}</span><span className="tag">{s.vendor.split(' ')[0]}</span>{scanned ? <span className="pill accent">Scanned</span> : <span className="pill">Text PDF</span>}{s.run_before ? <span className="pill" data-tip="This sample has been run before">Run before</span> : null}</div>
                <div><h4>{s.invoice_no}</h4><p className="small sec" style={{ marginTop: 2 }}>{s.description}</p></div>
                {s.requires_llm && !s.runnable_now ? <div className="small" style={{ color: 'var(--hold-fg)', background: 'var(--hold-bg)', borderRadius: 8, padding: '6px 9px' }}>{s.note || 'Needs AI extraction. It will be put on hold with a clear reason.'}</div> : null}
                {expect ? <div className="row gap-s small sec fade-in">Expected: <Chip k={s.expected_outcome} />{s.requires_llm && !s.runnable_now ? <span className="tiny muted">(with an AI key)</span> : null}</div> : null}
                <button className="btn primary" style={{ marginTop: 'auto' }} disabled={!!starting} onClick={() => startSample(s.id)} data-testid={`run-${s.id}`}>{starting === s.id ? <><Ic n="spinner" c="sm spin" />Starting…</> : <><Ic n="play" c="sm" />Run this sample</>}</button>
              </div>
            );
          })}
        </div>
        <div className="row wrap"><button className="btn primary lg" disabled={!ready || !!starting} onClick={startQueue} data-testid="start-processing">Start processing</button><span className="small muted">{ready ? 'The first file opens in the live run view.' : 'Add a PDF or run a sample to begin.'}</span></div>
      </div>
    </>
  );
}
