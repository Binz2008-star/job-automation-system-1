"use client";

import { fetchMe } from "@/lib/api";
import { clearAuth, type StoredUser } from "@/lib/auth";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

/**
 * Session-cookie auth hook.
 * Validates auth state by calling /api/v1/me (via /proxy).
 * For dev with NEXT_PUBLIC_USE_MOCK=true, sets a synthetic dev user.
 */
export function useAuth() {
  const [user, setUser] = useState<StoredUser | null>(null);
  const [ready, setReady] = useState(false);
  const router = useRouter();

  useEffect(() => {
    const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";
    if (USE_MOCK) {
      setUser({ user_id: "dev_user", name: "Dev User", email: "dev@rico.ai" });
      setReady(true);
      return;
    }

    fetchMe()
      .then((me) => {
        if (me.authenticated) {
          setUser({
            user_id: me.email,
            name: me.email.split("@")[0],
            email: me.email,
          });
        }
      })
      .catch(() => {
        /* not authenticated — leave user as null */
      })
      .finally(() => setReady(true));
  }, []);

  const logout = useCallback(async () => {
    await clearAuth();
    setUser(null);
    router.push("/login");
  }, [router]);

  return { user, ready, logout };
}
