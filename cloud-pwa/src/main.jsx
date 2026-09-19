import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import CustomerApp from "./CustomerApp.jsx";
import "./styles.css";

if ("serviceWorker" in navigator && import.meta.env.PROD) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => undefined);
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
    return <CustomerApp key={token} token={token} />;
  }
  return <App />;
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <RootRoute />
  </React.StrictMode>
);
