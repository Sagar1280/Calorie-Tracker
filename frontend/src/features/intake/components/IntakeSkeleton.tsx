export default function IntakeSkeleton() {
  return (
    <>
      <div className="skeleton skeleton-bmi" />
      <section className="card skeleton-card" aria-label="Loading day">
        <div className="skeleton skeleton-line skeleton-short" />
        <div className="skeleton skeleton-input" />
        <div className="skeleton skeleton-input" />
      </section>
      <section className="card skeleton-card">
        <div className="skeleton skeleton-line skeleton-short" />
        <div className="skeleton skeleton-line" />
        <div className="skeleton skeleton-line skeleton-medium" />
      </section>
      <p className="loading-caption">Loading your day…</p>
    </>
  );
}
