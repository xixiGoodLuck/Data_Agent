import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { ConversationsPage } from "./pages/ConversationsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DatasetsPage } from "./pages/DatasetsPage";
import { EvalsPage } from "./pages/EvalsPage";
import { LogsPage } from "./pages/LogsPage";
import { QueryPage } from "./pages/QueryPage";
import { SettingsPage } from "./pages/SettingsPage";

export default function App() {
  return <Routes><Route element={<Layout />}><Route index element={<DashboardPage />} /><Route path="ask" element={<QueryPage />} /><Route path="datasets" element={<DatasetsPage />} /><Route path="conversations" element={<ConversationsPage />} /><Route path="logs" element={<LogsPage />} /><Route path="approvals" element={<ApprovalsPage />} /><Route path="evals" element={<EvalsPage />} /><Route path="settings" element={<SettingsPage />} /><Route path="*" element={<Navigate to="/" replace />} /></Route></Routes>;
}
