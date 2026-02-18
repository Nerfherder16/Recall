import { useState, useEffect, useCallback } from "react";
import { ArrowClockwise } from "@phosphor-icons/react";
import { api } from "../api/client";
import type { HealthDashboard, Conflict } from "../api/types";
import PageHeader from "../components/PageHeader";
import LoadingSpinner from "../components/LoadingSpinner";
import { useToastContext } from "../context/ToastContext";
import { Button } from "../components/common/Button";
import { FeedbackCard } from "../components/health/FeedbackCard";
import { PopulationCard } from "../components/health/PopulationCard";
import { GraphCohesionCard } from "../components/health/GraphCohesionCard";
import { PinRatioCard } from "../components/health/PinRatioCard";
import { ImportanceChart } from "../components/health/ImportanceChart";
import { FeedbackHistogram } from "../components/health/FeedbackHistogram";
import { ConflictsTable } from "../components/health/ConflictsTable";
import { StaleAuditSection } from "../components/StaleAuditSection";

export default function HealthPage() {
  const { addToast } = useToastContext();
  const [dashboard, setDashboard] = useState<HealthDashboard | null>(null);
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [dash, conf] = await Promise.all([
        api<HealthDashboard>("/admin/health/dashboard"),
        api<{ conflicts: Conflict[] }>("/admin/conflicts"),
      ]);
      setDashboard(dash);
      setConflicts(conf.conflicts || []);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to load health data";
      addToast(message, "error");
    } finally {
      setLoading(false);
    }
  }, [addToast]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (loading) return <LoadingSpinner />;

  return (
    <div>
      <PageHeader
        title="System Health"
        subtitle="Memory system metrics, force analysis, and conflict detection"
      >
        <Button variant="secondary" size="sm" onClick={fetchData}>
          <ArrowClockwise size={14} /> Refresh
        </Button>
      </PageHeader>

      {dashboard && (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <FeedbackCard feedback={dashboard.feedback} />
            <PopulationCard population={dashboard.population} />
            <GraphCohesionCard graph={dashboard.graph} />
            <PinRatioCard pins={dashboard.pins} />
          </div>

          {/* Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-8">
            <ImportanceChart bands={dashboard.importance_distribution} />
            <FeedbackHistogram buckets={dashboard.feedback_similarity} />
          </div>
        </>
      )}

      {/* Stale Memories */}
      <div className="mb-8">
        <StaleAuditSection />
      </div>

      {/* Conflicts */}
      <ConflictsTable conflicts={conflicts} />
    </div>
  );
}
