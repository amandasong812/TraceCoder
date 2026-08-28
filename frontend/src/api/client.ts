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
};

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

export async function fetchRun(runId: string): Promise<TraceRun> {
  const response = await fetch(`/api/runs/${runId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch run: ${response.status}`);
  }
  return response.json();
}

