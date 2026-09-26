import React, { lazy, Suspense, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./styles.css";

const CustomerApp = lazy(() => import("./CustomerApp.jsx"));

if ("serviceWorker" in navigator && import.meta.env.PROD) {
  window.addEventListener("load", () => {
    const hadController = Boolean(navigator.serviceWorker.controller);
    const announceUpdate = () => window.dispatchEvent(new CustomEvent("cloudpdv:update-available"));
    navigator.serviceWorker.register("/sw.js").then((registration) => {
      if (registration.waiting && hadController) announceUpdate();
      registration.addEventListener("updatefound", () => {
        const worker = registration.installing;
        worker?.addEventListener("statechange", () => {
          if (worker.state === "installed" && navigator.serviceWorker.controller) announceUpdate();
        });
      });
    }).catch(() => undefined);
  });
}

function RootRoute() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const changed = () => setHash(window.location.hash);
    window.addEventListener('hashchange', changed);
    return () => window.removeEventListener('hashchange', changed);
  }, []);
  if (hash.startsWith('#/comanda/')) {
    const token = hash.slice('#/comanda/'.length);
    return <Suspense fallback={<main className="customer-shell"><section className="panel">Abrindo sua comanda…</section></main>}><CustomerApp key={token} token={token} /></Suspense>;
  }
  return <App />;
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <RootRoute />
  </React.StrictMode>
);
