import { lazy } from "react";
import type { RouteObject } from "react-router-dom";

const RequestsPage = lazy(() => import("@/features/requests/RequestsPage"));

export const requestRoutes: RouteObject[] = [
  { path: "/requests", element: <RequestsPage /> },
];
