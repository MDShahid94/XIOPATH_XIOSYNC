import { useContext } from "react";
import { SessionContext, type SessionContextValue } from "./SessionContext";
import type { Authority } from "@/lib/authority";

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error("useSession must be used within a <SessionProvider>.");
  }
  return context;
}

/** The current authority axes, or `null` when anonymous (doc 05 §1.1). */
export function useAuthority(): Authority | null {
  const { session } = useSession();
  if (!session) return null;
  return {
    platformRole: session.platformRole,
    membershipRole: session.membershipRole,
  };
}
