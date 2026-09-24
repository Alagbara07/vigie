import { SystemStatus } from "@/components/system-status";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-full w-full max-w-3xl flex-1 flex-col justify-center px-6 py-16">
      <p className="text-sm font-semibold tracking-[0.22em] text-zinc-500">VIGIE</p>
      <h1 className="mt-4 max-w-2xl text-4xl font-semibold tracking-tight text-zinc-950">
        L&apos;intelligence qui veille sur votre entreprise.
      </h1>
      <p className="mt-4 max-w-xl text-lg text-zinc-600">
        Your business is talking all day. VIGIE tells you what matters.
      </p>
      <SystemStatus />
    </main>
  );
}
