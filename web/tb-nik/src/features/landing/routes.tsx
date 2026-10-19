import { lazy } from "react";
import type { RouteObject } from "react-router-dom";

const LandingPage = lazy(() => import("@/features/landing/LandingPage"));

/** The public landing page at the root of /tb-nik (no guard: visitors and signed-in people both see it). */
export const landingRoutes: RouteObject[] = [
  { path: "/", element: <LandingPage /> },
];
