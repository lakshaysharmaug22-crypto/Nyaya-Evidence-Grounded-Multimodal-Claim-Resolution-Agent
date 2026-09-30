"use client";
import { useEffect, useState } from "react";
import { API } from "./useClaimStream";

/** Sample mode: agent pages run on built-in sample data instead of the token-protected API.
 *  Lets visitors (e.g. recruiters) explore the console without credentials; nothing touches the API. */
const SAMPLE_KEY = "nyaya_sample";
export const isSample = () => {
  try { return typeof window !== "undefined" && sessionStorage.getItem(SAMPLE_KEY) === "1"; } catch { return false; }
};
export const setSample = (on: boolean) => {
  try { on ? sessionStorage.setItem(SAMPLE_KEY, "1") : sessionStorage.removeItem(SAMPLE_KEY); } catch { /* storage blocked */ }
  window.dispatchEvent(new Event("agent-sample"));
};
/** API base for agent pages: "" (local sample data) in sample mode, else the configured API. */
export function useAgentApi(): string {
  const [api, setApi] = useState(() => (isSample() ? "" : API));
  useEffect(() => {
    const f = () => setApi(isSample() ? "" : API);
    window.addEventListener("agent-sample", f); return () => window.removeEventListener("agent-sample", f);
  }, []);
  return api;
}

export const getToken = () => { try { return typeof window === "undefined" ? "" : sessionStorage.getItem("agent_token") ?? ""; } catch { return ""; } };
export const setToken = (t: string) => { sessionStorage.setItem("agent_token", t); window.dispatchEvent(new Event("agent-token-set")); };

/** Fetch an agent-only endpoint. Sends the access token and asks the UI for one when the API says 401. */
export async function agentFetch(path: string, init: RequestInit = {}) {
  const t = getToken();
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(t ? { "X-Agent-Token": t } : {}), ...(init.headers ?? {}) },
  });
  if (res.status === 401) window.dispatchEvent(new Event("agent-401"));
  return res;
}

export async function downloadFromApi(path: string, filename: string) {
  const res = await agentFetch(path);
  if (!res.ok) return;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(await res.blob()); a.download = filename; a.click();
}

export const openCase = (id: string) => window.dispatchEvent(new CustomEvent("open-case", { detail: id }));
