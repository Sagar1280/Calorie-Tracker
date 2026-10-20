import { Component, type ErrorInfo, type ReactNode } from "react";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export default class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Unhandled application error", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="app">
          <main className="page">
            <section className="card state-card" role="alert">
              <span className="state-icon" aria-hidden="true">
                !
              </span>
              <h1>Something went wrong</h1>
              <p>
                The page hit an unexpected error. Your saved data is safe.
                Reload to continue.
              </p>
              <button
                type="button"
                className="primary-button"
                onClick={() => window.location.reload()}
              >
                Reload app
              </button>
            </section>
          </main>
        </div>
      );
    }
    return this.props.children;
  }
}
