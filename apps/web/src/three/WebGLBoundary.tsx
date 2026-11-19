import { Component, type ReactNode } from "react";

/**
 * Catches a failure to create the WebGL context (hardware acceleration off, a GPU-less
 * VM, a blocked driver) so it degrades to a message inside the 3D panel instead of
 * unmounting the whole app. Everything outside the 3D view keeps working.
 */
export class WebGLBoundary extends Component<{ children: ReactNode; testId?: string }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error) {
    console.warn("3D view disabled:", error.message);
  }

  render() {
    if (!this.state.error) return this.props.children;
    const webgl = /webgl/i.test(this.state.error.message);
    return (
      <div data-testid={this.props.testId} role="note" className="flex h-full w-full items-center justify-center p-8 text-center">
        <div className="max-w-md text-sm leading-6 text-ink-2">
          <p className="t-head mb-2 text-ink">3D view unavailable</p>
          <p>
            {webgl
              ? "Your browser could not create a WebGL context, for example because hardware acceleration is turned off."
              : `The 3D view failed: ${this.state.error.message}`}{" "}
            The rest of this page still works.
          </p>
        </div>
      </div>
    );
  }
}
