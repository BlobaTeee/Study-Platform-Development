import type { Metadata } from 'next'
import { Fraunces, IBM_Plex_Mono, Open_Sans } from 'next/font/google'
import { NextIntlClientProvider } from 'next-intl'
import { getLocale, getTranslations } from 'next-intl/server'
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

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations('common')
  return {
    title: t('metaTitle'),
    description: t('metaDescription'),
    icons: {
      icon: '/icon.svg',
    },
  }
}

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  // From the `lang` cookie, Vietnamese without one — see i18n/request.ts.
  // The server renders the chosen language from the first byte.
  const locale = await getLocale()
  return (
    <html
      lang={locale}
      className={`${openSans.variable} ${fraunces.variable} ${plexMono.variable} bg-white`}
    >
      <body
        className={`${openSans.className} antialiased bg-white text-slate-900 text-[17px] leading-relaxed`}
      >
        <NextIntlClientProvider>
          <AuthProvider>
            {children}
          </AuthProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  )
}
