/**
 * App-wide providers. Server state via TanStack Query keyed by resource +
 * organization_id (doc 08 §4); global session/auth via SessionProvider. Local
 * UI state stays local. On org switch, org-scoped caches are invalidated
 * (INV-FE-5) — wired when the org switcher lands.
 */
import { useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { SessionProvider } from "@/app/session/SessionContext";

export function AppProviders({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: 1,
            refetchOnWindowFocus: false,
            staleTime: 30_000,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <SessionProvider>{children}</SessionProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
