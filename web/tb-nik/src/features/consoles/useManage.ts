// "Manage inside this hospital" and "Back to Vaidyx console": the Vaidyx admin chooses (or leaves) the hospital it works inside.
// The choice is kept for this tab (lib/acting.ts), every cached answer is dropped, /me reloads, and the page moves on.
import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { notify } from "@/components/Toasts";
import { useSession } from "@/lib/session";

export function useManageHospital() {
  const { setActingHospital } = useSession();
  const navigate = useNavigate();
  const manage = useCallback(async (h: { id: string; name: string }, to = "/hospital") => {
    await setActingHospital({ id: h.id, name: h.name });
    notify.info(`Managing ${h.name}`, "As Vaidyx admin. Counts and people only; no patient data.");
    navigate(to);
  }, [setActingHospital, navigate]);
  const leave = useCallback(async () => {
    await setActingHospital(null);
    navigate("/platform");
  }, [setActingHospital, navigate]);
  return { manage, leave };
}
