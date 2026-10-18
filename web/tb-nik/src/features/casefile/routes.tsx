import { lazy } from "react";
import type { RouteObject } from "react-router-dom";

// The Case File page and its sub-views. Sub-views are query-free paths that open the matching side panel:
// /cases/:id, /cases/:id/helpers, /cases/:id/team, /cases/:id/board, /cases/:id/published, /cases/:id/reports.
const CaseFilePage = lazy(() => import("./CaseFilePage"));

export const casefileRoutes: RouteObject[] = [
  { path: "/cases/:id", element: <CaseFilePage /> },
  { path: "/cases/:id/:view", element: <CaseFilePage /> },
];
