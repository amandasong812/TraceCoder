import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { Activity, CheckCircle2, Circle, Cpu, FileUp, Play, Send, Terminal, Trash2, XCircle } from "lucide-react";
import {
  cancelRun,
  createRun,
  deleteUploadedFile,
  fetchOllamaStatus,
  fetchRun,
  fetchRuns,
  Observation,
  OllamaStatus,
  PlanNode,
  RunSummary,
  TraceEvent,
  TraceRun,
  UploadedFile,
  uploadFile
} from "./api/client";
import "./styles.css";

const statusText: Record<TraceRun["status"] | "idle", string> = {
  idle: "未开始",
  created: "已创建",
  running: "执行中",
  success: "已完成",
  failed: "已失败"
};

const nodeStatusText: Record<PlanNode["status"], string> = {
  pending: "等待中",
  running: "执行中",
  success: "已完成",
  failed: "已失败",
  revised: "已修订"
};

const toolText: Record<string, string> = {
  list_files: "列出文件",
  read_file: "读取文件",
  write_file: "写入文件",
  run_command: "执行命令",
  final_guard: "最终检查"
};

type ChatRole = "user" | "agent" | "tool" | "error";
type RichBlock =
  | { type: "heading"; level: number; text: string }
  | { type: "paragraph"; text: string }
  | { type: "code"; text: string }
  | { type: "list"; items: string[] };

function StatusIcon({ status }: { status: PlanNode["status"] }) {
  if (status === "success") return <CheckCircle2 className="statusIcon success" size={18} />;
  if (status === "failed") return <XCircle className="statusIcon failed" size={18} />;
  if (status === "running") return <Activity className="statusIcon running" size={18} />;
  return <Circle className="statusIcon pending" size={18} />;
}

function PlanTimeline({ nodes }: { nodes: PlanNode[] }) {
  if (nodes.length === 0) {
    return <div className="empty">提交任务后，智能体会先生成计划节点；节点状态会随执行实时变化。</div>;
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
        <span>节点：{observation.node_id}</span>
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

function splitInlinePython(text: string): RichBlock[] | null {
  const codeStart = text.indexOf("class ");
  if (codeStart < 0 || !text.includes(" def ")) return null;
  const markerCandidates = ["思路", "复杂度", "说明", "解释"].map((marker) => text.indexOf(marker, codeStart + 1)).filter((index) => index > 0);
  const codeEnd = markerCandidates.length > 0 ? Math.min(...markerCandidates) : text.length;
  const before = text.slice(0, codeStart).trim();
  const code = text
    .slice(codeStart, codeEnd)
    .trim()
    .replace(/\s+(class\s+)/g, "\n$1")
    .replace(/\s+(def\s+)/g, "\n    $1")
    .replace(/\s+(if\s+)/g, "\n        $1")
    .replace(/\s+(elif\s+)/g, "\n        $1")
    .replace(/\s+(else:)/g, "\n        $1")
    .replace(/\s+(for\s+)/g, "\n        $1")
    .replace(/\s+(while\s+)/g, "\n        $1")
    .replace(/\s+(return\b)/g, "\n            $1");
  const after = text.slice(codeEnd).trim();
  return [
    ...(before ? [{ type: "paragraph" as const, text: before }] : []),
    { type: "code" as const, text: code },
    ...(after ? plainTextBlocks(after) : [])
  ];
}

function plainTextBlocks(text: string): RichBlock[] {
  const inlinePython = splitInlinePython(text);
  if (inlinePython) return inlinePython;

  const blocks: RichBlock[] = [];
  let paragraph: string[] = [];
  let list: string[] = [];
  let code: string[] = [];
  const flushParagraph = () => {
    if (paragraph.length) blocks.push({ type: "paragraph", text: paragraph.join("\n") });
    paragraph = [];
  };
  const flushList = () => {
    if (list.length) blocks.push({ type: "list", items: list });
    list = [];
  };
  const flushCode = () => {
    if (code.length) blocks.push({ type: "code", text: code.join("\n") });
    code = [];
  };
  const codeLike = (line: string) => /^\s*(class |def |for |if |elif |else:|while |return\b|import |from |\w+\s*=|[\])}])/.test(line);

  for (const line of text.replace(/\r\n/g, "\n").split("\n")) {
    if (!line.trim()) {
      flushCode();
      flushList();
      flushParagraph();
      continue;
    }
    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      flushCode();
      flushList();
      flushParagraph();
      blocks.push({ type: "heading", level: heading[1].length, text: heading[2] });
      continue;
    }
    const bullet = line.match(/^\s*(?:[-*]|\d+\.)\s+(.+)$/);
    if (bullet) {
      flushCode();
      flushParagraph();
      list.push(bullet[1]);
      continue;
    }
    if (codeLike(line)) {
      flushList();
      flushParagraph();
      code.push(line);
      continue;
    }
    flushCode();
    flushList();
    paragraph.push(line);
  }
  flushCode();
  flushList();
  flushParagraph();
  return blocks;
}

