import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import ForceGraph2D from "react-force-graph-2d";
import { ArrowClockwise, FunnelSimple, X } from "@phosphor-icons/react";
import PageHeader from "../components/PageHeader";
import LoadingSpinner from "../components/LoadingSpinner";
import { useToastContext } from "../context/ToastContext";
import { Button } from "../components/common/Button";
import { cn } from "../lib/utils";

type NodeType = "api" | "core" | "storage" | "worker" | "dashboard" | "hook";

type LinkType = "imports" | "calls" | "data_flow" | "triggers";

interface GraphNode {
  id: string;
  label: string;
  type: NodeType;
  description: string;
  x?: number;
  y?: number;
}

interface GraphLink {
  source: string | GraphNode;
  target: string | GraphNode;
  type: LinkType;
}

interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
  metadata: { generated_at: string; node_count: number; link_count: number };
}

const NODE_COLORS: Record<NodeType, string> = {
  api: "#22d3ee",
  core: "#a78bfa",
  storage: "#34d399",
  worker: "#fb923c",
  dashboard: "#f472b6",
  hook: "#38bdf8",
};

const NODE_LABELS: Record<NodeType, string> = {
  api: "API Routes",
  core: "Core Logic",
  storage: "Storage",
  worker: "Workers",
  dashboard: "Dashboard",
  hook: "Hooks",
};

const LINK_COLORS: Record<LinkType, string> = {
  imports: "rgba(161,161,170,0.15)",
  calls: "rgba(139,92,246,0.25)",
  data_flow: "rgba(34,211,238,0.2)",
  triggers: "rgba(251,146,60,0.3)",
};

function nodeId(n: string | GraphNode): string {
  return typeof n === "string" ? n : n.id;
}

