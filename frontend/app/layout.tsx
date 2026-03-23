import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'ITU Assistant',
  description: 'Multilingual ITU knowledge assistant with grounded answers.',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
