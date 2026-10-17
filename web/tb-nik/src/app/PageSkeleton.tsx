export function PageSkeleton() {
  return (
    <div className="p-4 md:p-6 max-w-6xl mx-auto space-y-3" aria-busy="true" aria-label="Loading">
      <div className="skeleton-line h-7 w-1/3" />
      <div className="skeleton-line h-4 w-2/3" />
      <div className="surface p-4 space-y-3 mt-4">
        <div className="skeleton-line h-4 w-full" />
        <div className="skeleton-line h-4 w-5/6" />
        <div className="skeleton-line h-4 w-4/6" />
      </div>
    </div>
  );
}
