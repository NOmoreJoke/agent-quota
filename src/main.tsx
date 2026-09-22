import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./ui/App";
import { FloatingQuota } from "./ui/FloatingQuota";
import "./ui/styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("root element missing");
const floating = new URLSearchParams(window.location.search).get("surface") === "floating";
document.documentElement.classList.toggle("floating-surface", floating);
createRoot(root).render(<StrictMode>{floating ? <FloatingQuota /> : <App />}</StrictMode>);
