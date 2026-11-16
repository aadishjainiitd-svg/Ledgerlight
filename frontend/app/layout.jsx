import './globals.css';
import Shell from '@/components/Shell';

export const metadata = {
  title: 'Ledgerlight',
  description: 'AI invoice processing for accounts payable. The AI reads, rules decide, everyone can see why.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" style={{ colorScheme: 'light' }}>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&family=Manrope:wght@600;700;800&display=swap"
        />
        <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='9' fill='%232c55d9'/%3E%3Cpath d='M9 22V10m0 12h14' stroke='white' stroke-width='2.6' stroke-linecap='round' fill='none'/%3E%3C/svg%3E" />
      </head>
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