function richBlocks(text: string): RichBlock[] {
  const parts = text.split(/(```[\s\S]*?```)/g).filter(Boolean);
  return parts.flatMap((part) => {
    if (part.startsWith("```")) {
      return [{ type: "code" as const, text: part.replace(/^```[a-zA-Z0-9_-]*\n?/, "").replace(/```$/, "").trim() }];
    }
    return plainTextBlocks(part.trim());
  });
}

function RichText({ text }: { text: string }) {
  const blocks = useMemo(() => richBlocks(text), [text]);
  return (
    <div className="richText">
      {blocks.map((block, index) => {
        if (block.type === "code") return <pre key={index}>{block.text}</pre>;
        if (block.type === "list") return <ul key={index}>{block.items.map((item) => <li key={item}>{item}</li>)}</ul>;
        if (block.type === "heading") {
          if (block.level === 1) return <h1 key={index}>{block.text}</h1>;
          if (block.level === 2) return <h2 key={index}>{block.text}</h2>;
          return <h3 key={index}>{block.text}</h3>;
        }
        return <p key={index}>{block.text}</p>;
      })}
    </div>
  );
}

function actionSummary(event: TraceEvent) {
  const action = event.payload.action as Record<string, unknown> | undefined;
  if (!action) return "模型返回了一个动作。";
  if (action.kind === "plan") return "模型生成或修订了计划图。";
  if (action.kind === "final") return "模型尝试给出最终回复。";
  const toolCall = action.tool_call as Record<string, unknown> | undefined;
  return `模型决定调用工具：${toolText[String(toolCall?.tool)] ?? String(toolCall?.tool ?? "unknown")}，绑定节点 ${String(toolCall?.node_id ?? "unknown")}。`;
}

function eventTitle(event: TraceEvent) {
  const titles: Record<string, string> = {
    context_built: "上下文窗口",
    model_output: "模型原始输出",
    action: "结构化动作",
    policy_blocked: "策略拦截",
    final_blocked: "最终报告拦截",
    parse_error: "解析失败",
    cancelled: "任务停止",
    error: "运行错误"
  };
  return titles[event.type] ?? event.type;
}

function eventBody(event: TraceEvent) {
  if (event.type === "context_built") {
    return [
      `任务类型：${String((event.payload.workflow as Record<string, unknown> | undefined)?.task_kind ?? "unknown")}`,
      `计划节点：${String(event.payload.plan_count ?? 0)}`,
      `最近工具观察：${String(event.payload.recent_observation_count ?? 0)}`,
      `最近策略事件：${String(event.payload.recent_guard_event_count ?? 0)}`,
      `下一步约束：${String(event.payload.next_step_guidance ?? "")}`
    ].join("\n");
  }
  if (event.type === "action") return actionSummary(event);
  if (event.type === "model_output") return String(event.payload.raw ?? "");
  if (event.type === "policy_blocked" || event.type === "final_blocked") {
    return `原因：${String(event.payload.reason ?? "")}\n建议：${String(event.payload.guidance ?? "")}`;
  }
  if (event.type === "parse_error") return `第 ${String(event.payload.attempt ?? "?")} 次解析失败：${String(event.payload.error ?? "")}`;
  return String(event.payload.message ?? event.payload.final_report ?? JSON.stringify(event.payload, null, 2));
}

function AgentEventStream({ events }: { events: TraceEvent[] }) {
  const visibleEvents = events.filter((event) =>
    ["context_built", "model_output", "action", "policy_blocked", "final_blocked", "parse_error", "cancelled", "error"].includes(event.type)
  );
  if (visibleEvents.length === 0) return <div className="empty">运行开始后，这里会显示上下文构造、模型输出和动作解析。</div>;
  return (
    <div className="eventStream">
      {visibleEvents.slice(-18).map((event, index) => (
        <article className={`eventCard ${event.type}`} key={`${event.created_at}-${index}`}>
          <div className="eventHeader">
            <span>{eventTitle(event)}</span>
            <time>{new Date(event.created_at).toLocaleTimeString()}</time>
          </div>
          <RichText text={eventBody(event)} />
        </article>
      ))}
    </div>
  );
}

