import { lazy } from "react";
import type { RouteObject } from "react-router-dom";

const AdminSetup = lazy(() => import("@/features/admin/AdminSetup"));
const PeoplePage = lazy(() => import("@/features/admin/PeoplePage"));

/** /admin: the root admin's guided set-up. /people: department admins (and the root admin) manage a department's people. */
export const adminRoutes: RouteObject[] = [
  { path: "/admin", element: <AdminSetup /> },
  { path: "/people", element: <PeoplePage /> },
];
