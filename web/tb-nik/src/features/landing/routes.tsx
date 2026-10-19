import { lazy } from "react";
import type { RouteObject } from "react-router-dom";

const LandingPage = lazy(() => import("@/features/landing/LandingPage"));
const AboutPage = lazy(() => import("@/features/landing/pages/AboutPage"));
const DocsPage = lazy(() => import("@/features/landing/pages/DocsPage"));
const ContactPage = lazy(() => import("@/features/landing/pages/ContactPage"));

/** The public site at the root of /tb-nik (no guard: visitors and signed-in people both see it). Product is the default page. */
export const landingRoutes: RouteObject[] = [
  { path: "/", element: <LandingPage /> },
  { path: "/about", element: <AboutPage /> },
  { path: "/docs", element: <DocsPage /> },
  { path: "/contact", element: <ContactPage /> },
];