function RunHistory({ runs, activeRunId, onSelect }: { runs: RunSummary[]; activeRunId: string | null; onSelect: (runId: string) => void }) {
  if (runs.length === 0) return <div className="empty">暂无历史对话。</div>;
  return (
    <div className="runHistory">
      {runs.slice(0, 8).map((item) => (
        <button className={item.id === activeRunId ? "historyItem active" : "historyItem"} key={item.id} onClick={() => onSelect(item.id)}>
          <span>{item.task}</span>
          <small>{statusText[item.status]} · {item.message_count} 条消息</small>
        </button>
      ))}
    </div>
  );
}

function ChatTimeline({ run, error }: { run: TraceRun | null; error: string | null }) {
  const messages = useMemo(() => {
    const rows: Array<{ role: ChatRole; title: string; body: string }> = [];
    if (run?.messages?.length) {
      for (const message of run.messages) {
        rows.push({
          role: message.role === "assistant" || message.role === "system" ? "agent" : message.role,
          title: message.title,
          body: message.content
        });
      }
    } else if (run?.task) {
      rows.push({ role: "user", title: "用户任务", body: run.task });
      for (const event of run.events ?? []) {
        if (event.type === "action") rows.push({ role: "agent", title: "模型动作", body: actionSummary(event) });
        if (event.type === "policy_blocked" || event.type === "final_blocked") rows.push({ role: "error", title: eventTitle(event), body: eventBody(event) });
        if (event.type === "parse_error") rows.push({ role: "error", title: "结构化解析失败", body: eventBody(event) });
      }
    }
    if (error) rows.push({ role: "error", title: "界面错误", body: error });
    return rows;
  }, [error, run]);

  if (messages.length === 0) {
    return (
      <div className="chatEmpty">
        <strong>输入一个编程任务，TraceCoder 会边执行边留下证据。</strong>
        <span>右侧是对话，左侧是计划图、上下文窗口和模型动作流。</span>
      </div>
    );
  }

  return (
    <div className="chatTimeline">
      {messages.map((message, index) => (
        <article className={`chatBubble ${message.role}`} key={`${message.role}-${index}`}>
          <span>{message.title}</span>
          <RichText text={message.body} />
        </article>
      ))}
    </div>
  );
}

