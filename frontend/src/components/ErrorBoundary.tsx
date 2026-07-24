/**
 * Per-feature error boundary (doc 08 §5, INV-FE-6). Scoped per route so a
 * render failure in one area never white-screens the app, and offers recovery.
 */
import { Component, type ErrorInfo, type ReactNode } from "react";
import { toMessage } from "@/lib/problem";

interface Props {
  /** Human label of the area this boundary guards, for the recovery message. */
  area: string;
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    // eslint-disable-next-line no-console
    console.error(`[error-boundary:${this.props.area}]`, error, info);
  }

  private readonly handleRetry = (): void => {
    this.setState({ error: null });
  };

  override render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div role="alert" className="error-boundary">
        <h2>Something went wrong in {this.props.area}.</h2>
        <p>{toMessage(error)}</p>
        <button type="button" onClick={this.handleRetry}>
          Try again
        </button>
      </div>
    );
  }
}
