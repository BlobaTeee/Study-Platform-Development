import type { Metadata } from 'next'
import { Fraunces, IBM_Plex_Mono, Open_Sans } from 'next/font/google'
import { AuthProvider } from '@/lib/auth-context'
import './globals.css'

const openSans = Open_Sans({
  subsets: ['latin'],
  variable: '--font-open-sans',
  display: 'swap',
})

const fraunces = Fraunces({
  subsets: ['latin'],
  variable: '--font-fraunces',
  display: 'swap',
  weight: ['500', '600'],
})

const plexMono = IBM_Plex_Mono({
  subsets: ['latin'],
  variable: '--font-plex-mono',
  display: 'swap',
  weight: ['500', '600'],
})

export const metadata: Metadata = {
  title: 'StudyFlow - Smart Study Platform',
  description: 'Master your studies with flashcards, quizzes, and comprehensive learning tools',
  icons: {
    icon: '/icon.svg',
  },
}

export default function RootLayout({
  children, 
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html
      lang="en"
      className={`${openSans.variable} ${fraunces.variable} ${plexMono.variable} bg-white`}
    >
      <body
        className={`${openSans.className} antialiased bg-white text-slate-900 text-[17px] leading-relaxed`}
      >
        <AuthProvider>
          {children}
        </AuthProvider>
      </body>
    </html>
  )
}
