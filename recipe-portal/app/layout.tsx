import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Sigma API Recipe Portal',
  description: 'Interactive portal for Sigma API recipes and examples',
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