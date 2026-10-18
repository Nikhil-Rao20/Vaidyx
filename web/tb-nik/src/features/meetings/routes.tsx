import { lazy } from "react";
import type { RouteObject } from "react-router-dom";

// Meetings: the list, join by code, the agenda / control view, the full-screen room screen, the remote member view.
// The room screen renders a fixed full-screen layer and adds the class "tbnik-fullscreen" to body, so it covers the
// shell without the shell having to know about it.
const MeetingsListPage = lazy(() => import("./MeetingsListPage"));
const MeetingAgendaPage = lazy(() => import("./MeetingAgendaPage"));
const MeetingRoomPage = lazy(() => import("./MeetingRoomPage"));
const MemberViewPage = lazy(() => import("./MemberViewPage"));
const JoinPage = lazy(() => import("./JoinPage"));

export const meetingRoutes: RouteObject[] = [
  { path: "/meetings", element: <MeetingsListPage /> },
  { path: "/meetings/join", element: <JoinPage /> },
  { path: "/meetings/:id", element: <MeetingAgendaPage /> },
  { path: "/meetings/:id/room", element: <MeetingRoomPage /> },
  { path: "/meetings/:id/member", element: <MemberViewPage /> },
];
