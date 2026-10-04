import React, { useCallback, useEffect, useRef, useState } from "react";
import { Moon, ShieldCheck, Sun } from "lucide-react";
import { api } from "./api";
import { Banner, Button, ErrorBoundary, PageHeader, Spinner, StateCard } from "./ui";
import { fmt, setDisplayZone, zoneLabel } from "./labels";
import { AnalysisState, needsAnalysis } from "./components/AnalysisState";
import { CampaignPanel } from "./components/CampaignPanel";
import { DatasetsView } from "./views/DatasetsView";
import { OverviewView } from "./views/OverviewView";
import { NetworkView } from "./views/NetworkView";
import { PostsView } from "./views/PostsView";
import { BriefView } from "./views/BriefView";

const VIEWS = [
  { id: "datasets", label: "Datasets" },
  { id: "overview", label: "Overview" },
  { id: "network", label: "Network" },
  { id: "posts", label: "Posts" },
  { id: "brief", label: "Brief" },
];
const EMPTY = { campaigns: null, graph: null, timeline: null, stats: null };

function getInitialTheme() {
  try {
    const saved = localStorage.getItem("theme");
    if (saved === "dark" || saved === "light") return saved;
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  } catch (_) {
    return "light";
  }
}

// Location is kept in the URL (#/view/dataset/campaign) so a reload or a shared link opens the same place
function readHash() {
  const [view, datasetId, campaignId] = window.location.hash
    .replace(/^#\/?/, "")
    .split("/");
  return {
    view: VIEWS.some((v) => v.id === view) ? view : "overview",
    datasetId: datasetId || null,
    campaignId: campaignId || null,
  };
}

export default function App() {
  const [theme, setTheme] = useState(getInitialTheme);
  const [view, setView] = useState(() => readHash().view);
  const [datasetId, setDatasetId] = useState(() => readHash().datasetId);
  const [datasets, setDatasets] = useState(null); // null while loading
  const [bobConfigured, setBobConfigured] = useState(false);
  const [xConfigured, setXConfigured] = useState(false);
  const [data, setData] = useState(EMPTY);
  const [selectedId, setSelectedId] = useState(null);
  const [error, setError] = useState(null);
  const [postFilter, setPostFilter] = useState({}); // Posts view: search words and filters
  const wantedCampaign = useRef(readHash().campaignId); // from the URL, applied once results load

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    document.documentElement.classList.toggle("dark", theme === "dark");
    try {
      localStorage.setItem("theme", theme);
    } catch (_) {}
  }, [theme]);

  const toggleTheme = () => setTheme((t) => (t === "dark" ? "light" : "dark"));

  // state → URL (adds a history entry, so Back works) and URL → state (Back/Forward, edited links)
  useEffect(() => {
    const hash = `#/${view}/${datasetId ?? ""}${selectedId && view !== "datasets" ? `/${selectedId}` : ""}`;
    if (window.location.hash !== hash) window.location.hash = hash;
  }, [view, datasetId, selectedId]);
  useEffect(() => {
    const onHashChange = () => {
      const h = readHash();
      setView(h.view);
      if (h.datasetId) setDatasetId(h.datasetId);
      if (h.campaignId) setSelectedId(h.campaignId);
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const refreshDatasets = useCallback(async () => {
    try {
      const ds = await api.datasets();
      setDatasets(ds);
      return ds;
    } catch (e) {
      setError(
        `Can't reach the analysis server (${e.message}). Is "python src/main.py" running?`,
      );
      return null;
    }
  }, []);

  useEffect(() => {
    api
      .status()
      .then((s) => {
        setBobConfigured(s.bob_configured);
        setXConfigured(s.x_configured);
      })
      .catch(() => {});
    refreshDatasets().then((ds) => {
      if (ds && (!datasetId || !ds.some((d) => d.id === datasetId))) {
        const delhi = ds.find((d) => d.id === "u_52239f" || d.name?.toLowerCase().includes("delhi"));
        setDatasetId(delhi?.id ?? ds[0]?.id ?? null);
      }
      if (ds && ds.length === 0) setView("datasets"); // first run: nothing to show until data comes in
    });
  }, []);

  const dataset = datasets?.find((d) => d.id === datasetId);
  setDisplayZone(dataset?.timezone); // every time shown is in the dataset's own clock
  const anyRunning = datasets?.some((d) => d.job?.state === "running");

  // Poll while any analysis runs, so progress and the finished state show up by themselves
  useEffect(() => {
    if (!anyRunning) return;
    const timer = setInterval(refreshDatasets, 1500);
    return () => clearInterval(timer);
  }, [anyRunning, refreshDatasets]);

  // Load results when the dataset changes or an analysis of it finishes
  const resultsKey =
    dataset && !needsAnalysis(dataset)
      ? `${dataset.id}:${dataset.job?.finished ?? ""}`
      : null;
  useEffect(() => setPostFilter({}), [datasetId]);
  useEffect(() => {
    setData(EMPTY);
    setSelectedId(null);
    if (!resultsKey) return;
    let cancelled = false;
    Promise.all([
      api.campaigns(dataset.id),
      api.graph(dataset.id),
      api.timeline(dataset.id),
      api.stats(dataset.id).catch(() => null),
    ])
      .then(([campaigns, graph, timeline, stats]) => {
        if (cancelled) return;
        setData({ campaigns, graph, timeline, stats });
        const wanted = campaigns.find((c) => c.id === wantedCampaign.current);
        wantedCampaign.current = null;
        // start on the highest-priority campaign: urgent first, then the top-scored (c1)
        const urgent = campaigns.find((c) => c.assessment?.level === 'URGENT');
        setSelectedId(wanted?.id ?? urgent?.id ?? campaigns[0]?.id ?? null);
      })
      .catch(
        (e) =>
          !cancelled &&
          setError(
            `Couldn't load the results for ${dataset.name}: ${e.message}`,
          ),
      );
    return () => {
      cancelled = true;
    };
  }, [resultsKey]);

  // Any account, hashtag, town or campaign link opens the Posts view filtered to it
  const openPosts = (filter) => {
    setPostFilter(filter);
    setView("posts");
  };

  const openDataset = (id, nextView = "overview") => {
    setDatasetId(id);
    setView(nextView);
  };

  const analyse = async (id) => {
    setError(null);
    try {
      await api.analyze(id);
      await refreshDatasets();
    } catch (e) {
      setError(`Could not start the analysis: ${e.message}`);
    }
  };

  // A new dataset (upload, column choice, X search) is analysed at once and opened
  const analyseAndOpen = async (id) => {
    await api.analyze(id);
    await refreshDatasets();
    openDataset(id);
  };

  const upload = async (file) => {
    const res = await api.upload(file); // errors (e.g. not X API v2 JSON) are shown in the upload card
    await analyseAndOpen(res.dataset_id);
  };

  const xSearch = async (query, max) => {
    const res = await api.xSearch(query, max);
    await analyseAndOpen(res.dataset_id);
  };

  const remove = async (d) => {
    if (
      !window.confirm(
        `Delete "${d.name}" and its analysis results? This cannot be undone.`,
      )
    )
      return;
    try {
      await api.remove(d.id);
      const ds = await refreshDatasets();
      if (d.id === datasetId) setDatasetId(ds?.[0]?.id ?? null);
    } catch (e) {
      setError(`Could not delete ${d.name}: ${e.message}`);
    }
  };

  // An IBM Bob assessment changes the campaign list badges and the brief
  const onAssessed = (cid, assessment) =>
    setData((prev) => ({
      ...prev,
      campaigns: prev.campaigns.map((c) =>
        c.id === cid ? { ...c, assessment } : c,
      ),
    }));

  const assessedCount = data.campaigns?.filter((c) => c.assessment).length ?? 0;
  const panel = dataset && (
    <CampaignPanel
      datasetId={dataset.id}
      campaignId={selectedId}
      bobConfigured={bobConfigured}
      onAssessed={onAssessed}
      onFilter={openPosts}
    />
  );

  const renderDatasetPage = () => {
    if (!dataset)
      return datasets?.length ? (
        <StateCard title="Dataset not found"
          action={<Button variant="primary" onClick={() => { refreshDatasets(); setView("datasets"); }}>Go to Datasets</Button>}>
          This link points to a dataset that isn't on this server (it may have been deleted).
        </StateCard>
      ) : null;
    const title = {
      overview: dataset.name,
      network: "Network",
      posts: "Posts",
      brief: "Threat brief",
    }[view];
    const subtitle = view === "overview" && dataset.description
      ? `${dataset.description} Times in ${zoneLabel()}.`
      : `${fmt(dataset.posts)} posts · ${fmt(dataset.accounts)} accounts${data.campaigns ? ` · ${data.campaigns.length} campaigns` : ""} · times in ${zoneLabel()}`;
    const rerun = dataset.analyzed &&
      !needsAnalysis(dataset) &&
      view === "overview" && (
        <Button onClick={() => analyse(dataset.id)}>Re-run analysis</Button>
      );

    let body;
    if (needsAnalysis(dataset))
      body = <AnalysisState dataset={dataset} onAnalyze={analyse} />;
    else if (!data.campaigns)
      body = (
        <div className="flex items-center justify-center gap-2 py-24 text-sm text-muted">
          <Spinner />
          Loading results…
        </div>
      );
    else if (view === "overview")
      body = (
        <OverviewView
          dataset={dataset}
          data={data}
          selectedId={selectedId}
          onSelect={setSelectedId}
          panel={panel}
        />
      );
    else if (view === "network")
      body = (
        <NetworkView
          datasetId={dataset?.id}
          data={data}
          selectedId={selectedId}
          onSelect={setSelectedId}
          panel={panel}
          theme={theme}
          onOpenPosts={openPosts}
        />
      );
    else if (view === "posts")
      body = <PostsView datasetId={dataset.id} filter={postFilter} onFilter={setPostFilter} campaigns={data.campaigns} />;
    else
      body = (
        <BriefView
          key={`${dataset.id}-${assessedCount}`}
          dataset={dataset}
          campaigns={data.campaigns}
          timeline={data.timeline}
          stats={data.stats}
          bobConfigured={bobConfigured}
          onAssessed={onAssessed}
          onFilter={openPosts}
          selectedCampaignId={selectedId}
          onSelectCampaign={setSelectedId}
          url={`${api.briefUrl(dataset.id)}?v=${assessedCount}`}
        />
      );

    return (
      <>
        {view !== "posts" && view !== "brief" && <PageHeader title={title} subtitle={subtitle} action={rerun} />}
        {body}
      </>
    );
  };

  return (
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-20 bg-surface border-b border-line">
        <div className="max-w-[1440px] mx-auto px-4 lg:px-6 min-h-14 py-2 flex flex-wrap items-center gap-x-6 gap-y-2">
          <div className="flex items-center gap-2 font-semibold">
            <ShieldCheck className="w-5 h-5 text-accent" aria-hidden />
            Social-Threat Intel Engine
          </div>
          <nav className="flex items-center gap-1" aria-label="Pages">
            {VIEWS.map((v) => (
              <button
                key={v.id}
                onClick={() => setView(v.id)}
                aria-current={view === v.id ? "page" : undefined}
                className={`h-8 px-3 rounded-md text-sm cursor-pointer transition-colors ${view === v.id ? "bg-subtle text-ink font-medium" : "text-muted hover:text-ink"}`}
              >
                {v.label}
              </button>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            {datasets && datasets.length > 0 && (
              <label className="flex items-center gap-2 text-xs text-muted">
                Dataset
                <select
                  value={datasetId ?? ""}
                  onChange={(e) => setDatasetId(e.target.value)}
                  className="h-8 max-w-[260px] rounded-md border border-line bg-surface text-ink text-sm px-2 cursor-pointer"
                >
                  {datasets.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                      {d.job?.state === "running"
                        ? " — analysing…"
                        : d.analyzed
                          ? ""
                          : " — not analysed"}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <span
              className="flex items-center gap-1.5 text-xs text-muted"
              title={
                bobConfigured
                  ? "Bob Shell and BOB_API_KEY are ready for live assessments"
                  : "Live assessments require Bob Shell and BOB_API_KEY"
              }
            >
              <span
                className={`w-2 h-2 rounded-full ${bobConfigured ? "bg-benign" : "bg-faint"}`}
              />
              {bobConfigured ? "IBM Bob ready" : "IBM Bob: saved results only"}
            </span>
            <button
              type="button"
              onClick={toggleTheme}
              className="inline-flex items-center justify-center w-8 h-8 rounded-md border border-line bg-surface text-ink hover:bg-subtle transition-colors cursor-pointer"
              title={
                theme === "dark"
                  ? "Switch to light mode"
                  : "Switch to dark mode"
              }
              aria-label={
                theme === "dark"
                  ? "Switch to light mode"
                  : "Switch to dark mode"
              }
            >
              {theme === "dark" ? (
                <Sun className="w-4 h-4 text-alert" />
              ) : (
                <Moon className="w-4 h-4 text-muted" />
              )}
            </button>
          </div>
        </div>
      </header>

      <main className="flex-1 w-full max-w-[1440px] mx-auto px-4 lg:px-6 py-6">
        {error && (
          <div className="mb-4">
            <Banner onClose={() => setError(null)}>{error}</Banner>
          </div>
        )}
        {datasets === null && !error && (
          <div className="flex items-center justify-center gap-2 py-24 text-sm text-muted">
            <Spinner />
            Connecting…
          </div>
        )}
        {datasets && view === "datasets" && (
          <DatasetsView
            datasets={datasets}
            currentId={datasetId}
            onOpen={(id) => openDataset(id)}
            onAnalyze={(id) => {
              analyse(id);
              openDataset(id);
            }}
            onDelete={remove}
            onUpload={upload}
            onXSearch={xSearch}
            xConfigured={xConfigured}
          />
        )}
        {datasets?.length === 0 && view !== "datasets" && (
          <StateCard title="No datasets yet"
            action={<Button variant="primary" onClick={() => setView("datasets")}>Add a dataset</Button>}>
            Upload X API v2 JSON (search, timeline or filtered-stream output, as the API returned it) or search X, and the analysis starts by itself.
          </StateCard>
        )}
        <ErrorBoundary resetKey={`${view}:${datasetId}`}>
          {datasets && view !== "datasets" && renderDatasetPage()}
        </ErrorBoundary>
      </main>

      <footer className="border-t border-line py-3 text-center text-xs text-faint">
        Decision support only. Legal sections are suggestions to be verified by
        a legal officer.
      </footer>
    </div>
  );
}
