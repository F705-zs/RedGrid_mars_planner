import {
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  CircleSlash,
  Cpu,
  FlaskConical,
  GitBranch,
  History,
  Lock,
  PencilLine,
  Radio,
  ShieldAlert,
  ShieldCheck,
  XCircle,
  type LucideIcon,
} from "lucide-react";

import { DATA_STATE_HINT, DATA_STATE_LABEL, RISK_LABEL, STATUS_LABEL } from "@/lib/labels";
import { cn } from "@/lib/utils";
import type { DataState, MissionStatus, RiskLevel } from "@/types";

const base =
  "inline-flex shrink-0 items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] font-medium leading-none";

const DATA_STATE_STYLE: Record<DataState, { icon: LucideIcon; className: string }> = {
  LATEST_OBSERVATION: { icon: Radio, className: "border-success/40 bg-success/10 text-success" },
  HISTORICAL_OBSERVATION: { icon: History, className: "border-info/40 bg-info/10 text-info" },
  MODELLED_CONDITION: { icon: Cpu, className: "border-info/40 bg-info/10 text-info" },
  DEMONSTRATION_DATA: { icon: FlaskConical, className: "border-sand/40 bg-sand/10 text-sand" },
  DATA_UNAVAILABLE: {
    icon: CircleSlash,
    className: "border-border bg-surface text-muted-foreground",
  },
  LIMITED_CONFIDENCE: {
    icon: ShieldAlert,
    className: "border-warning/40 bg-warning/10 text-warning",
  },
  DERIVED: { icon: GitBranch, className: "border-border bg-surface text-foreground" },
};

export function DataStateBadge({ state, className }: { state: DataState; className?: string }) {
  const s = DATA_STATE_STYLE[state] ?? DATA_STATE_STYLE.DATA_UNAVAILABLE;
  const Icon = s.icon;
  return (
    <span className={cn(base, s.className, className)} title={DATA_STATE_HINT[state]}>
      <Icon className="size-3" aria-hidden />
      {DATA_STATE_LABEL[state] ?? state}
    </span>
  );
}

const RISK_STYLE: Record<RiskLevel, { icon: LucideIcon; className: string }> = {
  LOW: { icon: ShieldCheck, className: "border-risk-low/50 bg-risk-low/10 text-risk-low" },
  MODERATE: {
    icon: AlertTriangle,
    className: "border-risk-moderate/50 bg-risk-moderate/10 text-risk-moderate",
  },
  HIGH: { icon: AlertTriangle, className: "border-risk-high/50 bg-risk-high/10 text-risk-high" },
  CRITICAL: {
    icon: AlertOctagon,
    className: "border-risk-critical/50 bg-risk-critical/15 text-risk-critical",
  },
};

export function RiskBadge({ risk, className }: { risk: RiskLevel; className?: string }) {
  const s = RISK_STYLE[risk];
  const Icon = s.icon;
  return (
    <span className={cn(base, s.className, className)}>
      <Icon className="size-3" aria-hidden />
      {RISK_LABEL[risk]}
    </span>
  );
}

export function FeasibleBadge({ feasible, className }: { feasible: boolean; className?: string }) {
  return feasible ? (
    <span className={cn(base, "border-border bg-surface text-foreground", className)}>
      <CheckCircle2 className="size-3 text-success" aria-hidden /> Feasible
    </span>
  ) : (
    <span
      className={cn(
        base,
        "border-dashed border-destructive/60 bg-destructive/10 text-destructive",
        className,
      )}
    >
      <XCircle className="size-3" aria-hidden /> Not feasible
    </span>
  );
}

const STATUS_STYLE: Record<MissionStatus, { icon: LucideIcon; className: string }> = {
  DRAFT: {
    icon: PencilLine,
    className: "border-status-draft/40 bg-status-draft/10 text-status-draft",
  },
  PLANNED: {
    icon: CircleDashed,
    className: "border-status-planned/40 bg-status-planned/10 text-status-planned",
  },
  FINALIZED: {
    icon: Lock,
    className: "border-status-finalized/40 bg-status-finalized/10 text-status-finalized",
  },
};

export function StatusBadge({ status, className }: { status: MissionStatus; className?: string }) {
  const s = STATUS_STYLE[status];
  const Icon = s.icon;
  return (
    <span className={cn(base, s.className, className)}>
      <Icon className="size-3" aria-hidden />
      {STATUS_LABEL[status]}
    </span>
  );
}
