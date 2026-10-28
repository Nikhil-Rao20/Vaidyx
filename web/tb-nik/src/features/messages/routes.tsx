import { lazy } from "react";
import type { RouteObject } from "react-router-dom";

const MessagesPage = lazy(() => import("@/features/messages/MessagesPage"));

// /messages/new must come before /messages/:id (react-router ranks static segments first anyway).
export const messageRoutes: RouteObject[] = [
  { path: "/messages", element: <MessagesPage /> },
  { path: "/messages/new", element: <MessagesPage /> },
  { path: "/messages/:id", element: <MessagesPage /> },
];
