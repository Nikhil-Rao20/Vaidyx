import { lazy } from "react";
import type { RouteObject } from "react-router-dom";

// The Vaidyx console (/platform) and the Hospital console (/hospital), docs/admin-console/DESIGN.md section 4. Each tab is its own
// address; the console layout keeps its header and tabs while a tab loads.
const PlatformConsole = lazy(() => import("@/features/consoles/platform/PlatformConsole"));
const PlatformOverview = lazy(() => import("@/features/consoles/platform/PlatformOverview"));
const HospitalsTab = lazy(() => import("@/features/consoles/platform/HospitalsTab"));
const LoginsTab = lazy(() => import("@/features/consoles/platform/LoginsTab"));
const PlatformActivity = lazy(() => import("@/features/consoles/platform/PlatformActivity"));
const HospitalDetail = lazy(() => import("@/features/consoles/platform/HospitalDetail"));

const HospitalConsole = lazy(() => import("@/features/consoles/hospital/HospitalConsole"));
const HospitalOverview = lazy(() => import("@/features/consoles/hospital/HospitalOverview"));
const HospitalPeople = lazy(() => import("@/features/consoles/hospital/HospitalPeople"));
const HospitalDepartments = lazy(() => import("@/features/consoles/hospital/HospitalDepartments"));
const HospitalSetup = lazy(() => import("@/features/consoles/hospital/HospitalSetup"));
const HospitalSystem = lazy(() => import("@/features/consoles/hospital/HospitalSystem"));
const HospitalActivity = lazy(() => import("@/features/consoles/hospital/HospitalActivity"));

export const consoleRoutes: RouteObject[] = [
  {
    path: "/platform",
    element: <PlatformConsole />,
    children: [
      { index: true, element: <PlatformOverview /> },
      { path: "hospitals", element: <HospitalsTab /> },
      { path: "logins", element: <LoginsTab /> },
      { path: "activity", element: <PlatformActivity /> },
    ],
  },
  { path: "/platform/hospitals/:id", element: <HospitalDetail /> },
  {
    path: "/hospital",
    element: <HospitalConsole />,
    children: [
      { index: true, element: <HospitalOverview /> },
      { path: "people", element: <HospitalPeople /> },
      { path: "departments", element: <HospitalDepartments /> },
      { path: "setup", element: <HospitalSetup /> },
      { path: "system", element: <HospitalSystem /> },
      { path: "activity", element: <HospitalActivity /> },
    ],
  },
];
