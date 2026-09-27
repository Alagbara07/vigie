export function ErrorNotice({
  onRetry,
  title = "VIGIE couldn't load your signals.",
  detail = "Try again.",
}: {
  onRetry: () => void;
  title?: string;
  detail?: string;
}) {
  return (
    <section className="max-w-lg border border-[var(--line)] bg-[var(--panel)] px-5 py-6" role="alert">
      <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
      <p className="mt-2 text-sm leading-6 text-[var(--muted)]">{detail}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-5 border border-[var(--ink)] px-3 py-2 text-sm font-medium"
      >
        Try again
      </button>
    </section>
  );
}

export function MissingBusiness() {
  return (
    <section className="max-w-lg border border-[var(--line)] bg-[var(--panel)] px-5 py-6">
      <h1 className="text-xl font-semibold tracking-tight">Adaeze Wears isn&apos;t available yet.</h1>
      <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
        The demo business has not been loaded into this workspace.
      </p>
    </section>
  );
}

export function EmptyAttention() {
  return (
    <div className="border border-[var(--line)] bg-[var(--panel)] px-5 py-8">
      <p className="max-w-md text-sm leading-6 text-[var(--muted)]">
        Nothing needs your attention right now.
      </p>
    </div>
  );
}

export function DashboardSkeleton() {
  return (
    <div aria-busy="true" aria-live="polite">
      <p className="sr-only">Looking for what needs your attention</p>
      <div className="h-4 w-24 bg-[var(--line)]" />
      <div className="mt-3 h-4 w-72 bg-[var(--line)]" />
      <div className="mt-8 h-10 w-64 bg-[var(--line)]" />
      <div className="mt-8 grid grid-cols-2 gap-px bg-[var(--line)] md:grid-cols-4">
        {Array.from({ length: 4 }, (_, index) => (
          <div key={index} className="h-24 bg-[var(--panel)]" />
        ))}
      </div>
      <div className="mt-10 space-y-4">
        {Array.from({ length: 2 }, (_, index) => (
          <div key={index} className="h-28 border border-[var(--line)] bg-[var(--panel)]" />
        ))}
      </div>
    </div>
  );
}

export function DetailSkeleton({ label = "Opening this item" }: { label?: string }) {
  return (
    <div aria-busy="true" aria-live="polite" className="max-w-2xl">
      <p className="sr-only">{label}</p>
      <div className="h-4 w-32 bg-[var(--line)]" />
      <div className="mt-6 h-8 w-64 bg-[var(--line)]" />
      <div className="mt-8 h-40 border border-[var(--line)] bg-[var(--panel)]" />
    </div>
  );
}
