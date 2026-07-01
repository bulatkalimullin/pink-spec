import { Routes, Route, Navigate } from "react-router-dom";
import Home from "./pages/Home";
import RulesEditor from "./pages/RulesEditor";
import AgentWorkspace from "./pages/AgentWorkspace";
import ArtifactsViewer from "./pages/ArtifactsViewer";
import Settings from "./pages/Settings";
import Statistics from "./pages/Statistics";
import ProjectsAdmin from "./pages/ProjectsAdmin";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/rules" element={<RulesEditor />} />
      <Route path="/workspace/:sessionId" element={<AgentWorkspace />} />
      <Route path="/artifacts/:sessionId" element={<ArtifactsViewer />} />
      <Route path="/settings" element={<Settings />} />
      <Route path="/statistics" element={<Statistics />} />
      <Route path="/projects" element={<ProjectsAdmin />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
