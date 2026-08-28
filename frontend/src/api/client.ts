export type NodeStatus = "pending" | "running" | "success" | "failed" | "revised";

export type PlanNode = {
  id: string;
  title: string;
  detail: string;
  status: NodeStatus;
};

export type Observation = {
  node_id: string;
  tool: string;
  ok: boolean;
  summary: string;
  data: Record<string, unknown>;
  created_at: string;
};

export type TraceRun = {
  id: string;
  task: string;
  status: "created" | "running" | "success" | "failed";
  plan: PlanNode[];
  observations: Observation[];
  final_report: string | null;
  messages: ChatMessage[];
  events: TraceEvent[];
};

export type ChatMessage = {
  role: "user" | "assistant" | "tool" | "system" | "error";
  title: string;
  content: string;
  event_type: string | null;
  created_at: string;
};

export type TraceEvent = {
  type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type RunSummary = {
  id: string;
  title: string;
  task: string;
  status: TraceRun["status"];
  updated_at: string;
};

export type OllamaStatus = {
  base_url: string;
  models: string[];
  selected_model: string | null;
  error: string | null;
};

export async function fetchOllamaStatus(): Promise<OllamaStatus> {
  const response = await fetch("/api/model");
  if (!response.ok) {
    throw new Error(`Failed to fetch Ollama status: ${response.status}`);
  }
  return response.json();
}

export type UploadedFile = {
  path: string;
  filename: string;
  size: number;
};

export async function uploadFile(file: File): Promise<UploadedFile> {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch("/api/uploads", {
    method: "POST",
    body
  });
  if (!response.ok) {
    throw new Error(`Failed to upload file: ${response.status}`);
  }
  return response.json();
}

export async function deleteUploadedFile(path: string): Promise<void> {
  const response = await fetch(`/api/uploads?path=${encodeURIComponent(path)}`, {
    method: "DELETE"
  });
  if (!response.ok) {
    throw new Error(`Failed to delete uploaded file: ${response.status}`);
  }
}

export async function createRun(task: string): Promise<string> {
  const response = await fetch("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task })
  });
  if (!response.ok) {
    throw new Error(`Failed to create run: ${response.status}`);
  }
  const data = (await response.json()) as { run_id: string };
  return data.run_id;
}

export async function continueRun(runId: string, task: string): Promise<string> {
  const response = await fetch(`/api/runs/${runId}/continue`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task })
  });
  if (!response.ok) {
    throw new Error(`Failed to continue run: ${response.status}`);
  }
  const data = (await response.json()) as { run_id: string };
  return data.run_id;
}

export async function fetchRuns(): Promise<RunSummary[]> {
  const response = await fetch("/api/runs");
  if (!response.ok) {
    throw new Error(`Failed to fetch runs: ${response.status}`);
  }
  return response.json();
}

export async function renameRun(runId: string, title: string): Promise<void> {
  const response = await fetch(`/api/runs/${runId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title })
  });
  if (!response.ok) {
    throw new Error(`Failed to rename run: ${response.status}`);
  }
}

export async function deleteRun(runId: string): Promise<void> {
  const response = await fetch(`/api/runs/${runId}`, {
    method: "DELETE"
  });
  if (!response.ok) {
    throw new Error(`Failed to delete run: ${response.status}`);
  }
}

export async function deleteRuns(runIds: string[]): Promise<void> {
  const response = await fetch("/api/runs/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_ids: runIds })
  });
  if (!response.ok) {
    throw new Error(`Failed to delete runs: ${response.status}`);
  }
}

export async function cancelRun(runId: string): Promise<void> {
  const response = await fetch(`/api/runs/${runId}/cancel`, {
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Failed to cancel run: ${response.status}`);
  }
}

export async function fetchRun(runId: string): Promise<TraceRun> {
  const response = await fetch(`/api/runs/${runId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch run: ${response.status}`);
  }
  return response.json();
}
