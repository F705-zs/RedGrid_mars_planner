import { Link } from "@tanstack/react-router";
import { FlaskConical } from "lucide-react";

import { Button } from "@/components/ui/button";
import { USE_MOCKS } from "@/config";

import { DataSourcesSheet } from "./DataSourcesSheet";
import { RedGridLogo } from "./RedGridLogo";
import { RegionSelector } from "./RegionSelector";

const navLink =
  "rounded-md px-2.5 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-surface hover:text-foreground data-[status=active]:bg-surface data-[status=active]:text-foreground";

export function AppHeader() {
  return (
    <header className="no-print z-40 shrink-0 border-b border-border bg-panel">
      <div className="flex h-12 items-center gap-3 px-4">
        <Link to="/" className="flex shrink-0 items-center gap-2" aria-label="RedGrid explorer">
          <RedGridLogo />
          <span className="text-[15px] font-semibold tracking-tight">RedGrid</span>
        </Link>
        <RegionSelector />
        {USE_MOCKS && (
          <span
            className="inline-flex items-center gap-1 rounded border border-warning/50 bg-warning/10 px-2 py-0.5 text-[11px] text-warning"
            title="VITE_USE_MOCKS is on: answers come from built-in test fixtures, not the RedGrid API."
          >
            <FlaskConical className="size-3" /> Mock mode
          </span>
        )}
        <div className="flex-1" />
        <nav className="flex items-center gap-0.5" aria-label="Main">
          <Link to="/" activeOptions={{ exact: true }} className={navLink}>
            Explorer
          </Link>
          <Link to="/missions" activeOptions={{ exact: true }} className={navLink}>
            Missions
          </Link>
          <DataSourcesSheet />
          <Button size="sm" className="ml-1.5 h-8" asChild>
            <Link to="/missions/new">New mission</Link>
          </Button>
        </nav>
      </div>
    </header>
  );
}
