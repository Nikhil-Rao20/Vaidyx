import { lazy } from "react";
import type { RouteObject } from "react-router-dom";

const SettingsPage = lazy(() => import("@/features/settings/SettingsPage"));
const ActivityPage = lazy(() => import("@/features/settings/ActivityPage"));

export const settingsRoutes: RouteObject[] = [
  { path: "/settings", element: <SettingsPage /> },
  { path: "/activity", element: <ActivityPage /> },
];
