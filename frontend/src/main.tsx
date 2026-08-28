import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { Activity, CheckCircle2, Circle, Play, Send, Terminal, XCircle } from "lucide-react";
import { createRun, fetchRun, Observation, PlanNode, TraceRun } from "./api/client";
import "./styles.css";

const defaultTask =
  "Fix the failing tests in demo_project. Read the files, run pytest, make the smallest fix, then run tests again.";

function StatusIcon({ status }: { status: PlanNode["status"] }) {
  if (status === "success") return <CheckCircle2 className="statusIcon success" size={18} />;
  if (status === "failed") return <XCircle className="statusIcon failed" size={18} />;
  if (status === "running") return <Activity className="statusIcon running" size={18} />;
  return <Circle className="statusIcon pending" size={18} />;
}

function PlanTimeline({ nodes }: { nodes: PlanNode[] }) {
  if (nodes.length === 0) {
    return <div className="empty">No plan yet. The first model action should create one.</div>;
  }
  return (
    <div className="timeline">
      {nodes.map((node) => (
        <article className="node" key={node.id}>
          <StatusIcon status={node.status} />
          <div>
            <div className="nodeTitle">{node.title}</div>
            <div className="nodeMeta">{node.id}</div>
            {node.detail ? <p>{node.detail}</p> : null}
          </div>
        </article>
      ))}
    </div>
  );
}

function ObservationCard({ observation }: { observation: Observation }) {
  const command = observation.data.command as string | undefined;
  const stdout = observation.data.stdout as string | undefined;
  const stderr = observation.data.stderr as string | undefined;
  const content = observation.data.content as string | undefined;

  return (
    <article className={`observation ${observation.ok ? "ok" : "bad"}`}>
      <div className="obsHeader">
        <span>{observation.tool}</span>
        <span>{observation.node_id}</span>
      </div>
      <p>{observation.summary}</p>
      {command ? <code className="command">{command}</code> : null}
      {content ? <pre>{content}</pre> : null}
      {stdout ? <pre>{stdout}</pre> : null}
      {stderr ? <pre>{stderr}</pre> : null}
    </article>
  );
}

function App() {
  const [task, setTask] = useState(defaultTask);
  const [runId, setRunId] = useState<string | null>(null);
  const [run, setRun] = useState<TraceRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState(false);

  const newestObservation = useMemo(() => run?.observations.at(-1), [run]);

  useEffect(() => {
    if (!runId) return;
    void fetchRun(runId).then(setRun).catch((err: Error) => setError(err.message));
    const source = new EventSource(`/api/runs/${runId}/events`);
    source.onmessage = () => {
      void fetchRun(runId).then(setRun).catch((err: Error) => setError(err.message));
    };
    ["created", "status", "action", "plan_updated", "observation", "final"].forEach((eventName) => {
      source.addEventListener(eventName, () => {
        void fetchRun(runId).then(setRun).catch((err: Error) => setError(err.message));
      });
    });
    source.onerror = () => source.close();
    return () => source.close();
  }, [runId]);

  async function startRun() {
    setIsStarting(true);
    setError(null);
    setRun(null);
    try {
      const id = await createRun(task);
      setRunId(id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIsStarting(false);
    }
  }

  return (
    <main>
      <header className="topbar">
        <div>
          <h1>TraceCoder</h1>
          <p>Local Ollama coding agent with a visible plan graph trace.</p>
        </div>
        <div className={`runStatus ${run?.status ?? "created"}`}>{run?.status ?? "idle"}</div>
      </header>

      <section className="taskBand">
        <textarea value={task} onChange={(event) => setTask(event.target.value)} />
        <button onClick={startRun} disabled={isStarting || !task.trim()} title="Start run">
          {isStarting ? <Play size={18} /> : <Send size={18} />}
          <span>{isStarting ? "Starting" : "Run Task"}</span>
        </button>
      </section>

      {error ? <div className="error">{error}</div> : null}

      <div className="grid">
        <section>
          <div className="sectionHeader">
            <Activity size={18} />
            <h2>Plan Graph</h2>
          </div>
          <PlanTimeline nodes={run?.plan ?? []} />
        </section>

        <section>
          <div className="sectionHeader">
            <Terminal size={18} />
            <h2>Latest Tool Output</h2>
          </div>
          {newestObservation ? <ObservationCard observation={newestObservation} /> : <div className="empty">No tool output yet.</div>}
        </section>
      </div>

      <section>
        <div className="sectionHeader">
          <CheckCircle2 size={18} />
          <h2>Trace Details</h2>
        </div>
        <div className="observations">
          {(run?.observations ?? []).map((observation, index) => (
            <ObservationCard key={`${observation.created_at}-${index}`} observation={observation} />
          ))}
        </div>
      </section>

      <section>
        <div className="sectionHeader">
          <CheckCircle2 size={18} />
          <h2>Final Report</h2>
        </div>
        <div className="report">{run?.final_report ?? "Waiting for completion."}</div>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

