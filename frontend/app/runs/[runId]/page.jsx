import LiveRun from '@/components/LiveRun';
export const metadata = { title: 'Live run · Ledgerlight' };
export default async function Page({ params }) { const { runId } = await params; return <LiveRun runId={runId} />; }
