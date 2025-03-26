import type { Metadata } from 'next'
import './globals.css'
import { BackgroundInitializer } from './components/background-initializer'
import { PostHogProvider } from './providers'

export const metadata: Metadata = {
  title: 'ArXiv DayZ',
  description: '每日 arXiv 摘要快讯',
  icons: {
    icon: '/favicon.png',
    shortcut: '/favicon.png',
  },
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="zh-Hans">
      <body>
        <BackgroundInitializer />
        <PostHogProvider>
          {children}
        </PostHogProvider>
      </body>
    </html>
  )
}
