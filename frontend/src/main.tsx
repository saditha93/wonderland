import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const services = [
  { id: 'attractions', name: 'Attractions', detail: 'Catalog and suitability guidance' },
  { id: 'booking', name: 'Booking', detail: 'Tiers, payments and digital tickets' },
  { id: 'gate', name: 'Gate & rides', detail: 'Arrivals and ride usage' },
  { id: 'analytics', name: 'Analytics', detail: 'Timestamped reporting events' },
];
type Result = { state: 'checking' | 'ok' | 'unavailable'; version?: string };
function App() {
  const [results, setResults] = useState<Record<string, Result>>({});
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    const timeout = window.setTimeout(() => controller.abort(), 5000);
    setResults({});
    void Promise.all(services.map(async ({ id }) => {
      try {
        const response = await fetch(`/api/${id}/health`, { signal: controller.signal });
        if (!response.ok) throw new Error('Health request failed');
        const data: unknown = await response.json();
        if (typeof data !== 'object' || data === null || !('status' in data) || data.status !== 'ok') throw new Error('Invalid health response');
        if (!cancelled && !controller.signal.aborted) setResults(current => ({ ...current, [id]: { state: 'ok', version: 'version' in data ? String(data.version) : undefined } }));
      } catch {
        if (!cancelled) setResults(current => ({ ...current, [id]: { state: 'unavailable' } }));
      }
    })).finally(() => window.clearTimeout(timeout));
    return () => { cancelled = true; window.clearTimeout(timeout); controller.abort(); };
  }, [refresh]);
  return <>
    <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6"><a href="#main" className="text-xl font-black tracking-tight">WONDERLAND<span className="ml-2 text-amber-600">✳</span></a><span className="rounded-full border border-teal-900/20 px-3 py-1 text-xs font-semibold uppercase tracking-widest">Local foundation</span></header>
    <main id="main" className="mx-auto max-w-6xl px-6 pb-16">
      <section className="hero relative overflow-hidden rounded-3xl bg-teal-950 px-8 py-16 text-white sm:px-14">
        <p className="mb-4 text-xs font-semibold uppercase tracking-[.25em] text-amber-300">Wonderland Theme Park</p>
        <h1 className="max-w-2xl text-4xl font-bold leading-tight sm:text-6xl">A little wonder.<br/>A world of possibility.</h1>
        <p className="mt-6 max-w-lg text-base leading-relaxed text-teal-100">The beginning of our cloud-native booking and park analytics platform. Built locally, one verified step at a time.</p>
        <span className="mt-8 inline-block rounded-full bg-amber-300 px-5 py-2 text-sm font-semibold text-teal-950">Phase 0 + minimal Phase 1</span>
      </section>
      <section className="mt-12" aria-labelledby="services-title">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-widest text-teal-700">Behind the experience</p><h2 id="services-title" className="mt-2 text-2xl font-bold">Service health</h2></div><button onClick={() => setRefresh(x => x + 1)} className="rounded-full border border-teal-900 px-5 py-2 text-sm font-semibold hover:bg-teal-100 focus-visible:outline-2 focus-visible:outline-offset-4">Refresh status</button></div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{services.map(service => {
          const result = results[service.id] ?? { state: 'checking' };
          return <article key={service.id} className="rounded-2xl border border-teal-900/10 bg-white p-6"><h3 className="text-lg font-bold">{service.name}</h3><p className="mt-2 min-h-12 text-sm leading-relaxed text-slate-600">{service.detail}</p><p aria-live="polite" className={`mt-5 text-sm font-semibold ${result.state === 'ok' ? 'text-teal-700' : 'text-slate-600'}`}>{result.state === 'ok' ? `● Skeleton responding · ${result.version ?? ''}` : result.state === 'checking' ? '◌ Checking…' : '○ Unavailable'}</p></article>;
        })}</div>
        <p className="mt-5 max-w-3xl text-sm leading-relaxed text-slate-600">These checks verify the health-only API processes. Booking, login, payment, gate operations and analytics processing are planned for later phases. No cloud resources are connected.</p>
      </section>
    </main><footer className="border-t border-teal-900/10 px-6 py-6 text-center text-xs text-slate-500">SE6020 · Individual MSc project · Local development</footer>
  </>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
