import { Suspense } from 'react';
import Decision from '@/components/Decision';
export const metadata = { title: 'Invoice decision · Ledgerlight' };
export default async function Page({ params }) { const { runId } = await params; return <Suspense fallback={null}><Decision runId={runId} /></Suspense>; }
