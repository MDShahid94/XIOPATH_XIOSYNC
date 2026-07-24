import { AppProviders } from "./providers";
import { AppRouter } from "./router";

/**
 * Root composition. `AppProviders` already mounts the single `BrowserRouter`
 * (alongside the query client and session provider), so the router tree is
 * rendered directly as its child — a second nested router would break routing.
 */
export function App() {
  return (
    <AppProviders>
      <AppRouter />
    </AppProviders>
  );
}
