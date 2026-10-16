import { Component, type ReactNode } from "react";
import { Alert } from "./Feedback";

/** Keeps one failed section (for example a chart chunk) from blanking the page. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <Alert tone="error">
        This section failed to load. Reload the page to try again.
      </Alert>
    );
  }
}