function App() {
  const [task, setTask] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const [run, setRun] = useState<TraceRun | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [model, setModel] = useState<OllamaStatus | null>(null);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [isUploading, setIsUploading] = useState(false);

  const completedNodes = useMemo(() => (run?.plan ?? []).filter((node) => node.status === "success").length, [run]);
  const evidence = useMemo(() => {
    const observations = run?.observations ?? [];
    return {
      commands: observations.filter((observation) => observation.tool === "run_command").length,
      writes: observations.filter((observation) => observation.tool === "write_file").length,
      blocked: observations.some((observation) => observation.tool === "final_guard")
    };
  }, [run]);

  useEffect(() => {
    void fetchOllamaStatus().then(setModel).catch((err: Error) => setError(err.message));
    void fetchRuns().then(setRuns).catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!runId) return;
    const refresh = () => {
      void fetchRun(runId).then(setRun).catch((err: Error) => setError(err.message));
      void fetchRuns().then(setRuns).catch((err: Error) => setError(err.message));
    };
    refresh();
    const source = new EventSource(`/api/runs/${runId}/events`);
    source.onmessage = refresh;
    ["created", "status", "context_built", "model_output", "action", "plan_updated", "observation", "final", "error", "cancelled", "policy_blocked", "final_blocked", "parse_error"].forEach((eventName) => {
      source.addEventListener(eventName, refresh);
    });
    source.onerror = () => source.close();
    return () => source.close();
  }, [runId]);

  async function startRun() {
    const submittedTask = task.trim();
    if (!submittedTask) return;
    setIsStarting(true);
    setError(null);
    setRun(null);
    setTask("");
    try {
      const id = await createRun(submittedTask);
      setRunId(id);
      void fetchRuns().then(setRuns).catch((err: Error) => setError(err.message));
    } catch (err) {
      setTask(submittedTask);
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIsStarting(false);
    }
  }

  async function selectRun(id: string) {
    setError(null);
    setRunId(id);
    try {
      const selected = await fetchRun(id);
      setRun(selected);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    }
  }

  async function stopRun() {
    if (!runId || run?.status !== "running") return;
    try {
      await cancelRun(runId);
      const updated = await fetchRun(runId);
      setRun(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
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
      setTask((current) => `${current.trim()}\n\n可参考上传文件：${uploaded.path}`.trim());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIsUploading(false);
    }
  }

  async function removeUploadedFile(file: UploadedFile) {
    try {
      await deleteUploadedFile(file.path);
      setUploadedFiles((files) => files.filter((item) => item.path !== file.path));
      setTask((current) =>
        current
          .split("\n")
          .filter((line) => !line.includes(`可参考上传文件：${file.path}`))
          .join("\n")
          .replace(/\n{3,}/g, "\n\n")
          .trim()
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    }
  }

  return (
    <main>
      <header className="hero">
        <div>
          <h1>TraceCoder</h1>
          <p>把编程任务拆成计划图，逐步执行工具，并把上下文、模型输出、动作解析和验证证据留在页面上。</p>
        </div>
        <div className={`runStatus ${run?.status ?? "idle"}`}>{statusText[run?.status ?? "idle"]}</div>
      </header>

      <div className="workspace">
        <aside className="leftRail">
          <div className="sectionHeader">
            <Cpu size={18} />
            <h2>历史对话</h2>
          </div>
          <RunHistory runs={runs} activeRunId={runId} onSelect={(id) => void selectRun(id)} />

          <section className="summaryBand">
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
            <div>
              <span>模型</span>
              <strong>{model?.selected_model ?? "未选择"}</strong>
            </div>
          </section>

          <div className="sectionHeader">
            <Activity size={18} />
            <h2>计划图</h2>
          </div>
          <PlanTimeline nodes={run?.plan ?? []} />

          <div className="sectionHeader">
            <Cpu size={18} />
            <h2>模型动作流</h2>
          </div>
          <AgentEventStream events={run?.events ?? []} />

          <div className="sectionHeader">
            <Terminal size={18} />
            <h2>执行记录</h2>
          </div>
          <div className="observations compact">
            {(run?.observations ?? []).length > 0 ? (
              (run?.observations ?? []).map((observation, index) => (
                <ObservationCard key={`${observation.created_at}-${index}`} observation={observation} />
              ))
            ) : (
              <div className="empty">暂无工具调用记录。</div>
            )}
          </div>
        </aside>

        <section className="chatPanel">
          <div className="chatHeader">
            <div>
              <h2>对话</h2>
              <p>{run ? statusText[run.status] : "等待输入任务"}</p>
            </div>
            <div className={`runStatus ${run?.status ?? "idle"}`}>{statusText[run?.status ?? "idle"]}</div>
          </div>

          <ChatTimeline run={run} error={error} />

          {uploadedFiles.length > 0 ? (
            <div className="uploadList">
              {uploadedFiles.map((file) => (
                <div key={file.path}>
                  <div>
                    <strong>{file.filename}</strong>
                    <span>{file.path} · {file.size} bytes</span>
                  </div>
                  <button className="iconButton" onClick={() => void removeUploadedFile(file)} title="删除这个上传文件">
                    <Trash2 size={16} />
                  </button>
                </div>
              ))}
            </div>
          ) : null}

          <div className="composer">
            <textarea
              aria-label="任务内容"
              placeholder="输入你想让 TraceCoder 完成的编程任务..."
              value={task}
              onChange={(event) => setTask(event.target.value)}
            />
            <div className="composerActions">
              <label className="uploadButton">
                <FileUp size={18} />
                <span>{isUploading ? "上传中" : "上传文件"}</span>
                <input type="file" onChange={(event) => void handleUpload(event.target.files)} disabled={isUploading} />
              </label>
              <button onClick={startRun} disabled={isStarting || !task.trim()} title="发送任务">
                {isStarting ? <Play size={18} /> : <Send size={18} />}
                <span>{isStarting ? "运行中" : "发送"}</span>
              </button>
              <button className="stopButton" onClick={stopRun} disabled={run?.status !== "running"} title="停止当前任务">
                <XCircle size={18} />
                <span>停止</span>
              </button>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
