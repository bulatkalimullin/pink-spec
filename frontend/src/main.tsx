import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "sonner";
import App from "./App.tsx";
import { I18nProvider } from "./i18n/I18nProvider";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <I18nProvider>
        <App />
        <Toaster position="top-right" richColors closeButton />
      </I18nProvider>
    </BrowserRouter>
  </React.StrictMode>
);
