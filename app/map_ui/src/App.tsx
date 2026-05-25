import React, { useEffect, useMemo, useRef, useState } from "react";
import DeckGL from "@deck.gl/react";
import { GeoJsonLayer } from "@deck.gl/layers";
import { TileLayer } from "@deck.gl/geo-layers";
import { BitmapLayer } from "@deck.gl/layers";
import { layout, prepare } from "@chenglou/pretext";
import {
  Activity,
  AlertTriangle,
  Brain,
  Clock3,
  MapPinned,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  RadioTower,
  Send,
  Sparkles,
  X,
} from "lucide-react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

type FeatureCollection = {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    properties: Record<string, unknown>;
    geometry: Record<string, unknown>;
  }>;
};

type RiskSummaryRow = {
  severity: string | null;
  event_type: string;
  count: number;
};

type ToolResult = {
  tool: string;
  count: number;
  features: FeatureCollection["features"];
  explanation: string;
  confidence: number;
};

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

type SelectedFeature = {
  id: string;
  properties: Record<string, unknown>;
} | null;

type IntelligenceMode = "live" | "flow" | "scenario" | "intelligence" | "memory";

// Layer visibility set for a given mode
type LayerSet = {
  routes: boolean;
  facilities: boolean;
  ports: boolean;
  alerts: boolean;
  riskScores: boolean | "auto"; // "auto" = on whenever active alerts exist
  streamGauges: boolean;
};

// Scalable config: add/change modes here without touching component logic
const MODE_LAYERS: Record<IntelligenceMode, LayerSet> = {
  live:         { routes: true,  facilities: true,  ports: true, alerts: true,  riskScores: "auto", streamGauges: true  },
  flow:         { routes: true,  facilities: true,  ports: true, alerts: false, riskScores: false,  streamGauges: false },
  scenario:     { routes: true,  facilities: true,  ports: true, alerts: true,  riskScores: true,   streamGauges: false },
  intelligence: { routes: false, facilities: true,  ports: true, alerts: true,  riskScores: true,   streamGauges: true  },
  memory:       { routes: true,  facilities: true,  ports: true, alerts: false, riskScores: false,  streamGauges: false },
};

const INITIAL_VIEW_STATE = {
  longitude: -74.22,
  latitude: 41.05,
  zoom: 6.2,
  pitch: 25,
  bearing: 0
};

const layerColors: Record<string, [number, number, number, number]> = {
  port: [25, 105, 138, 240],
  facility: [205, 104, 64, 230],
  route: [29, 132, 148, 225],
  location: [20, 160, 160, 200],
  risk: [221, 86, 58, 96]
};

function canMeasureText() {
  if (typeof document === "undefined") return false;
  if (typeof navigator !== "undefined" && navigator.userAgent.toLowerCase().includes("jsdom")) {
    return false;
  }
  try {
    return Boolean(document.createElement("canvas").getContext("2d"));
  } catch {
    return false;
  }
}

function measureNarrativeHeight(text: string) {
  if (!canMeasureText()) return 0;
  try {
    const prepared = prepare(text, "13px Inter");
    return layout(prepared, 344, 18).height;
  } catch {
    return 0;
  }
}

