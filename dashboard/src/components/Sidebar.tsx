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
import { cn } from "../lib/utils";

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
      className={cn(
        "flex flex-col sidebar-transition",
        "bg-white/60 dark:bg-zinc-900/60 backdrop-blur-2xl",
        "border-r border-zinc-200 dark:border-white/[0.06]",
        mobile ? "w-56 h-full" : collapsed ? "w-16" : "w-56",
      )}
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
          className="rounded-lg p-1.5 text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
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
                cn(
                  "flex items-center gap-2.5 rounded-xl px-3 py-2 text-sm transition-all duration-200",
                  isActive
                    ? "bg-violet-500/10 text-violet-600 dark:text-violet-400 font-medium border-l-2 border-violet-500"
                    : "text-zinc-500 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800/50 hover:text-zinc-900 dark:hover:text-zinc-100",
                  collapsed && !mobile && "justify-center px-0 border-l-0",
                )
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
      <div className="p-2 border-t border-zinc-200 dark:border-white/[0.06]">
        <button
          className={cn(
            "flex items-center rounded-xl px-3 py-2 text-sm w-full transition-colors",
            "text-zinc-500 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800/50 hover:text-zinc-900 dark:hover:text-zinc-100",
            collapsed && !mobile ? "justify-center px-0" : "gap-2.5",
          )}
          onClick={toggleTheme}
          title={
            collapsed && !mobile
              ? `Switch to ${theme === "dark" ? "light" : "dark"} mode`
              : undefined
          }
        >
          {theme === "dark" ? (
            <Sun size={18} className="shrink-0" />
          ) : (
            <Moon size={18} className="shrink-0" />
          )}
          {(!collapsed || mobile) && (
            <span>{theme === "dark" ? "Light mode" : "Dark mode"}</span>
          )}
        </button>
      </div>
    </aside>
  );
}
