import { lazy } from "react";
import type { RouteObject } from "react-router-dom";

const SignIn = lazy(() => import("@/features/auth/SignIn"));
const FirstLogin = lazy(() => import("@/features/auth/FirstLogin"));
const Welcome = lazy(() => import("@/features/auth/Welcome"));

/** Public pages (no session): the sign-in page. */
export const authRoutes: RouteObject[] = [
  { path: "/sign-in", element: <SignIn /> },
];

/** Pages that need a session but run before the normal shell: the forced password change and the profile set-up.
 *  Included by homeRoutes (they render inside the shell in its bare mode). */
export const authShellRoutes: RouteObject[] = [
  { path: "/first-login", element: <FirstLogin /> },
  { path: "/welcome", element: <Welcome /> },
];
