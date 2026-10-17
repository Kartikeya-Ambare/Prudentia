import { QueryClient } from "@tanstack/react-query";

/** One client for the whole app, so code outside React (the assistant store) can refresh queries too. */
export const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false } },
});
