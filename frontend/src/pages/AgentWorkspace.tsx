import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useSessionStore } from "@/stores/sessionStore";
import { useAgentWebSocket } from "@/hooks/useAgentWebSocket";
import { useSessionPolling } from "@/hooks/useSessionPolling";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import Header from "@/components/layout/Header";
import MobileBottomNav, { type MobileNavTab } from "@/components/layout/MobileBottomNav";
import PanelSheet from "@/components/layout/PanelSheet";
import SessionProgressBar from "@/components/workspace/SessionProgressBar";
import ActivityFeed from "@/components/workspace/ActivityFeed";
import AgentTimeline from "@/components/workspace/AgentTimeline";
import SupervisorCard from "@/components/workspace/SupervisorCard";
import AgentControlPanel from "@/components/workspace/AgentControlPanel";
import RecoveryPanel from "@/components/workspace/RecoveryPanel";
import SystemMetricsPanel from "@/components/metrics/SystemMetricsPanel";
import AssumptionsPanel from "@/components/observability/AssumptionsPanel";
import FallbacksPanel from "@/components/observability/FallbacksPanel";
import HitlPanel from "@/components/workspace/HitlPanel";
import TasksPanel from "@/components/workspace/TasksPanel";
import { getSession, exportSession } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  Activity,
  AlertTriangle,
  CheckSquare,
  Cpu,
  Eye,
  GitBranch,
  ChevronLeft,
  ChevronRight,
  Download,
  ExternalLink,
  Menu,
  MessageCircleQuestion,
} from "lucide-react";
import { toast } from "sonner";

type SidebarTab =
  | "activity"
  | "supervisor"
  | "tasks"
  | "questions"
  | "fallbacks"
  | "assumptions"
  | "metrics";

const SIDEBAR_TABS: { id: SidebarTab; label: string; icon: React.ReactNode }[] = [
  { id: "activity", label: "Activity", icon: <Activity className="h-3.5 w-3.5" /> },
  { id: "supervisor", label: "Supervisor", icon: <GitBranch className="h-3.5 w-3.5" /> },
  { id: "questions", label: "Questions", icon: <MessageCircleQuestion className="h-3.5 w-3.5" /> },
  { id: "tasks", label: "Tasks", icon: <CheckSquare className="h-3.5 w-3.5" /> },
  { id: "fallbacks", label: "Fallbacks", icon: <AlertTriangle className="h-3.5 w-3.5" /> },
  { id: "assumptions", label: "Assumptions", icon: <Eye className="h-3.5 w-3.5" /> },
  { id: "metrics", label: "System", icon: <Cpu className="h-3.5 w-3.5" /> },
];

const TAB_LABELS: Record<SidebarTab, string> = Object.fromEntries(
  SIDEBAR_TABS.map((t) => [t.id, t.label])
) as Record<SidebarTab, string>;

