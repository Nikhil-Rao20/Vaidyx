/** Where the website lives in the address bar. On the internal development server the main Vaidyx app owns "/", so the website
 *  is opened under /tb-nik; on the public address (every user: doctors, coordinator, admins) it is at the root, with no prefix.
 *  Worked out once from the address the page was opened with. */
export const BASE: string =
  typeof window !== "undefined" && (window.location.pathname === "/tb-nik" || window.location.pathname.startsWith("/tb-nik/"))
    ? "/tb-nik"
    : "";
