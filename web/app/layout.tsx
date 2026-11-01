import './globals.css';
import type { Metadata } from 'next';
import AppShell from './components/app-shell';

export const metadata: Metadata = {
  title: 'openHunt — your job search',
  description: 'A focused dashboard for discovering and tracking developer roles.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body><AppShell>{children}</AppShell></body>
    </html>
  );
}
