import { BarChart3, Bell, FolderKanban, Settings, Zap } from "lucide-react";
import { Link } from "react-router-dom";
import LanguageSelector from "@/components/LanguageSelector";
import { useI18n } from "@/i18n/I18nProvider";
import { cn } from "@/lib/utils";
import { useSessionStore } from "@/stores/sessionStore";

const WS_STATUS_COLORS: Record<string, string> = {
  connected: "bg-emerald-400",
  connecting: "bg-yellow-400 animate-pulse",
  reconnecting: "bg-orange-400 animate-pulse",
  disconnected: "bg-zinc-500",
  error: "bg-red-400",
};

const SPEC_LEVEL_COLORS: Record<string, string> = {
  L1: "text-sky-300",
  L2: "text-emerald-300",
  L3: "text-violet-300",
  L4: "text-pink-300",
};

const STATUS_COLORS: Record<string, string> = {
  running: "text-emerald-400",
  stuck: "text-amber-400",
  failed: "text-red-400",
  completed: "text-pink-400",
  completed_partial: "text-orange-400",
  degraded: "text-orange-400",
  paused: "text-sky-400",
  pending: "text-zinc-400",
};

const STATUS_DOT_COLORS: Record<string, string> = {
  running: "bg-emerald-400",
  stuck: "bg-amber-400",
  failed: "bg-red-400",
  completed: "bg-pink-400",
  completed_partial: "bg-orange-400",
  degraded: "bg-orange-400",
  paused: "bg-sky-400",
  pending: "bg-zinc-400",
};

interface HeaderProps {
  sessionId?: string;
  onNotificationsClick?: () => void;
}

export default function Header({ sessionId, onNotificationsClick }: HeaderProps) {
  const { wsStatus, specLevel, sessionStatus, unreadCount } = useSessionStore();
  const { t } = useI18n();

  return (
    <header className="sticky top-0 z-40 flex h-12 min-w-0 items-center gap-2 border-b border-border bg-card/80 px-3 backdrop-blur-sm sm:gap-4 sm:px-4">
      <Link
        to="/"
        className="flex shrink-0 items-center gap-2 font-semibold text-primary hover:opacity-80"
      >
        <Zap className="h-4 w-4" />
        <span className="hidden text-sm sm:inline">Pink Spec</span>
      </Link>

      <span className="hidden text-border sm:inline">|</span>

      {sessionId && (
        <div className="flex min-w-0 items-center gap-1.5 sm:gap-2">
          <span
            className="truncate font-mono text-xs text-muted-foreground"
            title={sessionId}
          >
            {sessionId.slice(0, 8)}
          </span>
          <span
            className={cn(
              "shrink-0 text-xs font-semibold",
              SPEC_LEVEL_COLORS[specLevel] ?? "text-zinc-300"
            )}
          >
            {specLevel}
          </span>
          <span
            className={cn(
              "hidden shrink-0 text-xs font-medium capitalize sm:inline",
              STATUS_COLORS[sessionStatus] ?? "text-zinc-400"
            )}
          >
            ● {sessionStatus}
          </span>
          <span
            className={cn(
              "h-2 w-2 shrink-0 rounded-full sm:hidden",
              STATUS_DOT_COLORS[sessionStatus] ?? "bg-zinc-400"
            )}
            title={sessionStatus}
          />
        </div>
      )}

      <div className="flex-1 min-w-0" />

      <div className="flex shrink-0 items-center gap-1.5">
        <span
          className={cn("h-2 w-2 rounded-full", WS_STATUS_COLORS[wsStatus] ?? "bg-zinc-500")}
        />
        <span className="hidden text-xs text-muted-foreground capitalize sm:block">
          {wsStatus}
        </span>
      </div>

      <button
        onClick={onNotificationsClick}
        className="relative shrink-0 rounded-md p-1.5 hover:bg-accent transition-colors"
      >
        <Bell className="h-4 w-4 text-muted-foreground" />
        {unreadCount > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-destructive text-[9px] font-bold text-white">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      <Link
        to="/projects"
        className="shrink-0 rounded-md p-1.5 hover:bg-accent transition-colors"
        title={t.nav.projects}
      >
        <FolderKanban className="h-4 w-4 text-muted-foreground" />
      </Link>

      <Link
        to="/statistics"
        className="shrink-0 rounded-md p-1.5 hover:bg-accent transition-colors"
        title={t.nav.statistics}
      >
        <BarChart3 className="h-4 w-4 text-muted-foreground" />
      </Link>

      <LanguageSelector compact className="hidden sm:block" />

      <Link
        to="/settings"
        className="shrink-0 rounded-md p-1.5 hover:bg-accent transition-colors"
        title={t.nav.settings}
      >
        <Settings className="h-4 w-4 text-muted-foreground" />
      </Link>
    </header>
  );
}