function escapeHtml(value: unknown) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function titleize(value: unknown) {
  return String(value ?? "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter: string) => letter.toUpperCase());
}

function tooltipHtml(props: Record<string, unknown>) {
  const isRiskEvent = props.record_type === "risk_event" || Boolean(props.event_type);
  const isRiskScore = props.record_type === "risk_score";
  const isGauge = props.record_type === "stream_gauge";
  const title = isRiskEvent
    ? props.headline || props.event_type || "NOAA alert"
    : props.name || props.subtype || props.entity_type || "Supply-chain entity";
  const rows = isRiskEvent
    ? [
        ["Type", props.event_type],
        ["Severity", props.severity],
        ["Area", props.area_desc],
        ["Source", props.source_name],
      ]
    : isRiskScore
    ? [
        ["Type", titleize(props.entity_type)],
        ["Risk score", props.risk_score],
        ["Top severity", props.top_severity],
        ["Alerts", props.impact_count],
      ]
    : isGauge
    ? [
        ["Status", props.at_risk ? "⚠ At risk" : "Normal"],
        ["Active alerts", props.active_alert_count],
        ["Site", (props.source_tags as Record<string, unknown>)?.site_no],
        ["Type", (props.source_tags as Record<string, unknown>)?.site_type_label],
      ]
    : [
        ["Type", titleize(props.entity_type)],
        ["Subtype", props.subtype],
        ["Source", props.source_name],
      ];
  const detail = rows
    .filter(([, value]) => value != null && value !== "")
    .map(([label, value]) => `<span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>`)
    .join("");

  return `<div class="map-tooltip"><h2>${escapeHtml(title)}</h2><div>${detail}</div></div>`;
}

function useGeoJson(entityType: string, enabled = true, subtype?: string) {
  const [data, setData] = useState<FeatureCollection>({ type: "FeatureCollection", features: [] });
  const [loading, setLoading] = useState(enabled);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    setLoading(true);
    const params = new URLSearchParams({ entity_type: entityType, limit: "25000" });
    if (subtype) params.set("subtype", subtype);
    fetch(`${API_BASE_URL}/geo/entities?${params}`)
      .then((response) => response.json())
      .then(setData)
      .finally(() => setLoading(false));
  }, [enabled, entityType, subtype]);

  return { data, loading };
}

function useStreamGauges(enabled = true) {
  const [data, setData] = useState<FeatureCollection>({ type: "FeatureCollection", features: [] });
  const [loading, setLoading] = useState(enabled);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    setLoading(true);
    fetch(`${API_BASE_URL}/geo/stream-gauges`)
      .then((r) => r.json())
      .then(setData)
      .finally(() => setLoading(false));
  }, [enabled]);

  return { data, loading };
}

function useRiskEvents(enabled = true) {
  const [data, setData] = useState<FeatureCollection>({ type: "FeatureCollection", features: [] });
  const [loading, setLoading] = useState(enabled);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    setLoading(true);
    fetch(`${API_BASE_URL}/risk/events?limit=1000`)
      .then((response) => response.json())
      .then(setData)
      .finally(() => setLoading(false));
  }, [enabled]);

  return { data, loading };
}

function useRiskImpacts(eventId: string | null) {
  const [data, setData] = useState<FeatureCollection>({ type: "FeatureCollection", features: [] });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!eventId) {
      setData({ type: "FeatureCollection", features: [] });
      setLoading(false);
      return;
    }
    setLoading(true);
    fetch(`${API_BASE_URL}/risk/events/${eventId}/impacts?limit=5000`)
      .then((response) => response.json())
      .then(setData)
      .catch(() => setData({ type: "FeatureCollection", features: [] }))
      .finally(() => setLoading(false));
  }, [eventId]);

  return { data, loading };
}

function riskScoreColor(score: number): [number, number, number, number] {
  if (score >= 6) return [207, 52, 40, 240];
  if (score >= 3) return [230, 130, 30, 230];
  if (score >= 1) return [210, 185, 30, 220];
  return [55, 170, 65, 210];
}

function useRiskScores(enabled = true) {
  const [data, setData] = useState<FeatureCollection>({ type: "FeatureCollection", features: [] });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!enabled) {
      setData({ type: "FeatureCollection", features: [] });
      setLoading(false);
      return;
    }
    setLoading(true);
    fetch(`${API_BASE_URL}/risk/scores?limit=5000`)
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData({ type: "FeatureCollection", features: [] }))
      .finally(() => setLoading(false));
  }, [enabled]);

  return { data, loading };
}

function useRiskSummary() {
  const [summary, setSummary] = useState<RiskSummaryRow[]>([]);

  useEffect(() => {
    fetch(`${API_BASE_URL}/risk/summary`)
      .then((response) => response.json())
      .then(setSummary)
      .catch(() => setSummary([]));
  }, []);

  return summary;
}

function gaugeColor(atRisk: boolean): [number, number, number, number] {
  return atRisk ? [220, 60, 50, 240] : [30, 130, 180, 200];
}

