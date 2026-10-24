"use client";

import { useRef, useState } from "react";

export default function Home() {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function processVideo() {
    if (!file || busy) return;
    setBusy(true); setError(""); setMessage("Uploading and processing video. Please wait…");
    const form = new FormData();
    form.append("file", file);
    try {
      const apiBase = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
      const response = await fetch(`${apiBase}/api/shorts`, {
        method: "POST", body: form
      });
      if (!response.ok) {
        let detail = "Processing failed.";
        try { detail = (await response.json()).detail || detail; } catch {}
        throw new Error(detail);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "drama-entertainment-shorts.zip";
      a.click();
      URL.revokeObjectURL(url);
      setMessage("Done. ZIP download started.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not connect to the backend.");
      setMessage("");
    } finally { setBusy(false); }
  }

  return (
    <main className="page">
      <header><div className="logo">D<span>&</span>E</div><div><b>DRAMA & ENTERTAINMENT</b><small>SHORTS CUTTER</small></div><span className="status">LOCAL TOOL</span></header>
      <section className="hero">
        <p className="eyebrow">VIDEO UTILITY / 01</p>
        <h1>One long video.<br/><em>60-second shorts.</em></h1>
        <p className="subtitle">Cut. Crop to vertical. Watermark. Download all clips in one ZIP.</p>
        <div className="upload">
          <div className="uploadIcon">↑</div>
          <h2>{file ? file.name : "Drop in your video"}</h2>
          <p>{file ? `${(file.size / 1048576).toFixed(1)} MB` : "MP4, MOV, MKV, WEBM or M4V · Max 2 GB"}</p>
          <input ref={input} type="file" accept="video/*,.mkv,.m4v" hidden onChange={e => {setFile(e.target.files?.[0] || null);setError("");setMessage("");}}/>
          <button className="secondary" onClick={() => input.current?.click()} disabled={busy}>Choose video</button>
        </div>
        <div className="settings">
          <div><span>CLIP DURATION</span><b>60 seconds</b></div>
          <div><span>OUTPUT FORMAT</span><b>Vertical 9:16 · 1080×1920</b></div>
          <div><span>WATERMARK</span><b>Drama & Entertainment · Bottom-right</b></div>
          <div><span>EXPORT</span><b>MP4 clips · One ZIP</b></div>
        </div>
        <button className="primary" onClick={processVideo} disabled={!file || busy}>{busy ? "PROCESSING…" : "CREATE SHORTS  ↗"}</button>
        {message && <p className="message">{message}</p>}
        {error && <p className="error">{error}</p>}
        <p className="note">Only fixed-duration cutting and vertical cropping. No AI, scene detection, or captions.</p>
      </section>
      <footer>PCMDK369™ <span>DRAMA & ENTERTAINMENT · 2026</span></footer>
    </main>
  );
}
