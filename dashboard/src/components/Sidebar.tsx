import { NavLink } from "react-router-dom";
import { useThemeContext } from "../context/ThemeContext";
import {
  House,
  ClipboardText,
  Clock,
  Lightning,
  FileText,
  Users,
  GearSix,
  CaretLeft,
  CaretRight,
  Sun,
  Moon,
  Warning,
  Heartbeat,
  FilePdf,
} from "@phosphor-icons/react";
import type { Icon } from "@phosphor-icons/react";

const links: { to: string; label: string; icon: Icon }[] = [
  { to: "/dashboard", label: "Dashboard", icon: House },
  { to: "/dashboard/memories", label: "Memories", icon: ClipboardText },
  { to: "/dashboard/sessions", label: "Sessions", icon: Clock },
  { to: "/dashboard/signals", label: "Signals", icon: Lightning },
  { to: "/dashboard/anti-patterns", label: "Anti-Patterns", icon: Warning },
  { to: "/dashboard/audit", label: "Audit Log", icon: FileText },
  { to: "/dashboard/users", label: "Users", icon: Users },
  { to: "/dashboard/health", label: "Health", icon: Heartbeat },
  { to: "/dashboard/documents", label: "Documents", icon: FilePdf },
  { to: "/dashboard/settings", label: "Settings", icon: GearSix },
];

interface Props {
  collapsed: boolean;
  onToggle: () => void;
  mobile?: boolean;
}

export default function Sidebar({ collapsed, onToggle, mobile }: Props) {
  const { theme, toggle: toggleTheme } = useThemeContext();

  return (
    <aside
      className={`bg-base-300 flex flex-col sidebar-transition ${
        mobile ? "w-56 h-full" : collapsed ? "w-16" : "w-56"
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between p-4">
        {!collapsed && (
          <img
            src="/dashboard/recall-logo.png"
            alt="Recall"
            className="h-auto w-[120px]"
          />
        )}
        <button
          className="rounded-lg p-1.5 hover:bg-base-100/50 transition-colors"
          onClick={onToggle}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <CaretRight size={16} /> : <CaretLeft size={16} />}
        </button>
      </div>

      {/* Nav links */}
      <nav className="flex-1 flex flex-col gap-0.5 px-2">
        {links.map((link) => {
          const IconComp = link.icon;
          return (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.to === "/dashboard"}
              className={({ isActive }) =>
                `flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? "bg-base-100/80 text-primary"
                    : "text-base-content/60 hover:bg-base-100/50 hover:text-base-content"
                } ${collapsed && !mobile ? "justify-center px-0" : ""}`
              }
              title={collapsed && !mobile ? link.label : undefined}
            >
              <IconComp size={18} className="shrink-0" />
              {(!collapsed || mobile) && <span>{link.label}</span>}
            </NavLink>
          );
        })}
      </nav>

      {/* Bottom: theme toggle */}
      <div className="p-2 border-t border-base-content/5">
        <button
          className={`flex items-center rounded-lg px-3 py-2 text-sm w-full transition-colors text-base-content/60 hover:bg-base-100/50 hover:text-base-content ${
            collapsed && !mobile ? "justify-center px-0" : "gap-2.5"
          }`}
          onClick={toggleTheme}
          title={
            collapsed && !mobile
              ? `Switch to ${theme === "recall-dark" ? "light" : "dark"} mode`
              : undefined
          }
        >
          {theme === "recall-dark" ? (
            <Sun size={18} className="shrink-0" />
          ) : (
            <Moon size={18} className="shrink-0" />
          )}
          {(!collapsed || mobile) && (
            <span>{theme === "recall-dark" ? "Light mode" : "Dark mode"}</span>
          )}
        </button>
      </div>
    </aside>
  );
}
