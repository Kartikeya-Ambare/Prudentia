import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "./index.css";
import "./lib/theme";
import { App } from "./App";
import { ErrorBoundary } from "./components/ui/ErrorBoundary";

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false } },
});

/**
 * Wait (briefly) for the two web fonts before the first render. Headings and text re-wrap when a font swaps in,
 * and with the start screen centred, that moves every element on it (a large layout shift). If the fonts are
 * slow or blocked, the page still renders after the timeout.
 */
async function fontsReady(maxMs: number) {
  if (!("fonts" in document)) return;
  const load = Promise.all([
    document.fonts.load('600 44px "Space Grotesk Variable"', "What would you like to invest?"),
    document.fonts.load('600 16px "Space Grotesk Variable"', "Asset Allocation Recommendation"),
    document.fonts.load('400 16px "Manrope Variable"', "Share the amount, how long and how much risk"),
    document.fonts.load('600 16px "Manrope Variable"', "Invested Return Volatility 0123456789"),
  ]).catch(() => undefined);
  await Promise.race([load, new Promise((r) => setTimeout(r, maxMs))]);
}

fontsReady(1500).finally(() => {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <ErrorBoundary>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </ErrorBoundary>
      </QueryClientProvider>
    </StrictMode>,
  );
});
