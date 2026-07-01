import {
  Activity,
  LayoutGrid,
  MessageCircleQuestion,
  MoreHorizontal,
} from "lucide-react";
import { cn } from "@/lib/utils";

export type MobileNavTab = "timeline" | "panels" | "questions" | "more";

interface MobileBottomNavProps {
  active: MobileNavTab;
  onChange: (tab: MobileNavTab) => void;
  questionCount?: number;
}

const TABS: { id: MobileNavTab; label: string; icon: React.ReactNode }[] = [
  { id: "timeline", label: "Timeline", icon: <Activity className="h-4 w-4" /> },
  { id: "panels", label: "Panels", icon: <LayoutGrid className="h-4 w-4" /> },
  { id: "questions", label: "Questions", icon: <MessageCircleQuestion className="h-4 w-4" /> },
  { id: "more", label: "More", icon: <MoreHorizontal className="h-4 w-4" /> },
];

export default function MobileBottomNav({
  active,
  onChange,
  questionCount = 0,
}: MobileBottomNavProps) {
  return (
    <nav className="flex shrink-0 border-t border-border bg-card/95 backdrop-blur-sm pb-[env(safe-area-inset-bottom)] lg:hidden">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={cn(
            "relative flex flex-1 flex-col items-center gap-0.5 py-2 text-[10px] transition-colors",
            active === tab.id ? "text-primary" : "text-muted-foreground hover:text-foreground"
          )}
        >
          {tab.icon}
          <span>{tab.label}</span>
          {tab.id === "questions" && questionCount > 0 && (
            <span className="absolute right-1/4 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[9px] font-bold text-white">
              {questionCount > 99 ? "99+" : questionCount}
            </span>
          )}
        </button>
      ))}
    </nav>
  );
}
