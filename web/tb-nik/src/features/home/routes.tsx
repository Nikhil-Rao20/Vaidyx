import { lazy } from "react";
import { Navigate, type RouteObject } from "react-router-dom";
import { authShellRoutes } from "@/features/auth/routes";

const Home = lazy(() => import("@/features/home/Home"));
const NewCaseFile = lazy(() => import("@/features/newcase/NewCaseFile"));
// Ask PubMed on Home (docs/pubmed-ask/DESIGN.md section 8): general questions, each login's own history.
const PubMedPage = lazy(() => import("@/features/pubmed/PubMedPage"));

export const homeRoutes: RouteObject[] = [
  { path: "/cases", element: <Home /> },
  { path: "/home", element: <Navigate to="/cases" replace /> },  // old links and bookmarks
  { path: "/cases/new", element: <NewCaseFile /> },
  { path: "/pubmed", element: <PubMedPage /> },
  ...authShellRoutes,
];
