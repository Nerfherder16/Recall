import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { useAuth } from "./hooks/useAuth";
import AuditPage from "./pages/AuditPage";
import DashboardPage from "./pages/DashboardPage";
import MemoriesPage from "./pages/MemoriesPage";
import SessionsPage from "./pages/SessionsPage";
import SettingsPage from "./pages/SettingsPage";
import SignalsPage from "./pages/SignalsPage";

function AuthGate({ children }: { children: React.ReactNode }) {
  const { apiKey, setApiKey } = useAuth();

  if (!apiKey) {
    return (
      <div className="flex items-center justify-center h-screen bg-base-200">
        <div className="card bg-base-100 shadow-xl w-96">
          <div className="card-body">
            <h2 className="card-title">Recall Dashboard</h2>
            <p className="text-sm text-base-content/60">
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
                className="input input-bordered w-full mt-2"
              />
              <button type="submit" className="btn btn-primary w-full mt-3">
                Connect
              </button>
            </form>
          </div>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthGate>
        <Routes>
          <Route path="/dashboard" element={<Layout />}>
            <Route index element={<DashboardPage />} />
            <Route path="memories" element={<MemoriesPage />} />
            <Route path="sessions" element={<SessionsPage />} />
            <Route path="signals" element={<SignalsPage />} />
            <Route path="audit" element={<AuditPage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </AuthGate>
    </BrowserRouter>
  );
}
