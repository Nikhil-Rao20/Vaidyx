// Profile changes (PUT /me/profile) and the saved filters that live inside the profile.
import { useCallback, useMemo } from "react";
import { api } from "@/lib/api";
import { EP } from "@/lib/endpoints";
import { useSession, type Me } from "@/lib/session";
import type { SavedFilter } from "@/lib/types";
import type { FilterQuery } from "@/lib/filters";
import { findSaved, removeSaved, upsertSaved } from "@/lib/filters";

export type ProfilePatch = Partial<Me["profile"]> & { display_name?: string };

export function useProfile() {
  const { me, setMe } = useSession();
  const update = useCallback(async (patch: ProfilePatch) => {
    // PUT /me/profile answers {profile, setup_needed}; an older answer may be the bare profile.
    const r = await api.put<{ profile?: Me["profile"] & { display_name?: string }; setup_needed?: boolean } & Partial<Me["profile"]>>(EP.profile, patch);
    const saved = (r && typeof r === "object" && r.profile && typeof r.profile === "object" ? r.profile : r) as Me["profile"] & { display_name?: string };
    if (me) {
      const profile = { ...me.profile, ...(saved && typeof saved === "object" ? saved : {}), ...patch } as Me["profile"] & { display_name?: string; profile?: unknown; setup_needed?: unknown; setup_complete?: unknown };
      const { display_name: dn, profile: _p, setup_needed: _s, setup_complete: _c, ...rest } = profile;
      void _p; void _s; void _c;
      setMe({ ...me, display_name: patch.display_name ?? dn ?? me.display_name, profile: rest, setup_needed: typeof r?.setup_needed === "boolean" ? r.setup_needed : false });
    }
    return saved;
  }, [me, setMe]);
  return { me, update };
}

export function useSavedFilters() {
  const { me, update } = useProfile();
  const list = useMemo<SavedFilter[]>(() => me?.profile?.saved_filters ?? [], [me]);
  const pin = useCallback((name: string, query: FilterQuery) => update({ saved_filters: upsertSaved(list, name, query) }), [list, update]);
  const unpin = useCallback((name: string) => update({ saved_filters: removeSaved(list, name) }), [list, update]);
  const pinned = useCallback((query: FilterQuery) => findSaved(list, query), [list]);
  return { list, pin, unpin, pinned };
}
