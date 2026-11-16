'use client';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { Shimmer } from '@/lib/ui';

/** "Live run" in the rail: jump to the newest run, or invite the user to start one. */
export default function RunsIndex() {
  const router = useRouter();
  const [none, setNone] = useState(false);
  useEffect(() => {
    api('/api/runs?all_runs=true&sort=time&order=desc&page_size=1').then((d) => {
      if (d.items[0]) router.replace(`/runs/${d.items[0].run_id}`); else setNone(true);
    }).catch(() => setNone(true));
  }, [router]);
  if (!none) return <div className="card" style={{ padding: 20 }}><Shimmer w="40%" h={18} /><Shimmer h={120} style={{ marginTop: 14 }} /></div>;
  return <div className="card" style={{ maxWidth: 560 }}><div className="empty"><h4>No run to watch yet</h4><p>Start a sample or upload an invoice and the nine stages light up here as they run.</p><p style={{ marginTop: 12 }}><Link className="btn primary" href="/new">Start a new run</Link></p></div></div>;
}
