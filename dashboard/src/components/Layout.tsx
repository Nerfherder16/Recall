import { useState, useEffect, useCallback } from "react";
import { Outlet } from "react-router-dom";
import { List as ListIcon } from "@phosphor-icons/react";
import Sidebar from "./Sidebar";
import { useLocalStorage } from "../hooks/useLocalStorage";

export default function Layout() {
  const [collapsed, setCollapsed] = useLocalStorage(
    "recall_sidebar_collapsed",
    false,
  );
  const [mobileOpen, setMobileOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);

  // Track screen size
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 767px)");
    setIsMobile(mq.matches);
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  // Close mobile sidebar on route change
  const closeMobile = useCallback(() => setMobileOpen(false), []);

  return (
    <div className="flex h-screen bg-base-200">
      {/* Desktop sidebar */}
      {!isMobile && (
        <Sidebar
          collapsed={collapsed}
          onToggle={() => setCollapsed(!collapsed)}
        />
      )}

      {/* Mobile overlay */}
      {isMobile && mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 sidebar-overlay"
          onClick={closeMobile}
        >
          <div onClick={(e) => e.stopPropagation()}>
            <Sidebar collapsed={false} onToggle={closeMobile} mobile />
          </div>
        </div>
      )}

      {/* Main content */}
      <main className="flex-1 overflow-y-auto">
        {/* Mobile header */}
        {isMobile && (
          <div className="sticky top-0 z-30 bg-base-300 px-4 py-2 flex items-center gap-3 border-b border-base-content/5">
            <button
              className="rounded-lg p-1.5 hover:bg-base-100/50 transition-colors"
              onClick={() => setMobileOpen(true)}
            >
              <ListIcon size={20} weight="bold" />
            </button>
            <img
              src="/dashboard/recall-logo.png"
              alt="Recall"
              className="h-auto w-[120px]"
            />
          </div>
        )}
        <div className="p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
