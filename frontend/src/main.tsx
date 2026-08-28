import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { Activity, CheckCircle2, Circle, Cpu, FileUp, Play, Send, Terminal, XCircle } from "lucide-react";
import { createRun, fetchOllamaStatus, fetchRun, Observation, OllamaStatus, PlanNode, TraceRun, UploadedFile, uploadFile } from "./api/client";
import "./styles.css";

const defaultTask =
  "修复 demo_project 中失败的测试。请先阅读相关文件，运行测试，定位问题，做最小修改，然后再次运行测试。";

const statusText: Record<TraceRun["status"] | "idle", string> = {
  idle: "未开始",
  created: "已创建",
  running: "执行中",
  success: "已完成",
  failed: "失败"
};

const nodeStatusText: Record<PlanNode["status"], string> = {
  pending: "等待中",
  running: "执行中",
  success: "已完成",
  failed: "失败",
  revised: "已修订"
};

const toolText: Record<string, string> = {
  list_files: "列出文件",
  read_file: "读取文件",
  write_file: "写入文件",
  run_command: "执行命令",
  final_guard: "最终检查"
};

function StatusIcon({ status }: { status: PlanNode["status"] }) {
  if (status === "success") return <CheckCircle2 className="statusIcon success" size={18} />;
  if (status === "failed") return <XCircle className="statusIcon failed" size={18} />;
  if (status === "running") return <Activity className="statusIcon running" size={18} />;
  return <Circle className="statusIcon pending" size={18} />;
}

