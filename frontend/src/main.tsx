import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import "./index.css";
import Layout from "./components/Layout";
import Today from "./pages/Today";
import Inbox from "./pages/Inbox";
import Jobs from "./pages/Jobs";
import Money from "./pages/Money";
import Parts from "./pages/Parts";
import Approvals from "./pages/Approvals";
import Report from "./pages/Report";
import Outbox from "./pages/Outbox";
import PublicChat from "./pages/PublicChat";

const router = createBrowserRouter([
  { path: "/chat", element: <PublicChat /> },
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <Today /> },
      { path: "inbox", element: <Inbox /> },
      { path: "jobs", element: <Jobs /> },
      { path: "money", element: <Money /> },
      { path: "parts", element: <Parts /> },
      { path: "approvals", element: <Approvals /> },
      { path: "report", element: <Report /> },
      { path: "outbox", element: <Outbox /> },
    ],
  },
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>,
);
