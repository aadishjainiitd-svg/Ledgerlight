'use client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { fmtDT } from '@/lib/format';
import { Chip, ErrorBanner, Ic, Modal, PageHead, Shimmer, useApi, useApp } from '@/lib/ui';

const GROUPS = ['Fields', 'Vendor', 'Duplicate', 'Purchase order', 'Numbers'];
const OUT_FROM = { auto_approve: 'auto', approve_with_note: 'note', route_for_review: 'review', hold_request_info: 'hold', reject: 'reject' };
const GLOBAL_LABELS = { cap: 'High-value cap (₹)', split: 'Exposure split, clerk up to (₹)', sample: 'Audit sample (%)', sla: 'Hold SLA (days)', baseline: 'Manual minutes per invoice' };

export default function Rules() {
  const { toast, tick, roleTick } = useApp();
  const { data: s, error, loading, reload } = useApi('/api/settings', { deps: [roleTick] });
  const [draft, setDraft] = useState({ rules: {}, enabled: {}, global: {} });
  const [open, setOpen] = useState(new Set());
  const [preview, setPreview] = useState(null);
  const [saving, setSaving] = useState(false);
  const [modal, setModal] = useState(null); // 'save' | 'defaults' | 'previous'
  const [why, setWhy] = useState('');
  const [err, setErr] = useState(null);
  const seq = useRef(0);

  useEffect(() => { setDraft({ rules: {}, enabled: {}, global: {} }); setPreview(null); }, [s && s.version]);

  /* the patch is the diff between the draft and what the server has */
  const patch = useMemo(() => {
    if (!s) return null; const out = { rules: {}, enabled: {}, global: {} };
    s.rules.forEach((r) => {
      const d = draft.rules[r.id];
      if (d) { const ch = {}; Object.keys(d).forEach((k) => { const v = d[k]; if (v === '' || Number.isNaN(Number(v))) ch[k] = v; else if (Number(v) !== r.params[k]) ch[k] = Number(v); }); if (Object.keys(ch).length) out.rules[r.id] = ch; }
      if (draft.enabled[r.id] !== undefined && draft.enabled[r.id] !== r.enabled) out.enabled[r.id] = draft.enabled[r.id];
    });
    Object.entries(draft.global).forEach(([k, v]) => { const cur = s.config.global[k]; if (v !== cur && !(typeof cur === 'number' && Number(v) === cur)) out.global[k] = typeof cur === 'number' ? (v === '' ? v : Number(v)) : v; });
    return out;
  }, [draft, s]);
  const dirtyCount = patch ? Object.keys(patch.rules).length + Object.keys(patch.enabled).length + Object.keys(patch.global).length : 0;

  /* live sentence + impact preview from the real engine */
  useEffect(() => {
    if (!patch || !dirtyCount) { setPreview(null); return undefined; }
    const my = ++seq.current;
    const t = setTimeout(async () => {
      try { const r = await api('/api/settings/preview', { method: 'POST', body: { config: patch, days: 90 } }); if (my === seq.current) setPreview(r); }
      catch (e) { if (my === seq.current) setPreview({ valid: false, errors: { _: e.message } }); }
    }, 350);
    return () => clearTimeout(t);
  }, [patch, dirtyCount]);

  const errs = (preview && preview.errors) || {};
  const invalid = preview && preview.valid === false;
  const fieldErr = (id, k) => errs[`${id}.${k}`] || (errs[id] && typeof errs[id] === 'object' ? errs[id][k] : null);

  const setParam = (id, k, v) => setDraft((d) => ({ ...d, rules: { ...d.rules, [id]: { ...(d.rules[id] || {}), [k]: v } } }));
  const toggleOpen = (id) => setOpen((o) => { const n = new Set(o); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const curVal = (r, k) => (draft.rules[r.id] && draft.rules[r.id][k] !== undefined ? draft.rules[r.id][k] : r.params[k]);

  async function confirm() {
    setSaving(true); setErr(null);
    try {
      if (modal === 'save') { const r = await api('/api/settings', { method: 'PUT', body: { config: patch, reason: why.trim() } }); toast(r.message || 'Settings saved. New runs use these values. Existing decisions are unchanged unless you re-run them.'); }
      else { const r = await api('/api/settings/revert', { method: 'POST', body: { to: modal, reason: why.trim() } }); toast(`Rule set restored as version ${r.version}. Existing decisions are unchanged unless you re-run them.`); }
      setModal(null); setWhy(''); reload();
    } catch (e) { setErr(e); } finally { setSaving(false); }
  }

  const sentence = (r) => (preview && preview.sentences && preview.sentences[r.id]) || r.sentence;
  const changes = preview && preview.changes ? Object.entries(preview.changes) : [];

  return (
    <>
      <PageHead title="Rules and tolerances" sub="Every check in plain language. Change a number, see the sentence change, and see what it would do to past decisions.">
        <span className={`pill ${dirtyCount ? 'accent' : ''}`} id="dirty-pill" data-testid="dirty-pill">{dirtyCount ? `${dirtyCount} unsaved change${dirtyCount > 1 ? 's' : ''}` : s ? `Rule set version ${s.version}` : ''}</span>
        <button className="btn" onClick={() => { setModal('defaults'); setErr(null); }} data-testid="revert-defaults">Revert to defaults</button>
        <button className="btn" onClick={() => { setModal('previous'); setErr(null); }} disabled={!s || s.version <= 1}>Revert to previous version</button>
        <button className="btn primary" disabled={!dirtyCount || invalid} onClick={() => { setModal('save'); setErr(null); }} data-testid="save-rules">Save with reason</button>
      </PageHead>
      <ErrorBanner error={error} onRetry={reload} />
      {loading && !s ? <div className="stack"><Shimmer h={200} style={{ borderRadius: 12 }} /><Shimmer h={260} style={{ borderRadius: 12 }} /></div> : null}
      {s ? (
        <div className="two-col">
          <div className="stack" data-testid="rule-groups">
            {GROUPS.map((g) => {
              const rules = s.rules.filter((r) => r.group === g); if (!rules.length) return null;
              return (
                <div className="card" key={g}><div className="card-h" style={{ paddingBottom: 10, borderBottom: '1px solid var(--line)' }}><h3>{g}</h3><span className="muted small">{rules.map((r) => r.id).join(', ')}</span></div>
                  {rules.map((r) => {
                    const hasP = Object.keys(r.params || {}).length > 0; const isOpen = open.has(r.id); const edited = !!patch.rules[r.id] || !r.is_default;
                    const on = draft.enabled[r.id] !== undefined ? draft.enabled[r.id] : r.enabled;
                    return (
                      <div className={`rule-row ${isOpen ? 'open' : ''}`} id={`rr-${r.id}`} key={r.id} data-testid="settings-rule">
                        <div><button className="toggle" role="switch" aria-checked={on} disabled={!r.can_disable} aria-label={`${r.name} enabled`} data-tip={!r.can_disable ? 'Hard-stop rules cannot be disabled' : undefined} onClick={() => setDraft((d) => ({ ...d, enabled: { ...d.enabled, [r.id]: !on } }))} /></div>
                        <div className="grow" style={{ minWidth: 0 }}>
                          <h4>{r.name}<span className="rid">{r.id}</span>{r.hard ? <span className="pill"><Ic n="lock" c="sm" />Hard stop</span> : null}{edited ? <span className="pill accent">Edited</span> : <span className="pill">Default</span>}</h4>
                          <p className="sec" style={{ marginTop: 3 }} data-testid={`sentence-${r.id}`}>{sentence(r)}</p></div>
                        <div className="rr-act"><button className="btn sm" onClick={() => toggleOpen(r.id)} data-testid={`edit-${r.id}`}><Ic n="edit" c="sm" />{isOpen ? 'Close' : 'Edit'}</button></div>
                        <div className="editor">
                          {hasP ? <div className="params">{Object.keys(r.params).map((k) => { const e = fieldErr(r.id, k); return (
                            <label className={`field-l ${e ? 'bad' : ''}`} key={k}>{r.param_labels[k] || k}<input type="number" step="any" id={`in-${r.id}-${k}`} data-testid={`in-${r.id}-${k}`} value={curVal(r, k)} onChange={(ev) => setParam(r.id, k, ev.target.value)} aria-invalid={!!e} />{e ? <span className="err-t">{e}</span> : null}</label>); })}</div>
                            : <p className="small sec">This rule has no thresholds. It is a yes or no check.{r.hard ? ' It is a hard stop and cannot be switched off.' : ''}</p>}
                          {r.band ? <div className="row wrap gap-s small sec" style={{ marginTop: 10 }}><span>Severity for each band:</span><span className="chip s-auto">Passes</span><Ic n="arrow-r" c="sm" /><span className="chip s-note">Note</span><Ic n="arrow-r" c="sm" /><span className="chip s-review">Review</span><Ic n="arrow-r" c="sm" /><span className="chip s-reject">Reject</span><span className="muted">(fixed bands, thresholds editable)</span></div> : null}
                          <div className="preview-sent"><b>Preview.</b> <span>{sentence(r)}</span></div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
          <div className="stack" style={{ position: 'sticky', top: 76 }}>
            <div className="card" data-testid="impact-card"><div className="card-h"><h3>Impact preview</h3><span className="pill right">Last 90 days</span></div>
              <div className="card-b">
                {dirtyCount && preview && preview.valid !== false ? (
                  <>
                    <p><b>{preview.would_change ? `If you save this, ${preview.would_change} of the last 90 days' decisions would change.` : `If you save this, none of the ${preview.checked_runs} checked decisions would change.`}</b></p>
                    <div className="stack-s" style={{ marginTop: 10 }}>{changes.map(([k, n]) => { const [a, b] = k.split('->'); return <div className="row gap-s" key={k}><Chip k={OUT_FROM[a] || a} /><Ic n="arrow-r" c="sm" /><Chip k={OUT_FROM[b] || b} /><b className="right num">{n}</b></div>; })}</div>
                    {(preview.invoices || []).length ? <div className="small sec" style={{ marginTop: 10 }}>{preview.invoices.slice(0, 4).map((i) => <div key={i.invoice_id}><span className="mono">{i.invoice_no}</span>: {OUT_FROM[i.from] || i.from} to {OUT_FROM[i.to] || i.to}</div>)}</div> : null}
                    <p className="small muted" style={{ marginTop: 10 }}>Existing decisions stay as they are unless you re-run them.{preview.note ? ` ${preview.note}` : ''}</p>
                  </>
                ) : dirtyCount && invalid ? <p style={{ color: 'var(--reject-fg)' }}><b>Fix the highlighted fields to see the impact.</b></p>
                  : dirtyCount ? <Shimmer h={46} />
                    : <p className="sec">Change a threshold and Ledgerlight shows how many past decisions would flip. Nothing is saved until you give a reason.</p>}
              </div></div>
            <div className="card"><div className="card-h"><h3>Global settings</h3></div><div className="card-b stack-s" style={{ gap: 12 }}>
              {Object.entries(GLOBAL_LABELS).map(([k, l]) => <label className="field-l" key={k}>{l}<input type="number" id={`g-${k}`} value={draft.global[k] !== undefined ? draft.global[k] : s.config.global[k]} onChange={(e) => setDraft((d) => ({ ...d, global: { ...d.global, [k]: e.target.value } }))} /></label>)}
              <label className="field-l">Date order<select id="g-do" value={draft.global.dateOrder || s.config.global.dateOrder} onChange={(e) => setDraft((d) => ({ ...d, global: { ...d.global, dateOrder: e.target.value } }))}><option>Day first</option><option>Month first</option></select></label>
              <label className="row"><button className="toggle" role="switch" aria-checked={draft.global.auto !== undefined ? draft.global.auto : s.config.global.auto} onClick={() => setDraft((d) => ({ ...d, global: { ...d.global, auto: !(d.global.auto !== undefined ? d.global.auto : s.config.global.auto) } }))} aria-label="Auto-approve enabled" /><span><b>Auto-approve enabled</b><br /><span className="small muted">Turn off to send every invoice to a person.</span></span></label></div></div>
            <div className="card"><div className="card-h"><h3>Change log</h3></div><div className="card-b"><div className="tl">{s.history.slice(0, 8).map((l, i) => <div className={`ev ${i === 0 ? 'now' : ''}`} key={l.version} style={{ '--evc': 'var(--accent)' }}><div className="row gap-s"><span className={`pill ${i === 0 ? 'accent' : ''}`}>v{l.version}</span><span className="small muted">{fmtDT(l.changed_at)}</span></div><div style={{ marginTop: 2 }}><b>{l.summary}</b></div><div className="small sec">{l.changed_by}: {l.reason}</div></div>)}</div></div></div>
          </div>
        </div>
      ) : null}

      <Modal open={!!modal} onClose={() => setModal(null)} label="Save with reason">
        <div className="sheet-h"><h3>{modal === 'save' ? `Save ${dirtyCount} change${dirtyCount > 1 ? 's' : ''}` : modal === 'defaults' ? 'Revert to the shipped defaults' : 'Revert to the previous version'}</h3><button className="icon-btn right" onClick={() => setModal(null)} aria-label="Close"><Ic n="x" /></button></div>
        <div className="sheet-b">
          {err ? <div className="banner bad" role="alert"><Ic n="warn" /><span>{err.message}{err.fields ? ' ' + Object.entries(err.fields).map(([k, v]) => `${k}: ${v}`).join(' · ') : ''}</span></div> : null}
          {modal === 'save' && patch ? <div className="small sec">{Object.entries(patch.rules).map(([id]) => <div key={id}><b>{id}</b> {sentence(s.rules.find((r) => r.id === id))}</div>)}{Object.keys(patch.enabled).map((id) => <div key={id}><b>{id}</b> switched {patch.enabled[id] ? 'on' : 'off'}</div>)}{Object.keys(patch.global).map((k) => <div key={k}><b>{GLOBAL_LABELS[k] || k}</b> changed</div>)}</div> : <p className="small sec">This saves a new version of the rule set. The history stays in the change log.</p>}
          <label className="field-l">Reason for the change (required)<textarea id="sv-why" data-testid="save-reason" value={why} onChange={(e) => setWhy(e.target.value)} placeholder="For example: aligned with the new contract terms" /></label>
        </div>
        <div className="sheet-f"><button className="btn" onClick={() => setModal(null)}>Cancel</button><button className="btn primary" id="sv-go" data-testid="confirm-save" disabled={why.trim().length < 10 || saving} onClick={confirm}>{saving ? 'Saving…' : modal === 'save' ? 'Save settings' : 'Revert'}</button></div>
      </Modal>
    </>
  );
}
