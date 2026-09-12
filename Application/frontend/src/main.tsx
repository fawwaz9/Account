import React from "react";
import ReactDOM from "react-dom/client";
import App from "./app/App";
import "./styles/globals.css";
import "./styles/login.css";
import "./styles/grades/courseDetail.css";
import "./styles/grades/grades.css";
// Not only the calendar's any more: .calRow, .calField, .calInput and .calButton
// are the shared form primitives, used by the grades, budget and task dialogs
// too. Loaded here so a page that renders one of those forms does not have to
// know which stylesheet happens to define them.
import "./styles/calendar.css";


ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);