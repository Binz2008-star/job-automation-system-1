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
  const useMock = process.env.NEXT_PUBLIC_USE_MOCK === "true";
  const [user, setUser] = useState<StoredUser | null>(() =>
    useMock ? { user_id: "dev_user", name: "Dev User", email: "dev@rico.ai" } : null
  );
  const [ready, setReady] = useState(useMock);
  const router = useRouter();

  useEffect(() => {
    if (useMock) {
      return;
    }

    let active = true;

    fetchMe()
      .then((me) => {
        if (!active) return;
        if (me.authenticated && me.email) {
          setUser({
            user_id: me.email,
            name: me.email.split("@")[0],
            email: me.email,
          });
        } else if (me.guest) {
          // Guest user - set user as null but mark as ready
          setUser(null);
        } else {
          router.push("/login");
        }
      })
      .catch(() => {
        // On error, treat as guest
        if (!active) return;
        setUser(null);
      })
      .finally(() => {
        if (active) {
          setReady(true);
        }
      });

    return () => {
      active = false;
    };
  }, [router, useMock]);

  const logout = useCallback(async () => {
    await clearAuth();
    setUser(null);
    router.push("/login");
  }, [router]);

  return { user, ready, logout };
}
