import { Outlet } from "react-router-dom";

// Placeholder shell: replaced by the real shell (top bar, Dock, search, bell, profile) in the shell build.
export function AppShell() {
  return (
    <div className="min-h-dvh">
      <main className="max-w-7xl mx-auto px-4 py-4">
        <Outlet />
      </main>
    </div>
  );
}
