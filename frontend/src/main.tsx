import React from "react";
import { createRoot } from "react-dom/client";
import { VisitorApp } from "./visitor/VisitorApp";
import "./style.css";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <VisitorApp />
  </React.StrictMode>,
);