// Mode-aware operational narrative — pure function, no hooks
function getModeNarrative(
  mode: IntelligenceMode,
  activeRiskCount: number,
  atRiskGaugeCount: number
): { headline: string; context: string; drivers: string[]; confidence: string } {
  switch (mode) {
    case "live":
      return activeRiskCount > 0
        ? {
            headline: "Operational pressure increasing.",
            context: `${activeRiskCount} active signal${activeRiskCount === 1 ? "" : "s"} intersecting the Atlantic corridor.`,
            drivers: [
              "Coastal hazard signals intersect exposed freight corridors",
              "Port and facility proximity edges updating from active events",
              atRiskGaugeCount > 0
                ? `${atRiskGaugeCount} hydrologic gauge${atRiskGaugeCount === 1 ? "" : "s"} in stressed state`
                : "Hydrologic monitoring active across regional infrastructure",
            ],
            confidence: "Moderate",
          }
        : {
            headline: "Network stable.",
            context: "No active pressure signals intersecting priority assets.",
            drivers: [
              "Movement corridors within normal observation bands",
              "No events intersecting ports or facilities",
              "Hydrologic monitoring active — no stressed gauges",
            ],
            confidence: "High",
          };
    case "flow":
      return {
        headline: "Movement corridor view.",
        context: "Highway, rail, waterway, and ferry routes across NY / NJ / CT.",
        drivers: [
          "Port interfaces and facility nodes overlaid",
          "Route network indexed from OSM statewide extracts",
          "Cargo flow and chain tracing in development",
        ],
        confidence: "High",
      };
    case "scenario":
      return {
        headline: "Scenario mode active.",
        context: "Model a disruption and trace its downstream impact.",
        drivers: [
          "Risk score overlay active — weighted exposure per asset",
          "Active alerts and impact edges loaded",
          "Ask: what happens if a corridor fails?",
        ],
        confidence: "Pending query",
      };
    case "intelligence":
      return {
        headline: "AI analysis mode.",
        context: "Risk scores and sensor signals cross-referenced.",
        drivers: [
          "Weighted risk scores across ports, facilities, and routes",
          "Stream gauges and NWS alerts spatially joined",
          "Ask for observations or anomalies",
        ],
        confidence: "Moderate",
      };
    case "memory":
      return {
        headline: "Historical replay mode.",
        context: "Pattern analysis requires accumulated ingestion history.",
        drivers: [
          "Live ingestion pipeline active — history accumulating",
          "Trend analysis and anomaly detection coming",
          "Ask about patterns in the current dataset",
        ],
        confidence: "Low",
      };
  }
}

const intelligenceModes: Array<{
  id: IntelligenceMode;
  label: string;
  icon: React.ReactNode;
}> = [
  { id: "live", label: "Live", icon: <RadioTower size={15} /> },
  { id: "flow", label: "Flow", icon: <Activity size={15} /> },
  { id: "scenario", label: "Scenario", icon: <Sparkles size={15} /> },
  { id: "intelligence", label: "Intel", icon: <Brain size={15} /> },
  { id: "memory", label: "Memory", icon: <Clock3 size={15} /> },
];

