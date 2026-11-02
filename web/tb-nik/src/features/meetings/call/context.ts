// The call context: the shell provides it (CallShell.tsx), the stage, the strip and every panel read it with useCall().
import { createContext, useContext } from "react";
import type { CallCtx } from "./types";

export const CallContext = createContext<CallCtx | null>(null);

export function useCall(): CallCtx {
  const c = useContext(CallContext);
  if (!c) throw new Error("useCall() must be used inside CallShell");
  return c;
}
