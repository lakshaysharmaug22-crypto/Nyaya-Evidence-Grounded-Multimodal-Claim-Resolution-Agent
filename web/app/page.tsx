"use client";
import { useState } from "react";
import { Glass } from "@/components/Glass";
import { FlowGraph, NODES } from "@/components/FlowGraph";
import { API, useClaimStream } from "@/lib/useClaimStream";
import { checkPhoto, Quality } from "@/lib/photoCheck";

const PRESETS: Record<string, { text: string; claim: Record<string, unknown> }> = {
  "Damaged product": { text: "Received a cracked screen protector kit, photo attached.", claim: { id: "P1", order_id: "ORD1001", damage_conf: 0.95, amount_inr: 1499, days_since_delivery: 2 } },
  "Late claim": { text: "Item was damaged but I only noticed now.", claim: { id: "P2", order_id: "ORD1002", damage_conf: 0.93, amount_inr: 999, days_since_delivery: 12 } },
  "Unclear photo": { text: "Something looks off with the package.", claim: { id: "P3", order_id: "ORD1003", damage_conf: 0.6, amount_inr: 2999, days_since_delivery: 3 } },
};

const toB64 = (f: File) => new Promise<string>((res) => {
  const r = new FileReader(); r.onload = () => res(String(r.result).split(",")[1]); r.readAsDataURL(f);
});

export default function Customer() {
  const [text, setText] = useState("");
  const [claim, setClaim] = useState<Record<string, unknown>>({});
  const [q, setQ] = useState<Quality | null>(null);
  const [img, setImg] = useState<string | undefined>();
  const [inv, setInv] = useState<string | undefined>();
  const [invName, setInvName] = useState("");
  const { status, final, busy, run } = useClaimStream();
  const [claimId, setClaimId] = useState("");
  const [handoff, setHandoff] = useState("");
  const [rec, setRec] = useState<MediaRecorder | null>(null);
  const [voiceMsg, setVoiceMsg] = useState("");

  const talkToHuman = async () => {
    if (!API) { setHandoff("Queued (demo mode). A person will pick this up with your full case."); return; }
    try {
      const r = await fetch(`${API}/handoff`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: claimId, note: text }) }).then((x) => x.json());
      setHandoff(`Queued at position ${r.position}. A person will pick this up${r.has_case ? " with your full case" : ""}.`);
    } catch { setHandoff("Could not reach support right now. Please try again."); }
  };
  const toggleVoice = async () => {
    if (rec) { rec.stop(); setRec(null); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream), chunks: Blob[] = [];
      mr.ondataavailable = (e) => chunks.push(e.data);
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setVoiceMsg("Transcribing...");
        const b64 = await toB64(new File([new Blob(chunks)], "note.webm"));
        const r = await fetch(`${API}/voice/transcribe`, { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ audio_b64: b64 }) }).then((x) => x.json()).catch(() => ({ ok: false }));
        if (r.ok) { setText((t) => (t ? t + " " : "") + r.text); setVoiceMsg(`Heard (${r.language}). Edit if needed.`); }
        else setVoiceMsg("Could not transcribe. Please type instead.");
      };
      mr.start(); setRec(mr); setVoiceMsg("Recording... tap again to stop.");
    } catch { setVoiceMsg("Microphone not available."); }
  };
  const started = Object.keys(status).length > 0;

  const onFile = async (f?: File) => {
    if (!f) return;
    setQ(await checkPhoto(f));
    setImg(await toB64(f));
  };
  const blocked = q ? !q.ok : false;

  return (
    <div className="wrap">
      <h1>Raise a claim</h1>
      <p className="muted">Describe the issue, add a photo. Most clear cases resolve in under a minute.</p>
      <div className="grid two">
        <Glass>
          <h2>Your claim</h2>
          <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="What went wrong?" />
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "12px 0" }}>
            {Object.entries(PRESETS).map(([k, v]) => (
              <button key={k} className="pill" style={{ background: "transparent", color: "inherit", cursor: "pointer" }}
                onClick={() => { setText(v.text); setClaim(v.claim); }}>{k}</button>
            ))}
          </div>
          {API && <button className="pill" style={{ background: rec ? "rgba(255,80,90,.3)" : "transparent", color: "inherit", cursor: "pointer", marginRight: 8 }}
            onClick={toggleVoice}>{rec ? "Stop recording" : "Voice note"}</button>}
          {voiceMsg && <div className="muted" style={{ margin: "6px 0" }}>{voiceMsg}</div>}
          <label className="pill" style={{ display: "inline-block", cursor: "pointer" }}>
            Add photo
            <input type="file" accept="image/*" hidden onChange={(e) => onFile(e.target.files?.[0])} />
          </label>
          <label className="pill" style={{ display: "inline-block", cursor: "pointer", marginLeft: 8 }}>
            {invName ? `Invoice: ${invName}` : "Add invoice (PDF/image)"}
            <input type="file" accept="application/pdf,image/*" hidden
              onChange={async (e) => { const f = e.target.files?.[0]; if (f) { setInvName(f.name); setInv(await toB64(f)); } }} />
          </label>
          {q && (
            <div className="muted" style={{ marginTop: 10, color: q.ok ? "#2ee6a6" : "#ff8a8a" }}>
              {q.ok ? "Photo is clear" : `Retake: ${q.reason.replace("_", " ")}`} · {q.tip}
              <div style={{ opacity: .7 }}>brightness {q.brightness} · sharpness {q.sharpness}</div>
            </div>
          )}
          <div style={{ marginTop: 14 }}>
            <button className="btn go" disabled={busy || !text || blocked}
              onClick={() => { const id = "C" + Date.now(); setClaimId(id); run({ id, order_id: "ORD1", text, ...claim, ...(img ? { image_b64: img } : {}), ...(inv ? { invoice_b64: inv } : {}) }); }}>
              {busy ? "Working..." : "Submit claim"}
            </button>
            <button className="pill" style={{ marginLeft: 8, background: "transparent", color: "inherit", cursor: "pointer" }} onClick={talkToHuman}>Talk to a human</button>
          </div>
          {handoff && <p className="muted" style={{ color: "#2ee6a6" }}>{handoff}</p>}
        </Glass>
        <Glass>
          <h2>Live status</h2>
          {!started ? <p className="muted">Nothing yet. Submit a claim to watch it resolve.</p> : <FlowGraph status={status} />}
        </Glass>
      </div>
      {final && (
        <Glass solid style={{ marginTop: 16 }}>
          <h2>Decision</h2>
          <div style={{ fontSize: 22, fontWeight: 700, textTransform: "capitalize" }}>{final.final.decision}</div>
          <p className="muted">Rule: {final.final.rule} · Verified: {final.verified ? "yes" : "no"} · {NODES.length} steps</p>
        </Glass>
      )}
    </div>
  );
}
