import { ErrorPage } from "@/app/ErrorPage";

export function NotFound() {
  return <ErrorPage code={404} />;
}
