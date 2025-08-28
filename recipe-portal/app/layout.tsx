import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'QuickStarts API Toolkit',
  description: 'Experiment with Sigma API calls and learn common request flows',
  icons: {
    icon: '/crane.png',
    shortcut: '/crane.png',
    apple: '/crane.png',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className="bg-gray-50 text-gray-900">
        {children}
      </body>
    </html>
  )
}