export default function GraphPage() {
  const { addToast } = useToastContext();
  const [data, setData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTypes, setActiveTypes] = useState<Set<NodeType>>(
    new Set(["api", "core", "storage", "worker", "dashboard", "hook"]),
  );
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const graphRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState<{
    width: number;
    height: number;
  } | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/dashboard/graph-data.json");
      const json: GraphData = await res.json();
      setData(json);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to load graph data";
      addToast(message, "error");
    } finally {
      setLoading(false);
    }
  }, [addToast]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Measure container and keep dimensions in sync
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const measure = () => {
      const rect = el.getBoundingClientRect();
      setDimensions({ width: rect.width, height: rect.height });
    };
    // Initial measurement
    measure();
    const obs = new ResizeObserver(measure);
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  // Prevent scroll events on graph container from scrolling the page
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const handler = (e: WheelEvent) => e.preventDefault();
    el.addEventListener("wheel", handler, { passive: false });
    return () => el.removeEventListener("wheel", handler);
  }, []);

  const toggleType = useCallback((type: NodeType) => {
    setActiveTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  }, []);

  const filteredData = useMemo(() => {
    if (!data) return null;
    const nodeIds = new Set(
      data.nodes.filter((n) => activeTypes.has(n.type)).map((n) => n.id),
    );
    return {
      nodes: data.nodes.filter((n) => nodeIds.has(n.id)),
      links: data.links.filter(
        (l) => nodeIds.has(nodeId(l.source)) && nodeIds.has(nodeId(l.target)),
      ),
    };
  }, [data, activeTypes]);

  const connectedIds = useMemo(() => {
    if (!selectedNode || !data) return new Set<string>();
    const ids = new Set<string>([selectedNode.id]);
    for (const l of data.links) {
      const src = nodeId(l.source);
      const tgt = nodeId(l.target);
      if (src === selectedNode.id) ids.add(tgt);
      if (tgt === selectedNode.id) ids.add(src);
    }
    return ids;
  }, [selectedNode, data]);

  const handleNodeClick = useCallback((node: any) => {
    setSelectedNode((prev) => (prev?.id === node.id ? null : node));
  }, []);

  const handleNodeHover = useCallback((node: any) => {
    setHoveredNode(node || null);
  }, []);

  const paintNode = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const n = node as GraphNode;
      const color = NODE_COLORS[n.type] || "#a1a1aa";
      const r = n.type === "core" ? 6 : n.type === "storage" ? 5.5 : 4.5;
      const dimmed = selectedNode && !connectedIds.has(n.id) ? 0.12 : 1;
      const isSelected = selectedNode?.id === n.id;
      const isHovered = hoveredNode?.id === n.id;

      ctx.globalAlpha = dimmed;

      if (isSelected || isHovered) {
        ctx.beginPath();
        ctx.arc(node.x, node.y, r + 3, 0, Math.PI * 2);
        ctx.fillStyle = color + (isSelected ? "30" : "18");
        ctx.fill();
      }

      ctx.beginPath();
      ctx.arc(node.x, node.y, r, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();

      if (globalScale > 1.2) {
        ctx.font = `${Math.max(10 / globalScale, 2.5)}px sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.fillStyle = "rgba(244,244,245,0.85)";
        ctx.fillText(n.label, node.x, node.y + r + 2);
      }

      ctx.globalAlpha = 1;
    },
    [selectedNode, connectedIds, hoveredNode],
  );

  const paintLink = useCallback(
    (link: any, ctx: CanvasRenderingContext2D) => {
      const l = link as GraphLink;
      const src = l.source as any;
      const tgt = l.target as any;
      if (!src.x || !tgt.x) return;

      const srcId = nodeId(l.source);
      const tgtId = nodeId(l.target);
      const dimmed =
        selectedNode && !connectedIds.has(srcId) && !connectedIds.has(tgtId)
          ? 0.04
          : 1;

      ctx.globalAlpha = dimmed;
      ctx.beginPath();
      ctx.moveTo(src.x, src.y);
      ctx.lineTo(tgt.x, tgt.y);
      ctx.strokeStyle = LINK_COLORS[l.type] || "rgba(161,161,170,0.1)";
      ctx.lineWidth = l.type === "triggers" ? 1.2 : 0.6;
      if (l.type === "data_flow") {
        ctx.setLineDash([3, 3]);
      }
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.globalAlpha = 1;
    },
    [selectedNode, connectedIds],
  );

  return (
    <div className="flex flex-col h-[calc(100vh-48px)] lg:h-[calc(100vh-64px)]">
      <PageHeader
        title="Architecture Graph"
        subtitle={`${data?.metadata.node_count ?? 0} modules, ${data?.metadata.link_count ?? 0} connections`}
      >
        <Button variant="secondary" size="sm" onClick={fetchData}>
          <ArrowClockwise size={14} /> Refresh
        </Button>
      </PageHeader>

      {/* Filter pills */}
      <div className="flex flex-wrap items-center gap-2 mb-3 shrink-0">
        <FunnelSimple size={16} className="text-zinc-400" />
        {(Object.entries(NODE_LABELS) as [NodeType, string][]).map(
          ([type, label]) => (
            <button
              key={type}
              onClick={() => toggleType(type)}
              className={cn(
                "flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition-all",
                activeTypes.has(type)
                  ? "border border-white/10"
                  : "border border-white/5 opacity-40",
              )}
              style={{
                backgroundColor: activeTypes.has(type)
                  ? NODE_COLORS[type] + "18"
                  : "transparent",
                color: NODE_COLORS[type],
              }}
            >
              <span
                className="inline-block w-2 h-2 rounded-full"
                style={{ backgroundColor: NODE_COLORS[type] }}
              />
              {label}
            </button>
          ),
        )}
      </div>

      {/* Graph canvas — fills all remaining space */}
      <div
        ref={containerRef}
        className="flex-1 min-h-0 rounded-xl border border-zinc-200 dark:border-white/[0.06] bg-zinc-100 dark:bg-zinc-900/60 overflow-hidden relative"
      >
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center z-20">
            <LoadingSpinner />
          </div>
        )}
        {filteredData && dimensions && (
          <ForceGraph2D
            ref={graphRef}
            graphData={filteredData}
            width={dimensions.width}
            height={dimensions.height}
            backgroundColor="transparent"
            nodeCanvasObject={paintNode}
            linkCanvasObject={paintLink}
            onNodeClick={handleNodeClick}
            onNodeHover={handleNodeHover}
            onBackgroundClick={() => setSelectedNode(null)}
            nodeId="id"
            cooldownTicks={120}
            d3AlphaDecay={0.02}
            d3VelocityDecay={0.3}
            enableNodeDrag={true}
            enableZoomInteraction={true}
            enablePanInteraction={true}
          />
        )}

        {/* Hover tooltip */}
        {hoveredNode && !selectedNode && (
          <div className="absolute top-3 left-3 pointer-events-none rounded-lg bg-zinc-900/90 backdrop-blur-md border border-white/10 px-3 py-2 max-w-xs shadow-xl z-10">
            <div className="flex items-center gap-2 mb-1">
              <span
                className="w-2 h-2 rounded-full"
                style={{ backgroundColor: NODE_COLORS[hoveredNode.type] }}
              />
              <span className="text-sm font-medium text-zinc-100">
                {hoveredNode.label}
              </span>
              <span className="text-[10px] uppercase tracking-wider text-zinc-500">
                {hoveredNode.type}
              </span>
            </div>
            <p className="text-xs text-zinc-400">{hoveredNode.description}</p>
          </div>
        )}

        {/* Detail panel — overlay inside graph container */}
        {selectedNode && data && (
          <div className="absolute top-3 right-3 w-72 rounded-xl border border-white/[0.08] bg-zinc-900/90 backdrop-blur-2xl p-4 shadow-2xl z-10 max-h-[calc(100%-24px)] overflow-y-auto">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span
                  className="w-3 h-3 rounded-full"
                  style={{
                    backgroundColor: NODE_COLORS[selectedNode.type],
                  }}
                />
                <span className="font-medium text-zinc-100 text-sm">
                  {selectedNode.label}
                </span>
              </div>
              <button
                onClick={() => setSelectedNode(null)}
                className="rounded-md p-1 hover:bg-zinc-800 transition-colors text-zinc-400"
              >
                <X size={14} />
              </button>
            </div>

            <span
              className="inline-block text-[10px] uppercase tracking-wider font-medium px-2 py-0.5 rounded-full mb-2"
              style={{
                backgroundColor: NODE_COLORS[selectedNode.type] + "18",
                color: NODE_COLORS[selectedNode.type],
              }}
            >
              {selectedNode.type}
            </span>

            <p className="text-xs text-zinc-400 mb-4">
              {selectedNode.description}
            </p>

            <p className="text-[10px] uppercase tracking-wider text-zinc-500 font-medium mb-1.5">
              {selectedNode.id}
            </p>

            {/* Connections */}
            <div className="border-t border-white/[0.06] pt-3 mt-2">
              <p className="text-[10px] uppercase tracking-wider text-zinc-500 font-medium mb-2">
                Connections
              </p>
              <div className="flex flex-col gap-1.5">
                {data.links
                  .filter((l) => {
                    const src = nodeId(l.source);
                    const tgt = nodeId(l.target);
                    return src === selectedNode.id || tgt === selectedNode.id;
                  })
                  .map((l, i) => {
                    const src = nodeId(l.source);
                    const tgt = nodeId(l.target);
                    const otherId = src === selectedNode.id ? tgt : src;
                    const other = data.nodes.find((n) => n.id === otherId);
                    const direction =
                      src === selectedNode.id ? "\u2192" : "\u2190";
                    return (
                      <div
                        key={i}
                        className="flex items-center gap-1.5 text-xs cursor-pointer hover:bg-white/5 rounded px-1.5 py-0.5 transition-colors"
                        onClick={() => {
                          if (other) setSelectedNode(other);
                        }}
                      >
                        <span
                          className="w-1.5 h-1.5 rounded-full shrink-0"
                          style={{
                            backgroundColor: other
                              ? NODE_COLORS[other.type]
                              : "#a1a1aa",
                          }}
                        />
                        <span className="text-zinc-400">{direction}</span>
                        <span className="text-zinc-300 truncate">
                          {other?.label ?? otherId}
                        </span>
                        <span className="text-zinc-600 text-[10px] ml-auto shrink-0">
                          {l.type}
                        </span>
                      </div>
                    );
                  })}
              </div>
            </div>
          </div>
        )}

        {/* Legend */}
        <div className="absolute bottom-3 right-3 rounded-lg bg-zinc-900/80 backdrop-blur-md border border-white/10 px-3 py-2 z-10">
          <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1.5">
            Link Types
          </div>
          <div className="flex flex-col gap-1">
            {(["calls", "imports", "data_flow", "triggers"] as LinkType[]).map(
              (type) => (
                <div key={type} className="flex items-center gap-2">
                  <span
                    className="w-4 h-0.5 inline-block"
                    style={{
                      backgroundColor:
                        type === "calls"
                          ? "#8b5cf6"
                          : type === "triggers"
                            ? "#fb923c"
                            : type === "data_flow"
                              ? "#22d3ee"
                              : "#a1a1aa",
                      borderBottom:
                        type === "data_flow" ? "1px dashed" : undefined,
                    }}
                  />
                  <span className="text-[10px] text-zinc-400">
                    {type.replace("_", " ")}
                  </span>
                </div>
              ),
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