export function App() {
  const [mode, setMode] = useState<IntelligenceMode>("live");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [signalsExpanded, setSignalsExpanded] = useState(false);
  const [selectedRiskEventId, setSelectedRiskEventId] = useState<string | null>(null);
  const [selectedFeature, setSelectedFeature] = useState<SelectedFeature>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [chatToolResult, setChatToolResult] = useState<ToolResult | null>(null);
  const [syncedAt, setSyncedAt] = useState<Date | null>(null);
  const [syncAge, setSyncAge] = useState("now");
  const chatEndRef = useRef<HTMLDivElement>(null);

  const riskSummary = useRiskSummary();
  const activeRiskCount = riskSummary.reduce((total, item) => total + item.count, 0);

  // Layer visibility is derived from mode — no manual toggles
  const visibleLayers = useMemo(() => {
    const m = MODE_LAYERS[mode];
    return {
      routes: m.routes,
      facilities: m.facilities,
      ports: m.ports,
      alerts: m.alerts,
      riskScores: m.riskScores === "auto" ? activeRiskCount > 0 : m.riskScores,
      streamGauges: m.streamGauges,
    };
  }, [mode, activeRiskCount]);

  // Clear map selection when switching modes
  useEffect(() => {
    setSelectedFeature(null);
    setSelectedRiskEventId(null);
  }, [mode]);

  const ports = useGeoJson("port", visibleLayers.ports);
  const facilities = useGeoJson("facility", visibleLayers.facilities);
  const routes = useGeoJson("route", visibleLayers.routes);
  const streamGauges = useStreamGauges(visibleLayers.streamGauges);
  const riskEvents = useRiskEvents(visibleLayers.alerts);
  const riskImpacts = useRiskImpacts(selectedRiskEventId);
  // Always fetch risk scores so the layer can activate as soon as alerts appear
  const riskScores = useRiskScores(true);

  const atRiskGaugeCount = streamGauges.data.features.filter((f) => f.properties.at_risk).length;
  const visibleRiskSignals = signalsExpanded
    ? riskEvents.data.features
    : riskEvents.data.features.slice(0, 3);
  const hiddenRiskSignalCount = Math.max(riskEvents.data.features.length - 3, 0);

  const narrative = getModeNarrative(mode, activeRiskCount, atRiskGaugeCount);
  const narrativeText = [narrative.headline, narrative.context, ...narrative.drivers].join(" ");
  const narrativeMinHeight = useMemo(() => measureNarrativeHeight(narrativeText), [narrativeText]);

  const modePrompts: Record<IntelligenceMode, string> = {
    live: "What is changing right now?",
    flow: "How are goods moving through this network?",
    scenario: "What happens if a corridor fails?",
    intelligence: "What should I care about?",
    memory: "What patterns have we learned?",
  };

  const isLoading =
    ports.loading ||
    facilities.loading ||
    routes.loading ||
    streamGauges.loading ||
    riskEvents.loading ||
    riskImpacts.loading ||
    riskScores.loading;

  // Track last sync timestamp
  useEffect(() => {
    if (!isLoading) setSyncedAt(new Date());
  }, [isLoading]);

  useEffect(() => {
    if (!syncedAt) return;
    const tick = () => {
      const secs = Math.floor((Date.now() - syncedAt.getTime()) / 1000);
      setSyncAge(secs < 60 ? `${secs}s ago` : `${Math.floor(secs / 60)}m ago`);
    };
    tick();
    const id = setInterval(tick, 30_000);
    return () => clearInterval(id);
  }, [syncedAt]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [chatMessages, chatLoading]);

  function handleFeatureClick(object: { id?: unknown; properties?: Record<string, unknown> } | null) {
    if (!object) {
      setSelectedFeature(null);
      setSelectedRiskEventId(null);
      return;
    }
    const props = object.properties ?? {};
    const id = String(object.id ?? "");
    setSelectedFeature({ id, properties: props });
    if (props.record_type === "risk_event") {
      setSelectedRiskEventId(id);
    } else {
      setSelectedRiskEventId(null);
    }
  }

  async function sendChat() {
    const content = chatInput.trim();
    if (!content || chatLoading) return;

    const newMessages: ChatMessage[] = [...chatMessages, { role: "user", content }];
    setChatMessages(newMessages);
    setChatInput("");
    setChatLoading(true);

    try {
      const resp = await fetch(`${API_BASE_URL}/tools/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: newMessages,
          active_layers: Object.entries(visibleLayers)
            .filter(([, v]) => v)
            .map(([k]) => k),
        }),
      });
      const data = await resp.json() as {
        response: string;
        tool_used: string | null;
        tool_result: ToolResult | null;
      };
      setChatMessages([...newMessages, { role: "assistant", content: data.response }]);
      if (data.tool_result) {
        setChatToolResult(data.tool_result);
      }
    } catch {
      setChatMessages([...newMessages, {
        role: "assistant",
        content: "Sorry, I couldn't reach the server. Please try again."
      }]);
    } finally {
      setChatLoading(false);
    }
  }

  const layers = useMemo(() => {
    const osmTiles = new TileLayer({
      id: "osm-base-tiles",
      data: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
      minZoom: 0,
      maxZoom: 19,
      tileSize: 256,
      renderSubLayers: (props) => {
        const tile = props.tile as unknown as {
          bbox?: { west: number; south: number; east: number; north: number };
          boundingBox?: [[number, number], [number, number]];
        };
        const bounds = tile.bbox
          ? [tile.bbox.west, tile.bbox.south, tile.bbox.east, tile.bbox.north]
          : [
              tile.boundingBox?.[0][0] ?? 0,
              tile.boundingBox?.[0][1] ?? 0,
              tile.boundingBox?.[1][0] ?? 0,
              tile.boundingBox?.[1][1] ?? 0
            ];
        return new BitmapLayer(props, {
          data: undefined,
          image: props.data,
          bounds: bounds as never
        });
      }
    });

    const routeLayer = new GeoJsonLayer({
      id: "routes",
      data: routes.data as never,
      pickable: true,
      stroked: true,
      filled: false,
      lineWidthMinPixels: 1,
      getLineColor: layerColors.route,
      getLineWidth: 2
    });

    const facilityLayer = new GeoJsonLayer({
      id: "facilities",
      data: facilities.data as never,
      pickable: true,
      stroked: true,
      filled: true,
      pointRadiusMinPixels: 3,
      getFillColor: layerColors.facility,
      getLineColor: [118, 64, 40, 230],
      getLineWidth: 1
    });

    const portLayer = new GeoJsonLayer({
      id: "ports",
      data: ports.data as never,
      pickable: true,
      stroked: true,
      filled: true,
      pointRadiusMinPixels: 5,
      getFillColor: layerColors.port,
      getLineColor: [12, 72, 104, 240],
      getLineWidth: 1
    });

    const streamGaugeLayer = new GeoJsonLayer({
      id: "stream-gauges",
      data: streamGauges.data as never,
      pickable: true,
      stroked: true,
      filled: true,
      pointRadiusMinPixels: 4,
      getFillColor: (f: { properties: { at_risk?: boolean } }) =>
        gaugeColor(Boolean(f.properties.at_risk)),
      getLineColor: (f: { properties: { at_risk?: boolean } }) =>
        f.properties.at_risk ? [160, 30, 20, 255] : [10, 80, 130, 230],
      getLineWidth: 1,
      updateTriggers: { getFillColor: [streamGauges.data], getLineColor: [streamGauges.data] },
    });

    const riskLayer = new GeoJsonLayer({
      id: "risk-events",
      data: riskEvents.data as never,
      pickable: true,
      stroked: true,
      filled: true,
      getFillColor: layerColors.risk,
      getLineColor: [154, 45, 39, 220],
      getLineWidth: 2,
      lineWidthMinPixels: 1
    });

    const riskImpactLayer = selectedRiskEventId
      ? new GeoJsonLayer({
          id: "risk-impacts",
          data: riskImpacts.data as never,
          pickable: true,
          stroked: true,
          filled: true,
          pointRadiusMinPixels: 8,
          getFillColor: [245, 194, 66, 230],
          getLineColor: [132, 89, 12, 255],
          getLineWidth: 3,
          lineWidthMinPixels: 2
        })
      : null;

    const riskScoreLayer = visibleLayers.riskScores
      ? new GeoJsonLayer({
          id: "risk-scores",
          data: riskScores.data as never,
          pickable: true,
          filled: true,
          stroked: true,
          pointRadiusMinPixels: 5,
          getFillColor: (f: { properties: { risk_score?: number } }) =>
            riskScoreColor(f.properties.risk_score ?? 0),
          getLineColor: [60, 20, 20, 180],
          getLineWidth: 2,
          lineWidthMinPixels: 1,
          updateTriggers: { getFillColor: [riskScores.data] },
        })
      : null;

    const chatResultLayer = chatToolResult && chatToolResult.count > 0
      ? new GeoJsonLayer({
          id: "chat-results",
          data: { type: "FeatureCollection", features: chatToolResult.features } as never,
          pickable: true,
          filled: true,
          stroked: true,
          pointRadiusMinPixels: 9,
          getFillColor: [255, 200, 0, 230],
          getLineColor: [160, 120, 0, 255],
          getLineWidth: 2,
          lineWidthMinPixels: 2,
        })
      : null;

    return [
      osmTiles,
      visibleLayers.routes ? routeLayer : null,
      visibleLayers.alerts ? riskLayer : null,
      riskImpactLayer,
      riskScoreLayer,
      visibleLayers.streamGauges ? streamGaugeLayer : null,
      visibleLayers.facilities ? facilityLayer : null,
      visibleLayers.ports ? portLayer : null,
      chatResultLayer,
    ].filter(Boolean);
  }, [
    facilities.data,
    streamGauges.data,
    ports.data,
    riskEvents.data,
    riskImpacts.data,
    riskScores.data,
    routes.data,
    selectedRiskEventId,
    visibleLayers,
    chatToolResult,
  ]);

  const selectedName = selectedFeature
    ? String(selectedFeature.properties.name || selectedFeature.properties.event_type || selectedFeature.properties.entity_type || "Entity")
    : null;
  const selectedType = selectedFeature
    ? String(selectedFeature.properties.record_type || selectedFeature.properties.entity_type || "")
    : null;

  return (
    <main>
      <DeckGL
        initialViewState={INITIAL_VIEW_STATE}
        controller
        layers={layers}
        getTooltip={({ object }) => {
          if (!object) return null;
          const props = object.properties ?? {};
          return { html: tooltipHtml(props) };
        }}
        onClick={({ object }) =>
          handleFeatureClick(object as { id?: unknown; properties?: Record<string, unknown> } | null)
        }
      />
      <div className="flow-field" aria-hidden />
      <div className="flow-ribbons" aria-hidden>
        <span />
        <span />
        <span />
      </div>

      <aside className={`command-surface${sidebarCollapsed ? " is-collapsed" : ""}`}>
        <div className="system-row">
          <div className="identity-lockup">
            <MapPinned size={20} aria-hidden />
            <div>
              <h1>Open Supply Chain</h1>
              <div className="aoi">NY + NJ + CT live operational model</div>
            </div>
          </div>
          <div className="system-pulse" aria-label="System status">
            <span className={isLoading ? "is-syncing" : ""} />
            <strong>{isLoading ? "Syncing" : "Live"}</strong>
          </div>
          <button
            type="button"
            className="collapse-button"
            aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            onClick={() => setSidebarCollapsed((c) => !c)}
          >
            {sidebarCollapsed ? <PanelLeftOpen size={15} /> : <PanelLeftClose size={15} />}
          </button>
        </div>

        <section className="mode-switcher" aria-label="Operational modes">
          {intelligenceModes.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`mode-button mode-button--${item.id}${mode === item.id ? " is-active" : ""}`}
              aria-pressed={mode === item.id}
              onClick={() => setMode(item.id)}
            >
              {item.icon}
              <span>{item.label}</span>
            </button>
          ))}
        </section>

        {!sidebarCollapsed && (
          <>
            <section
              className="narrative-brief"
              aria-label="Operational status"
              style={narrativeMinHeight > 0 ? { minHeight: narrativeMinHeight + 88 } : undefined}
            >
              <div className="narrative-mode-line">
                <span className={`mode-badge mode-badge--${mode}`}>{mode.toUpperCase()}</span>
                <span className="narrative-aoi">Atlantic Corridor</span>
              </div>
              <strong className="narrative-headline">{narrative.headline}</strong>
              <p className="narrative-context">{narrative.context}</p>
              <ul>
                {narrative.drivers.map((driver) => (
                  <li key={driver}>{driver}</li>
                ))}
              </ul>
              <div className="confidence-line">
                <span>Confidence</span>
                <strong>{narrative.confidence}</strong>
                {syncedAt && <span className="sync-age">Updated {syncAge}</span>}
              </div>
            </section>

            {riskEvents.data.features.length > 0 && (
              <section className="alert-list">
                <div className="alert-list-label">
                  <AlertTriangle size={13} aria-hidden />
                  <span>Pressure signals</span>
                </div>
                {visibleRiskSignals.map((f) => {
                  const p = f.properties;
                  const id = String((f as unknown as { id?: unknown }).id ?? "");
                  const isSelected = selectedRiskEventId === id;
                  return (
                    <button
                      key={id}
                      className={`alert-row${isSelected ? " is-selected" : ""}`}
                      onClick={() =>
                        handleFeatureClick(f as { id?: unknown; properties?: Record<string, unknown> })
                      }
                    >
                      <span className="alert-row-type">{String(p.event_type ?? "")}</span>
                      <span className={`alert-row-sev alert-row-sev--${String(p.severity ?? "").toLowerCase()}`}>
                        {String(p.severity ?? "")}
                      </span>
                    </button>
                  );
                })}
                {hiddenRiskSignalCount > 0 && (
                  <button
                    type="button"
                    className="signal-reveal"
                    onClick={() => setSignalsExpanded((e) => !e)}
                  >
                    {signalsExpanded
                      ? "Show fewer signals"
                      : `View all signals (${riskEvents.data.features.length})`}
                  </button>
                )}
              </section>
            )}

            {selectedFeature && (
              <section className="impact-summary">
                <div className="impact-summary-label">
                  {selectedType === "risk_event" ? (
                    <AlertTriangle size={13} aria-hidden />
                  ) : (
                    <MapPinned size={13} aria-hidden />
                  )}
                  <span>{titleize(selectedType ?? "entity")}</span>
                  <button
                    className="impact-summary-close"
                    onClick={() => {
                      setSelectedFeature(null);
                      setSelectedRiskEventId(null);
                    }}
                    aria-label="Dismiss"
                  >
                    <X size={12} />
                  </button>
                </div>
                <strong>{selectedName}</strong>
                {Boolean(selectedFeature.properties.subtype) && (
                  <span>{titleize(selectedFeature.properties.subtype)}</span>
                )}
                {Boolean(selectedFeature.properties.severity) && (
                  <span>Severity: {String(selectedFeature.properties.severity)}</span>
                )}
                {Boolean(selectedFeature.properties.area_desc) && (
                  <span>{String(selectedFeature.properties.area_desc)}</span>
                )}
                {selectedFeature.properties.at_risk != null && (
                  <span style={{ color: selectedFeature.properties.at_risk ? "#dc3c32" : "#1e82b4" }}>
                    {selectedFeature.properties.at_risk
                      ? `⚠ At risk · ${selectedFeature.properties.active_alert_count} active alert(s)`
                      : "Normal — no active alerts within 5 km"}
                  </span>
                )}
                {selectedRiskEventId && (
                  <>
                    <strong>{riskImpacts.data.features.length.toLocaleString()} linked assets</strong>
                    <span>
                      {riskImpacts.loading ? "Loading impact network…" : "Stored risk_impacts edges"}
                    </span>
                  </>
                )}
              </section>
            )}

            <section className="chat-panel">
              <div className="chat-panel-label">
                <MessageSquare size={13} aria-hidden />
                <span>{modePrompts[mode]}</span>
              </div>

              <div className="chat-messages">
                {chatMessages.length === 0 && (
                  <div className="chat-empty">
                    Try "Show vulnerabilities in food imports to NYC" or "What happens if Newark
                    port slows for 48 hours?"
                  </div>
                )}
                {chatMessages.map((msg, i) => (
                  <div key={i} className={`chat-bubble chat-bubble--${msg.role}`}>
                    {msg.content}
                  </div>
                ))}
                {chatLoading && (
                  <div className="chat-bubble chat-bubble--assistant chat-bubble--thinking">
                    Thinking…
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>

              {chatToolResult && chatToolResult.count > 0 && (
                <div className="chat-result-badge">
                  {chatToolResult.count.toLocaleString()} results on map ·{" "}
                  {chatToolResult.tool.replace(/_/g, " ")}
                </div>
              )}

              <div className="chat-input-row">
                <input
                  className="chat-input"
                  type="text"
                  placeholder="Ask the network..."
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      sendChat();
                    }
                  }}
                  disabled={chatLoading}
                />
                <button
                  className="chat-send"
                  onClick={sendChat}
                  disabled={chatLoading || chatInput.trim().length === 0}
                  aria-label="Send"
                >
                  <Send size={14} />
                </button>
              </div>
            </section>
          </>
        )}
      </aside>

      <footer>
        Map data © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>
      </footer>
    </main>
  );
}
