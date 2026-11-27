export default function NotebooksLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <div className="h-full min-h-0 flex flex-col">{children}</div>
}
