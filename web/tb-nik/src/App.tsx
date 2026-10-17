import { Suspense } from "react";
import { BrowserRouter, useRoutes, Navigate, type RouteObject } from "react-router-dom";
import { AppShell } from "@/app/AppShell";
import { SessionProvider } from "@/lib/session";
import { PublicOnly, RequireSession } from "@/app/guards";
import { PageSkeleton } from "@/app/PageSkeleton";
import { authRoutes } from "@/features/auth/routes";
import { homeRoutes } from "@/features/home/routes";
import { casefileRoutes } from "@/features/casefile/routes";
import { meetingRoutes } from "@/features/meetings/routes";
import { requestRoutes } from "@/features/requests/routes";
import { settingsRoutes } from "@/features/settings/routes";
import { adminRoutes } from "@/features/admin/routes";
import { NotFound } from "@/app/NotFound";

// Every feature folder exports its own RouteObject[] (src/features/<name>/routes.tsx).
// Pages inside the shell are children of the AppShell layout; public pages (sign in) sit outside it.
const routes: RouteObject[] = [
  { element: <PublicOnly />, children: authRoutes },
  {
    element: <RequireSession />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <Navigate to="/home" replace /> },
          ...homeRoutes,
          ...casefileRoutes,
          ...meetingRoutes,
          ...requestRoutes,
          ...settingsRoutes,
          ...adminRoutes,
        ],
      },
    ],
  },
  { path: "*", element: <NotFound /> },
];

function Routed() {
  return useRoutes(routes);
}

export default function App() {
  return (
    <BrowserRouter basename="/tb-nik">
      <SessionProvider>
        <Suspense fallback={<PageSkeleton />}>
          <Routed />
        </Suspense>
      </SessionProvider>
    </BrowserRouter>
  );
}
