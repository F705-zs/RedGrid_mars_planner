import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { createRouter } from "@tanstack/react-router";
import { toast } from "sonner";

import { ApiError } from "./api/client";
import { routeTree } from "./routeTree.gen";

// API errors: the message is shown in a toast; the code is used in component logic.
function notify(error: unknown, meta?: Record<string, unknown>) {
  if (typeof window === "undefined") return;
  const silent = meta?.["silentCodes"];
  if (error instanceof ApiError && Array.isArray(silent) && silent.includes(error.code)) return;
  const message = error instanceof Error ? error.message : "Something went wrong.";
  toast.error(message, { id: message });
}

export const getRouter = () => {
  // One client per request: a module-level QueryClient leaks cached data between SSR requests.
  const queryClient = new QueryClient({
    queryCache: new QueryCache({ onError: (e, q) => notify(e, q.meta) }),
    mutationCache: new MutationCache({ onError: (e, _v, _c, m) => notify(e, m.meta) }),
    defaultOptions: {
      queries: {
        retry: (count, error) =>
          !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 2,
        refetchOnWindowFocus: false,
      },
    },
  });

  const router = createRouter({
    routeTree,
    context: { queryClient },
    scrollRestoration: true,
    // Lets Query own freshness; set caching defaults on the QueryClient, not the router.
    defaultPreloadStaleTime: 0,
  });

  return router;
};
