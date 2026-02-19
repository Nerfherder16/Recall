import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { ThemeProvider } from "./context/ThemeContext";
import { ToastProvider } from "./context/ToastContext";
import { useAuth } from "./hooks/useAuth";
import { Button } from "./components/common/Button";
import AuditPage from "./pages/AuditPage";
import DashboardPage from "./pages/DashboardPage";
import MemoriesPage from "./pages/MemoriesPage";
import SessionsPage from "./pages/SessionsPage";
import SettingsPage from "./pages/SettingsPage";
import SignalsPage from "./pages/SignalsPage";
import AntiPatternsPage from "./pages/AntiPatternsPage";
import UsersPage from "./pages/UsersPage";
import HealthPage from "./pages/HealthPage";
import DocumentsPage from "./pages/DocumentsPage";
import GraphPage from "./pages/GraphPage";

function AuthGate({ children }: { children: React.ReactNode }) {
  const { apiKey, setApiKey } = useAuth();

  if (!apiKey) {
    return (
      <div className="flex items-center justify-center h-screen bg-zinc-50 dark:bg-zinc-950">
        <div className="rounded-2xl bg-white/60 dark:bg-zinc-800/40 backdrop-blur-xl border border-zinc-200 dark:border-white/[0.06] w-96 p-6 shadow-2xl">
          <h2 className="font-display text-xl font-bold text-zinc-900 dark:text-zinc-50 mb-1">
            Recall Dashboard
          </h2>
          <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-4">
            Enter your API key to continue. Leave blank if auth is disabled.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const val = (e.target as HTMLFormElement).key.value;
              setApiKey(val || "none");
            }}
          >
            <input
              name="key"
              type="password"
              placeholder="API Key (or leave blank)"
              className="w-full rounded-xl border border-zinc-200 dark:border-white/[0.06] bg-zinc-100 dark:bg-zinc-900/80 px-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 focus:border-violet-500/50 focus:outline-none focus:ring-2 focus:ring-violet-500/20"
            />
            <Button type="submit" className="w-full mt-3">
              Connect
            </Button>
          </form>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}

export default function App() {
  return (
    <ThemeProvider>
      <ToastProvider>
        <BrowserRouter>
          <AuthGate>
            <Routes>
              <Route path="/dashboard" element={<Layout />}>
                <Route index element={<DashboardPage />} />
                <Route path="memories" element={<MemoriesPage />} />
                <Route path="sessions" element={<SessionsPage />} />
                <Route path="signals" element={<SignalsPage />} />
                <Route path="anti-patterns" element={<AntiPatternsPage />} />
                <Route path="audit" element={<AuditPage />} />
                <Route path="users" element={<UsersPage />} />
                <Route path="health" element={<HealthPage />} />
                <Route path="documents" element={<DocumentsPage />} />
                <Route path="graph" element={<GraphPage />} />
                <Route path="settings" element={<SettingsPage />} />
              </Route>
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </AuthGate>
        </BrowserRouter>
      </ToastProvider>
    </ThemeProvider>
  );
}
