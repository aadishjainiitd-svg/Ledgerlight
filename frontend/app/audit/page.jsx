import { Suspense } from 'react';
import Audit from '@/components/Audit';
export const metadata = { title: 'Audit log · Ledgerlight' };
export default function Page() { return <Suspense fallback={null}><Audit /></Suspense>; }
