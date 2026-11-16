import { Suspense } from 'react';
import Queue from '@/components/Queue';
export const metadata = { title: 'Review queue · Ledgerlight' };
export default function Page() { return <Suspense fallback={null}><Queue /></Suspense>; }
