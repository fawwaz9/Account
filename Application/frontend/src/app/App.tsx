import { BrowserRouter, Routes, Route } from "react-router-dom";
import Dashboard from "../pages/Dashboard";
import GradesPage from "../pages/GradesPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/grades" element={<GradesPage />} />
      </Routes>
    </BrowserRouter>
  );
}