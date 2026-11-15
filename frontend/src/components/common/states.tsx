import { Link } from "@tanstack/react-router";
import { AlertCircle, CircleSlash, Rocket } from "lucide-react";
import type { ReactNode } from "react";

import { isApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { UNAVAILABLE } from "@/lib/format";
import { cn } from "@/lib/utils";

export function EmptyState({
  icon,
  title,
  description,
  children,
  className,
}: {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  children?: ReactNode;
  className?: string | undefined;
}) {
  return (
    <div
      className={cn(
        "panel grid-backdrop flex flex-col items-center px-6 py-12 text-center",
        className,
      )}
    >
      <div className="flex size-11 items-center justify-center rounded-full border border-border bg-surface text-sand">
        {icon ?? <Rocket className="size-5" />}
      </div>
      <h2 className="mt-4 text-base font-semibold">{title}</h2>
      {description && <p className="mt-1 max-w-md text-sm text-muted-foreground">{description}</p>}
      {children && <div className="mt-5 flex flex-wrap justify-center gap-2">{children}</div>}
    </div>
  );
}

/** Error panel driven by the API error code. */
export function ErrorState({
  error,
  onRetry,
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}) {
  const notFound = isApiError(error, "MISSION_NOT_FOUND") || isApiError(error, "REGION_NOT_FOUND");
  const message = error instanceof Error ? error.message : "Something went wrong.";
  return (
    <EmptyState
      className={className}
      icon={<AlertCircle className="size-5 text-destructive" />}
      title={notFound ? "Not found" : "Could not load data"}
      description={message}
    >
      {notFound ? (
        <Button variant="outline" asChild>
          <Link to="/missions">Back to missions</Link>
        </Button>
      ) : (
        onRetry && (
          <Button variant="outline" onClick={onRetry}>
            Try again
          </Button>
        )
      )}
    </EmptyState>
  );
}

export function PanelSkeleton({ rows = 4, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("panel space-y-3 p-5", className)} aria-busy="true" aria-label="Loading">
      <Skeleton className="h-4 w-1/3" />
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-3.5" style={{ width: `${90 - i * 12}%` }} />
      ))}
    </div>
  );
}

/** Renders a formatted value; missing values get a neutral "Data unavailable" treatment. */
export function Value({ children, className }: { children: string; className?: string }) {
  if (children === UNAVAILABLE)
    return (
      <span
        className={cn("inline-flex items-center gap-1 text-muted-foreground italic", className)}
      >
        <CircleSlash className="size-3 not-italic" aria-hidden />
        {UNAVAILABLE}
      </span>
    );
  return <span className={cn("data-value", className)}>{children}</span>;
}
