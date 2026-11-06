import { StrictMode, Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter, Route, Routes } from "react-router-dom";
import "@fontsource-variable/newsreader/opsz.css";
import "@fontsource-variable/newsreader/opsz-italic.css";
import "@fontsource-variable/geist/wght.css";
import "@fontsource-variable/geist-mono/wght.css";
import "./index.css";
import "./lib/theme"; // keeps <html data-theme> in sync with the stored preference / OS setting
import { Layout } from "./components/Layout";
import { Loading } from "./components/ui";
import Overview from "./pages/Overview";

const Explorer = lazy(() => import("./pages/Explorer"));
const Simulator = lazy(() => import("./pages/Simulator"));
const VirtualFly = lazy(() => import("./pages/VirtualFly"));
const Experiments = lazy(() => import("./pages/Experiments"));
const Datasets = lazy(() => import("./pages/Datasets"));
const Docs = lazy(() => import("./pages/Docs"));

const page = (el: React.ReactNode) => <Suspense fallback={<div className="p-8" aria-live="polite"><Loading /></div>}>{el}</Suspense>;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {/* HashRouter: works on GitHub Pages and behind the API's static file server alike */}
    <HashRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Overview />} />
          <Route path="explorer" element={page(<Explorer />)} />
          <Route path="simulator" element={page(<Simulator />)} />
          <Route path="fly" element={page(<VirtualFly />)} />
          <Route path="experiments" element={page(<Experiments />)} />
          <Route path="datasets" element={page(<Datasets />)} />
          <Route path="docs" element={page(<Docs />)} />
        </Route>
      </Routes>
    </HashRouter>
  </StrictMode>,
);
