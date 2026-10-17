# Feature folders

One folder per area. Each exports `routes.tsx` with a `RouteObject[]` named after the folder (authRoutes, homeRoutes, casefileRoutes, meetingRoutes, requestRoutes, settingsRoutes, adminRoutes); src/App.tsx composes them. Pages inside the shell render in the AppShell Outlet. Shared pieces: src/components/ui (shadcn), src/components/* (ours), src/lib/api.ts, src/lib/session.tsx, src/lib/appearance.ts, src/app/* (shell, guards, skeleton, not found). Do not edit App.tsx; add routes in your own routes.tsx.
