import { Suspense } from 'react';
import NewRun from '@/components/NewRun';
export const metadata = { title: 'New run · Ledgerlight' };
export default function Page() { return <Suspense fallback={null}><NewRun /></Suspense>; }
