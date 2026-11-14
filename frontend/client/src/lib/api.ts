import type { BackendJob, CvResult, GapResult, Profile, SearchResult } from "@/lib/types";
const base = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/+$/, "");
export const backendConfigured = Boolean(base) || import.meta.env.DEV;
const url = (path: string) => `${base}/api/v1${path}`;
type TraceEntry = { at: string; event: string; [key: string]: string | number | boolean | undefined };
const trace = (event: string, details: Omit<TraceEntry, "at" | "event"> = {}) => {
  const entry: TraceEntry = { at: new Date().toISOString(), event, ...details };
  const key = "carrery:trace";
  const existing = JSON.parse(sessionStorage.getItem(key) || "[]") as TraceEntry[];
  sessionStorage.setItem(key, JSON.stringify([...existing, entry].slice(-50)));
  console.info(`[Carrery trace] ${event}`, entry);
};
const requestHeaders = (headers?: HeadersInit) => {
  const values = new Headers(headers);
  if (base.includes(".ngrok-free.")) values.set("ngrok-skip-browser-warning", "true");
  return values;
};
async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const method = init?.method || "GET";
  const startedAt = performance.now();
  trace("request_started", { method, path });
  let res: Response;
  try {
    res = await fetch(url(path), { ...init, headers: requestHeaders(init?.headers) });
  } catch (error) {
    trace("request_network_error", { method, path, message: error instanceof Error ? error.message : "Unknown network error" });
    throw error;
  }
  const data = await res.json().catch(() => null);
  trace("response_received", { method, path, status: res.status, ok: res.ok, duration_ms: Math.round(performance.now() - startedAt) });
  if (!res.ok) throw new Error(data?.detail || "The request could not be completed.");
  return data as T;
}
export async function uploadCv(file: File) { const fd = new FormData(); fd.append("file", file); return api<Profile>("/cv/extract", { method: "POST", body: fd }); }
export const startManual = (payload: { keyword: string; location: string; target_level?: string }) => api<BackendJob<SearchResult>>("/jobs/search", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
export const startFromCv = (payload: { upload_id: string; keyword?: string; target_level?: string; location?: string }) => api<BackendJob<SearchResult>>("/jobs/search-from-cv", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
export const searchJob = (id: string) => api<BackendJob<SearchResult>>(`/jobs/search/${id}`);
export const startGap = (payload: { cv_upload_id: string; search_job_id: string; keyword?: string; target_level?: string; location?: string }) => api<BackendJob<GapResult>>("/analysis/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
export const gapJob = (id: string) => api<BackendJob<GapResult>>(`/analysis/jobs/${id}`);
export const startCvReview = (uploadId: string) => api<BackendJob<CvResult>>("/analysis/cv-direct", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ upload_id: uploadId }) });
export const cvReviewJob = (id: string) => api<BackendJob<CvResult>>(`/analysis/cv-direct/${id}`);
export async function poll<T>(get: () => Promise<BackendJob<T>>) {
  const until = Date.now() + 300000;
  let attempt = 0;
  trace("poll_started");
  while (Date.now() < until) {
    attempt += 1;
    const job = await get();
    trace("poll_status", { attempt, job_id: job.id, status: job.status });
    if (job.status === "completed") return job;
    if (job.status === "failed") throw new Error(job.error || "The background job failed.");
    await new Promise((r) => setTimeout(r, 1700));
  }
  trace("poll_timed_out", { attempts: attempt });
  throw new Error("This is taking longer than expected. Please try again shortly.");
}
