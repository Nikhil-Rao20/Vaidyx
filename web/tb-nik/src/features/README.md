# Feature folders

One folder per area. Each exports `routes.tsx` with a `RouteObject[]` named after the folder (authRoutes, homeRoutes, casefileRoutes, meetingRoutes, requestRoutes, settingsRoutes, adminRoutes); src/App.tsx composes them. Pages inside the shell render in the AppShell Outlet. Shared pieces: src/components/ui (shadcn), src/components/* (ours), src/lib/api.ts, src/lib/session.tsx, src/lib/appearance.ts, src/app/* (shell, guards, skeleton, not found). Do not edit App.tsx; add routes in your own routes.tsx.

Ask PubMed (`pubmed/`, 3 Nov 2026) has no routes.tsx of its own: its `/pubmed` page is a lazy route in homeRoutes; `PubMedAsk` is also used by the Case File Ask panel and the meeting side panel.
