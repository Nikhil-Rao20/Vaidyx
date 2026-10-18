import { lazy } from "react";
import type { RouteObject } from "react-router-dom";
import { authShellRoutes } from "@/features/auth/routes";

const Home = lazy(() => import("@/features/home/Home"));
const NewCaseFile = lazy(() => import("@/features/newcase/NewCaseFile"));

export const homeRoutes: RouteObject[] = [
  { path: "/home", element: <Home /> },
  { path: "/cases/new", element: <NewCaseFile /> },
  ...authShellRoutes,
];
