import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { ThemeProvider } from "./context/ThemeContext";
import { ToastProvider } from "./context/ToastContext";
import { useAuth } from "./hooks/useAuth";
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

function AuthGate({ children }: { children: React.ReactNode }) {
  const { apiKey, setApiKey } = useAuth();

  if (!apiKey) {
    return (
      <div className="flex items-center justify-center h-screen bg-base-200">
        <div className="rounded-2xl bg-base-100 border border-base-content/5 w-96 p-6">
          <h2 className="text-xl font-semibold mb-1">Recall Dashboard</h2>
          <p className="text-sm text-base-content/40 mb-4">
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
              className="w-full rounded-lg border border-base-content/10 bg-base-200 px-3 py-2 text-sm focus:border-primary/50 focus:outline-none"
            />
            <button
              type="submit"
              className="w-full mt-3 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-content hover:bg-primary/90 transition-colors"
            >
              Connect
            </button>
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