function PlanTimeline({ nodes }: { nodes: PlanNode[] }) {
  if (nodes.length === 0) {
    return <div className="empty">提交任务后，智能体会先生成计划节点；每个节点的状态会随着执行实时变化。</div>;
  }
  return (
    <div className="timeline">
      {nodes.map((node) => (
        <article className="node" key={node.id}>
          <StatusIcon status={node.status} />
          <div>
            <div className="nodeLine">
              <div className="nodeTitle">{node.title}</div>
              <span className={`nodeBadge ${node.status}`}>{nodeStatusText[node.status]}</span>
            </div>
            <div className="nodeMeta">节点 ID：{node.id}</div>
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
  const path = observation.data.path as string | undefined;
  const exitCode = observation.data.exit_code as number | undefined;
  const blockedReport = observation.data.blocked_report as string | undefined;
  const failureHint = useMemo(() => {
    const text = `${stdout ?? ""}\n${stderr ?? ""}`;
    const moduleError = text.match(/ModuleNotFoundError: No module named '([^']+)'/);
    if (moduleError) return `导入失败：找不到模块 ${moduleError[1]}`;
    const assertion = text.match(/E\s+assert .+/);
    if (assertion) return assertion[0].replace(/^E\s+/, "断言失败：");
    if (!observation.ok && exitCode !== undefined) return `命令失败，退出码 ${exitCode}`;
    return null;
  }, [exitCode, observation.ok, stderr, stdout]);

  return (
    <article className={`observation ${observation.ok ? "ok" : "bad"}`}>
      <div className="obsHeader">
        <span>{toolText[observation.tool] ?? observation.tool}</span>
        <span>绑定节点：{observation.node_id}</span>
      </div>
      <p>{observation.summary}</p>
      {failureHint ? <div className="failureHint">{failureHint}</div> : null}
      {path ? <div className="fieldLine">文件：<code>{path}</code></div> : null}
      {typeof exitCode === "number" ? <div className="fieldLine">退出码：<code>{exitCode}</code></div> : null}
      {blockedReport ? <div className="guardBox">被拦截的报告：{blockedReport}</div> : null}
      {command ? <code className="command">{command}</code> : null}
      {content ? <pre aria-label="文件内容">{content}</pre> : null}
      {stdout ? <pre aria-label="标准输出">{stdout}</pre> : null}
      {stderr ? <pre aria-label="错误输出">{stderr}</pre> : null}
    </article>
  );
}

function App() {
  const [task, setTask] = useState(defaultTask);
  const [runId, setRunId] = useState<string | null>(null);
  const [run, setRun] = useState<TraceRun | null>(null);
  const [ollama, setOllama] = useState<OllamaStatus | null>(null);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [isUploading, setIsUploading] = useState(false);

  const newestObservation = useMemo(() => {
    const observations = run?.observations ?? [];
    return observations.length > 0 ? observations[observations.length - 1] : undefined;
  }, [run]);

  const completedNodes = useMemo(() => {
    return (run?.plan ?? []).filter((node) => node.status === "success").length;
  }, [run]);

  const evidence = useMemo(() => {
    const observations = run?.observations ?? [];
    return {
      commands: observations.filter((observation) => observation.tool === "run_command").length,
      writes: observations.filter((observation) => observation.tool === "write_file").length,
      blocked: observations.some((observation) => observation.tool === "final_guard")
    };
  }, [run]);

  useEffect(() => {
    void fetchOllamaStatus().then(setOllama).catch((err: Error) => setError(err.message));
  }, []);

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

  async function handleUpload(fileList: FileList | null) {
    const file = fileList?.[0];
    if (!file) return;
    setIsUploading(true);
    setError(null);
    try {
      const uploaded = await uploadFile(file);
      setUploadedFiles((files) => [uploaded, ...files]);
      setTask((current) => `${current}\n\n可参考上传文件：${uploaded.path}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <main>
      <header className="hero">
        <div>
          <h1>TraceCoder</h1>
          <p>把一次代码修复任务拆成计划图，逐步执行工具，并把每一步证据留在页面上。</p>
        </div>
        <div className={`runStatus ${run?.status ?? "idle"}`}>{statusText[run?.status ?? "idle"]}</div>
      </header>

      <section className="taskPanel">
        <div className="sectionHeader">
          <FileUp size={18} />
          <h2>输入任务和材料</h2>
        </div>
        <textarea aria-label="任务内容" value={task} onChange={(event) => setTask(event.target.value)} />
        <div className="taskActions">
          <label className="uploadButton">
            <FileUp size={18} />
            <span>{isUploading ? "上传中" : "上传文件"}</span>
            <input type="file" onChange={(event) => void handleUpload(event.target.files)} disabled={isUploading} />
          </label>
          <button onClick={startRun} disabled={isStarting || !task.trim()} title="开始执行任务">
            {isStarting ? <Play size={18} /> : <Send size={18} />}
            <span>{isStarting ? "正在创建" : "开始执行"}</span>
          </button>
        </div>
      </section>

      {uploadedFiles.length > 0 ? (
        <section className="uploadList">
          {uploadedFiles.map((file) => (
            <div key={file.path}>
              <strong>{file.filename}</strong>
              <span>{file.path} · {file.size} bytes</span>
            </div>
          ))}
        </section>
      ) : null}

      <section className="summaryBand">
        <div>
          <span>当前任务</span>
          <strong>{run?.task ?? "尚未开始执行"}</strong>
        </div>
        <div>
          <span>计划进度</span>
          <strong>{completedNodes}/{run?.plan.length ?? 0}</strong>
        </div>
        <div>
          <span>工具观察</span>
          <strong>{run?.observations.length ?? 0}</strong>
        </div>
        <div>
          <span>证据状态</span>
          <strong>{evidence.blocked ? "证据不足" : `${evidence.commands} 命令 / ${evidence.writes} 修改`}</strong>
        </div>
      </section>

      {error ? <div className="error">{error}</div> : null}

      <div className="grid">
        <section>
          <div className="sectionHeader">
            <Activity size={18} />
            <h2>计划图</h2>
          </div>
          <PlanTimeline nodes={run?.plan ?? []} />
        </section>

        <section>
          <div className="sectionHeader">
            <Terminal size={18} />
            <h2>当前证据</h2>
          </div>
          {newestObservation ? <ObservationCard observation={newestObservation} /> : <div className="empty">智能体执行读取文件、写入文件或运行命令后，这里会显示最新结果。</div>}

          <div className="runtimePanel">
            <div className="sectionHeader">
              <Cpu size={18} />
              <h2>本地模型</h2>
            </div>
            <div className="runtimeRows">
              <div><span>服务</span><strong>{ollama?.base_url ?? "检测中"}</strong></div>
              <div><span>模型</span><strong>{ollama?.selected_model ?? "未选择"}</strong></div>
              <div><span>状态</span><strong>{ollama?.error ?? "可用"}</strong></div>
            </div>
          </div>
        </section>
      </div>

      <section>
        <div className="sectionHeader">
          <CheckCircle2 size={18} />
          <h2>完整执行记录</h2>
        </div>
        <div className="observations">
          {(run?.observations ?? []).length > 0 ? (
            (run?.observations ?? []).map((observation, index) => (
              <ObservationCard key={`${observation.created_at}-${index}`} observation={observation} />
            ))
          ) : (
            <div className="empty">暂无工具调用记录。</div>
          )}
        </div>
      </section>

      <section>
        <div className="sectionHeader">
          <CheckCircle2 size={18} />
          <h2>最终报告</h2>
        </div>
        <div className="report">{run?.final_report ?? "任务结束后，这里会总结修改内容、验证结果和剩余风险。"}</div>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
