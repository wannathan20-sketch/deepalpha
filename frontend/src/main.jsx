import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./styles.css";

class AppErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("DeepAlpha frontend crashed", error, errorInfo);
  }

  render() {
    if (this.state.error) {
      return (
        <main className="min-h-screen bg-slate-950 p-6 text-slate-100">
          <section className="mx-auto mt-12 max-w-2xl rounded-lg border border-red-400/30 bg-red-400/10 p-5">
            <h1 className="text-lg font-semibold text-red-100">前端渲染异常</h1>
            <p className="mt-2 text-sm leading-6 text-red-100/80">
              页面没有消失，只是某个组件渲染失败了。请刷新后重试，或把下面的错误信息发给开发者。
            </p>
            <pre className="mt-4 max-h-64 overflow-auto rounded-md border border-red-400/20 bg-slate-950 p-3 text-xs text-red-100">
              {this.state.error?.stack || this.state.error?.message || String(this.state.error)}
            </pre>
            <button
              className="mt-4 rounded-md bg-red-200 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-red-100"
              onClick={() => window.location.reload()}
              type="button"
            >
              刷新页面
            </button>
          </section>
        </main>
      );
    }

    return this.props.children;
  }
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <AppErrorBoundary>
      <App />
    </AppErrorBoundary>
  </React.StrictMode>,
);
