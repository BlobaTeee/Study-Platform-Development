import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Notebooks | StudyFlow',
  description: 'Organize study materials by subject in notebooks',
}

export default function NotebooksLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <div className="h-full min-h-0 flex flex-col">{children}</div>
}