export default function AgentWorkspace() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const { setSessionId, sessionStatus, assumptions, fallbacks, isStuck, markRead, setPipeline } =
    useSessionStore();
  const [activeTab, setActiveTab] = useState<SidebarTab>("activity");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [questionCount, setQuestionCount] = useState(0);
  const [mobileNav, setMobileNav] = useState<MobileNavTab>("timeline");
  const [panelSheetOpen, setPanelSheetOpen] = useState(false);
  const [moreSheetOpen, setMoreSheetOpen] = useState(false);
  const [navDrawerOpen, setNavDrawerOpen] = useState(false);

  const isLg = useMediaQuery("(min-width: 1024px)");
  const isXl = useMediaQuery("(min-width: 1280px)");

  useAgentWebSocket(sessionId ?? null);
  useSessionPolling(sessionId ?? null);

  useEffect(() => {
    if (!sessionId) return;
    getSession(sessionId)
      .then((s) => {
        setSessionId(sessionId, s.spec_level, s.idea ?? "", s.status ?? "running");
        setQuestionCount((s.open_questions ?? []).length);
        const pl = s.pipeline as { steps?: { id: string; name: string }[]; reasoning?: string } | null;
        if (pl?.steps?.length) {
          setPipeline(pl.steps, pl.reasoning ?? "");
        }
        setLoading(false);
      })
      .catch(() => {
        toast.error("Session not found");
        navigate("/");
      });
  }, [sessionId, setSessionId, setPipeline, navigate]);

  useEffect(() => {
    if (sessionStatus === "waiting_user" && questionCount > 0) {
      setActiveTab("questions");
      if (!isLg) {
        setMobileNav("questions");
        setPanelSheetOpen(true);
      }
    }
  }, [sessionStatus, questionCount, isLg]);

  const handleExport = async () => {
    if (!sessionId) return;
    try {
      const blob = await exportSession(sessionId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `pink-spec-${sessionId.slice(0, 8)}.zip`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Export failed");
    }
  };

  const handleNotificationsClick = () => {
    markRead();
    setActiveTab("activity");
    if (!isLg) {
      setMobileNav("panels");
      setPanelSheetOpen(true);
    }
  };

  const selectTab = useCallback((tab: SidebarTab) => {
    setActiveTab(tab);
    setNavDrawerOpen(false);
    if (!isLg) setPanelSheetOpen(true);
  }, [isLg]);

  const renderPanelContent = () => {
    if (!sessionId) return null;
    switch (activeTab) {
      case "activity":
        return <ActivityFeed />;
      case "supervisor":
        return (
          <div className="flex flex-col h-full min-h-0 p-3 space-y-3 overflow-y-auto">
            <SupervisorCard />
            <AgentControlPanel sessionId={sessionId} />
          </div>
        );
      case "questions":
        return (
          <HitlPanel sessionId={sessionId} onCountChange={setQuestionCount} />
        );
      case "tasks":
        return <TasksPanel sessionId={sessionId} />;
      case "fallbacks":
        return <FallbacksPanel />;
      case "assumptions":
        return <AssumptionsPanel />;
      case "metrics":
        return <SystemMetricsPanel />;
      default:
        return null;
    }
  };

  const handleMobileNav = (tab: MobileNavTab) => {
    setMobileNav(tab);
    if (tab === "timeline") {
      setPanelSheetOpen(false);
      setMoreSheetOpen(false);
    } else if (tab === "panels") {
      setMoreSheetOpen(false);
      setPanelSheetOpen(true);
    } else if (tab === "questions") {
      setActiveTab("questions");
      setMoreSheetOpen(false);
      setPanelSheetOpen(true);
    } else if (tab === "more") {
      setPanelSheetOpen(false);
      setMoreSheetOpen(true);
    }
  };

  const tabBadge = (tab: SidebarTab) => {
    if (tab === "fallbacks" && fallbacks.length > 0) return fallbacks.length;
    if (tab === "assumptions" && assumptions.length > 0) return assumptions.length;
    if (tab === "questions" && questionCount > 0) return questionCount;
    return null;
  };

  const sidebarNav = (
    <>
      <div className="flex items-center justify-between px-2 py-2 border-b border-border">
        {!sidebarCollapsed && (
          <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
            Panels
          </span>
        )}
        <button
          onClick={() => setSidebarCollapsed((c) => !c)}
          className="rounded p-1 hover:bg-accent transition-colors ml-auto"
        >
          {sidebarCollapsed ? (
            <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
          ) : (
            <ChevronLeft className="h-3.5 w-3.5 text-muted-foreground" />
          )}
        </button>
      </div>

      <div className="flex flex-col gap-0.5 p-1 flex-1">
        {SIDEBAR_TABS.map((tab) => {
          const badge = tabBadge(tab.id);
          return (
            <button
              key={tab.id}
              onClick={() => selectTab(tab.id)}
              className={cn(
                "flex items-center gap-2 rounded px-2 py-1.5 text-xs transition-colors relative",
                activeTab === tab.id
                  ? "bg-primary/20 text-primary font-medium"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground"
              )}
            >
              <span className="flex-shrink-0">{tab.icon}</span>
              {!sidebarCollapsed && <span>{tab.label}</span>}
              {badge != null && (
                <span
                  className={cn(
                    "ml-auto rounded-full px-1 text-[9px] font-bold",
                    sidebarCollapsed ? "absolute -top-1 -right-1" : "",
                    tab.id === "fallbacks"
                      ? "bg-orange-800 text-orange-300"
                      : tab.id === "questions"
                      ? "bg-sky-800 text-sky-300"
                      : "bg-amber-800 text-amber-300"
                  )}
                >
                  {badge}
                </span>
              )}
              {tab.id === "supervisor" && isStuck && !sidebarCollapsed && (
                <span className="ml-auto rounded-full bg-red-800 px-1 text-[9px] font-bold text-red-300">
                  !
                </span>
              )}
            </button>
          );
        })}
      </div>

      {!sidebarCollapsed && sessionStatus === "completed" && (
        <div className="border-t border-border p-2 space-y-1">
          <button
            onClick={() => void handleExport()}
            className="flex w-full items-center gap-1.5 rounded border border-border px-2 py-1.5 text-xs text-muted-foreground hover:bg-accent transition-colors"
          >
            <Download className="h-3.5 w-3.5" />
            Download ZIP
          </button>
          <button
            onClick={() => navigate(`/artifacts/${sessionId}`)}
            className="flex w-full items-center gap-1.5 rounded border border-border px-2 py-1.5 text-xs text-muted-foreground hover:bg-accent transition-colors"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            View Artifacts
          </button>
        </div>
      )}
    </>
  );

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <p className="text-sm text-muted-foreground animate-pulse">Loading session…</p>
      </div>
    );
  }

  const criticalBanner =
    sessionStatus === "waiting_user" && questionCount > 0 ? (
      <div className="border-b border-sky-700/50 bg-sky-900/20 px-4 py-2 text-xs text-sky-200">
        Агент ждёт ваши ответы ({questionCount} вопросов). Pipeline не начнётся, пока вы не
        ответите на все —{" "}
        <button
          onClick={() => selectTab("questions")}
          className="underline hover:text-sky-100 font-medium"
        >
          перейти к вопросам
        </button>
      </div>
    ) : questionCount > 0 ? (
      <div className="border-b border-sky-700/50 bg-sky-900/10 px-4 py-2 text-xs text-sky-300">
        {questionCount} open question{questionCount > 1 ? "s" : ""} need your input —{" "}
        <button
          onClick={() => selectTab("questions")}
          className="underline hover:text-sky-200"
        >
          answer now
        </button>
      </div>
    ) : null;

  return (
    <div className="flex h-[100dvh] flex-col bg-background overflow-hidden">
      <Header sessionId={sessionId} onNotificationsClick={handleNotificationsClick} />

      <SessionProgressBar />

      {/* Mobile hamburger for panel tabs on md */}
      {!isLg && (
        <div className="flex items-center gap-2 border-b border-border bg-card/50 px-3 py-1.5 lg:hidden">
          <button
            onClick={() => setNavDrawerOpen(true)}
            className="rounded p-1.5 hover:bg-accent"
            aria-label="Open panels menu"
          >
            <Menu className="h-4 w-4 text-muted-foreground" />
          </button>
          <span className="text-xs text-muted-foreground">{TAB_LABELS[activeTab]}</span>
        </div>
      )}

      {criticalBanner}

      <div className="flex flex-1 overflow-hidden min-h-0">
        {/* Desktop left nav */}
        {isLg && (
          <div
            className={cn(
              "hidden lg:flex flex-col border-r border-border bg-card transition-all duration-200",
              sidebarCollapsed ? "w-10" : "w-44"
            )}
          >
            {sidebarNav}
          </div>
        )}

        {/* Desktop / tablet side panel */}
        {isLg && (
          <div className="hidden lg:flex flex-col w-80 flex-shrink-0 border-r border-border bg-card/50 h-full min-h-0 overflow-hidden">
            {renderPanelContent()}
          </div>
        )}

        {/* Main timeline */}
        <div
          className={cn(
            "flex flex-1 flex-col overflow-hidden min-w-0",
            !isLg && mobileNav !== "timeline" && "hidden lg:flex"
          )}
        >
          {isStuck && sessionId && (
            <div className="border-b border-amber-700/50 bg-amber-900/10 px-4 py-2">
              <RecoveryPanel sessionId={sessionId} />
            </div>
          )}
          <div className="flex-1 overflow-y-auto border-r border-border bg-card/30 min-h-0">
            <AgentTimeline />
          </div>
        </div>

        {/* Right rail — xl+ only */}
        {isXl && (
          <div className="w-56 flex-shrink-0 border-l border-border overflow-y-auto hidden xl:block">
            <SystemMetricsPanel />
            <div className="border-t border-border mt-2 pt-2 px-3 pb-2 space-y-2">
              <SupervisorCard />
              <AgentControlPanel sessionId={sessionId ?? ""} />
            </div>
          </div>
        )}
      </div>

      <MobileBottomNav
        active={mobileNav}
        onChange={handleMobileNav}
        questionCount={questionCount}
      />

      {/* Mobile panel sheet */}
      <PanelSheet
        open={panelSheetOpen && !isLg}
        onOpenChange={setPanelSheetOpen}
        title={TAB_LABELS[activeTab]}
      >
        {renderPanelContent()}
      </PanelSheet>

      {/* Mobile more sheet */}
      <PanelSheet open={moreSheetOpen && !isLg} onOpenChange={setMoreSheetOpen} title="More">
        <div className="p-3 space-y-2">
          {SIDEBAR_TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => {
                selectTab(tab.id);
                setMoreSheetOpen(false);
                setMobileNav("panels");
              }}
              className="flex w-full items-center gap-2 rounded px-3 py-2 text-sm text-muted-foreground hover:bg-accent"
            >
              {tab.icon}
              {tab.label}
              {tabBadge(tab.id) != null && (
                <span className="ml-auto rounded-full bg-primary/20 px-1.5 text-[10px] font-bold text-primary">
                  {tabBadge(tab.id)}
                </span>
              )}
            </button>
          ))}
          {sessionStatus === "completed" && (
            <>
              <hr className="border-border" />
              <button
                onClick={() => void handleExport()}
                className="flex w-full items-center gap-2 rounded px-3 py-2 text-sm text-muted-foreground hover:bg-accent"
              >
                <Download className="h-4 w-4" />
                Download ZIP
              </button>
              <button
                onClick={() => navigate(`/artifacts/${sessionId}`)}
                className="flex w-full items-center gap-2 rounded px-3 py-2 text-sm text-muted-foreground hover:bg-accent"
              >
                <ExternalLink className="h-4 w-4" />
                View Artifacts
              </button>
            </>
          )}
        </div>
      </PanelSheet>

      {/* Tablet nav drawer */}
      <PanelSheet
        open={navDrawerOpen && !isLg}
        onOpenChange={setNavDrawerOpen}
        title="Panels"
        className="md:max-w-xs"
      >
        <div className="flex flex-col p-1">{sidebarNav}</div>
      </PanelSheet>
    </div>
  );
}
