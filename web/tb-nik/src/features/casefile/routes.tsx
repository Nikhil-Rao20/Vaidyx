import { lazy } from "react";
import type { RouteObject } from "react-router-dom";

// The guided Case File (21 Oct 2026): /cases/:id opens on Overview; each section is an address: /cases/:id/overview, /question,
// /reports, /check, /pre-authorization, /summary. Older addresses keep working (/helpers, /published open the Summary; /team, /board
// open their panel; /ask opens the chat).
const CaseFilePage = lazy(() => import("./GuidedCaseFilePage"));

export const casefileRoutes: RouteObject[] = [
  { path: "/cases/:id", element: <CaseFilePage /> },
  { path: "/cases/:id/:view", element: <CaseFilePage /> },
];
