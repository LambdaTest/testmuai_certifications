import Link from "next/link";

// Candidate-area chrome (routes.md: "(candidate) → Candidate nav layout").
// Grows nav links (dashboard, account) once those pages exist.
export default function CandidateLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <>
      <header className="sticky top-0 z-40 border-b bg-card/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-4">
          <Link href="/" className="flex items-baseline gap-2">
            <span className="text-lg font-bold tracking-tight">TestMu AI</span>
            <span className="text-sm text-muted-foreground">Certifications</span>
          </Link>
          <span className="rounded-full border px-2.5 py-0.5 text-xs text-muted-foreground">
            Preview build
          </span>
        </div>
      </header>
      <div className="flex-1">{children}</div>
    </>
  );
}
