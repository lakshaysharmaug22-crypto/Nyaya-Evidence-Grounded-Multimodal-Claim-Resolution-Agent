"use client";
import { API } from "./useClaimStream";

export const getToken = () => (typeof window === "undefined" ? "" : sessionStorage.getItem("agent_token") ?? "");
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
