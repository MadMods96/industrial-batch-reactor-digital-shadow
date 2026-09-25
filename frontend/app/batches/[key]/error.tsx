"use client";

export default function BatchError({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <main className="page">
      <div className="kicker">Replay</div>
      <h1 style={{ fontWeight: 500 }}>Could not open this batch</h1>
      <div className="banner">{error.message}</div>
      <button type="button" className="chip on" onClick={reset}>
        Try again
      </button>
    </main>
  );
}
