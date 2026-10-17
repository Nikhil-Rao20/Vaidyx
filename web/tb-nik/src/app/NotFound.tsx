import { Link } from "react-router-dom";

export function NotFound() {
  return (
    <main className="min-h-dvh grid place-items-center p-4">
      <div className="surface p-8 max-w-md w-full text-center">
        <p className="text-6xl font-bold text-muted-foreground" aria-hidden>404</p>
        <h1 className="mt-2">This page does not exist</h1>
        <p className="mt-2 text-muted-foreground">The link may be old, or the page moved.</p>
        <Link to="/home" className="inline-flex mt-6 rounded-md bg-primary text-primary-foreground px-4 py-2 font-medium hover:bg-primary-hover">Go to Home</Link>
      </div>
    </main>
  );
}
