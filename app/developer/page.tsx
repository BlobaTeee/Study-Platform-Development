import Link from 'next/link'
import { ExternalLink, Database, Shield, ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/button'

const links = [
  {
    title: 'Django Admin',
    description: 'Manage users, materials, flashcards, and quizzes through the web UI.',
    href: 'http://localhost:8000/admin/',
    icon: Shield,
  },
  {
    title: 'API overview',
    description: 'Check that the backend is running and see available API paths.',
    href: 'http://localhost:8000/api/',
    icon: ExternalLink,
  },
]

export default function DeveloperPage() {
  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 px-4 py-12">
      <div className="mx-auto max-w-2xl space-y-8">
        <Button variant="ghost" asChild className="text-slate-300 hover:text-white">
          <Link href="/">
            <ArrowLeft className="mr-2 size-4" />
            Back to home
          </Link>
        </Button>

        <div className="space-y-2 text-center">
          <h1 className="text-3xl font-bold text-white">Developer access</h1>
          <p className="text-slate-400">Quick links for admin and database tools</p>
        </div>

        <div className="space-y-4">
          {links.map(({ title, description, href, icon: Icon }) => (
            <a
              key={title}
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="flex gap-4 rounded-xl border border-slate-700 bg-slate-800/50 p-6 transition-colors hover:border-blue-500/50 hover:bg-slate-800"
            >
              <Icon className="size-8 shrink-0 text-blue-500" />
              <div>
                <h2 className="text-lg font-semibold text-white">{title}</h2>
                <p className="mt-1 text-sm text-slate-400">{description}</p>
                <p className="mt-2 font-mono text-xs text-blue-400">{href}</p>
              </div>
            </a>
          ))}
        </div>

        <div className="rounded-xl border border-slate-700 bg-slate-800/50 p-6">
          <div className="flex gap-3">
            <Database className="size-8 shrink-0 text-emerald-500" />
            <div className="space-y-3 text-sm text-slate-300">
              <h2 className="text-lg font-semibold text-white">pgAdmin 4</h2>
              <p>
                pgAdmin is a desktop app (not a browser tab in this project). Open it from
                Applications, then connect with:
              </p>
              <ul className="list-inside list-disc space-y-1 text-slate-400">
                <li>Host: <span className="font-mono text-slate-200">localhost</span></li>
                <li>Port: <span className="font-mono text-slate-200">5432</span></li>
                <li>Database: <span className="font-mono text-slate-200">studyflow</span></li>
                <li>Username: <span className="font-mono text-slate-200">studyflow_user</span></li>
                <li>Password: same as <span className="font-mono text-slate-200">DB_PASSWORD</span> in <span className="font-mono">backend/.env</span></li>
              </ul>
              <p className="font-medium text-amber-200/90">Where to find tables:</p>
              <p className="font-mono text-xs leading-relaxed text-slate-400">
                Servers → your server → Databases → studyflow → Schemas → public → Tables
              </p>
              <p className="text-slate-500">
                If Tables is empty, run{' '}
                <span className="font-mono text-slate-300">python manage.py migrate</span> in the{' '}
                <span className="font-mono text-slate-300">backend</span> folder.
              </p>
            </div>
          </div>
        </div>
      </div>
    </main>
  )
}
