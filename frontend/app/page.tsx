"use client";

import { ChangeEvent, DragEvent, FormEvent, useEffect, useRef, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "../lib/supabase";

const MAX_SIZE = 2 * 1024 * 1024 * 1024;
const ACCEPTED = [".mp4", ".mov", ".mkv", ".webm", ".m4v"];

export default function Home() {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [busy, setBusy] = useState(false);
  const [activeJob, setActiveJob] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState("");
  const [jobMessage, setJobMessage] = useState("");
  const [dragging, setDragging] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [apiState, setApiState] = useState<"checking" | "online" | "offline">("checking");
  const [session, setSession] = useState<Session | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState("");
  const adminEmail = (process.env.NEXT_PUBLIC_ADMIN_EMAIL || "").trim().toLowerCase();
  const [captionLanguage, setCaptionLanguage] = useState("original");
  const [captionStyle, setCaptionStyle] = useState("auto");
  const [captionColor, setCaptionColor] = useState("white");
  const [captionSize, setCaptionSize] = useState("medium");
  const [captionsEnabled, setCaptionsEnabled] = useState(true);
  const [outputResolution, setOutputResolution] = useState("1080p");
  const [encodingPriority, setEncodingPriority] = useState("balanced");
  const [framing, setFraming] = useState("portrait");

  const apiBase = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

  async function checkBackend() {
    setApiState("checking");
    try {
      const response = await fetch(`${apiBase}/health`, { cache: "no-store" });
      if (!response.ok) throw new Error("Backend unavailable");
      setApiState("online");
    } catch {
      setApiState("offline");
    }
  }

  useEffect(() => { void checkBackend(); }, []);

  useEffect(() => {
    if (!supabase) {
      setAuthReady(true);
      return;
    }
    let mounted = true;
    supabase.auth.getSession().then(({ data }) => {
      if (!mounted) return;
      const current = data.session;
      if (current && adminEmail && (current.user.email || "").toLowerCase() !== adminEmail) {
        setAuthError("This account is not the configured admin account.");
        setSession(null);
        void supabase.auth.signOut();
      } else {
        setSession(current);
      }
      setAuthReady(true);
    });
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      if (!mounted) return;
      if (nextSession && adminEmail && (nextSession.user.email || "").toLowerCase() !== adminEmail) {
        setSession(null);
        setAuthError("Admin access only. Use the configured owner account.");
        void supabase.auth.signOut();
      } else {
        setSession(nextSession);
      }
      setAuthReady(true);
    });
    return () => {
      mounted = false;
      subscription.unsubscribe();
    };
  }, []);

  useEffect(() => {
    if (!activeJob) return;
    let stopped = false;
    let timer: ReturnType<typeof setInterval> | undefined;
    const poll = async () => {
      try {
        const response = await fetch(`${apiBase}/api/jobs/${activeJob}`, { cache: "no-store", headers: { Authorization: `Bearer ${session?.access_token || ""}` } });
        if (!response.ok) throw new Error("Could not retrieve background job status.");
        const job = await response.json();
        if (stopped) return;
        setJobStatus(job.status || "processing");
        setJobMessage(job.message || "Processing in the background…");
        if (job.status === "completed") {
          stopped = true;
          if (timer) clearInterval(timer);
          const downloadResponse = await fetch(`${apiBase}/api/jobs/${activeJob}/download`, {
            headers: { Authorization: `Bearer ${session?.access_token || ""}` },
            cache: "no-store",
          });
          if (!downloadResponse.ok) throw new Error("Could not download the ZIP. Please sign in again and retry.");
          const blobUrl = URL.createObjectURL(await downloadResponse.blob());
          const a = document.createElement("a");
          a.href = blobUrl;
          a.download = "drama-entertainment-shorts.zip";
          document.body.appendChild(a);
          a.click();
          a.remove();
          URL.revokeObjectURL(blobUrl);
          setMessage("Processing completed in the background. Your ZIP download has started.");
          setActiveJob(null);
          setBusy(false);
        } else if (job.status === "failed") {
          stopped = true;
          if (timer) clearInterval(timer);
          setError(job.message || "Background processing failed.");
          setMessage("");
          setActiveJob(null);
          setBusy(false);
        }
      } catch (e) {
        if (stopped) return;
        setJobMessage(e instanceof Error ? e.message : "Waiting for the backend status…");
      }
    };
    void poll();
    timer = setInterval(() => { void poll(); }, 3000);
    return () => {
      stopped = true;
      if (timer) clearInterval(timer);
    };
  }, [activeJob, apiBase, session?.access_token]);

  useEffect(() => {
    if (!file) { setPreview(""); return; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function chooseFile(next: File | undefined) {
    setError("");
    setMessage("");
    if (!next) return;
    const ext = next.name.slice(next.name.lastIndexOf(".")).toLowerCase();
    if (!ACCEPTED.includes(ext)) {
      setFile(null);
      setError("Unsupported file. Choose MP4, MOV, MKV, WEBM or M4V.");
      return;
    }
    if (next.size > MAX_SIZE) {
      setFile(null);
      setError("This file is larger than the 2 GB application limit.");
      return;
    }
    if (next.size === 0) {
      setFile(null);
      setError("This file is empty. Choose another video.");
      return;
    }
    setFile(next);
  }

  function onInputChange(event: ChangeEvent<HTMLInputElement>) {
    chooseFile(event.target.files?.[0]);
    event.target.value = "";
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    chooseFile(event.dataTransfer.files?.[0]);
  }

  async function processVideo() {
    if (!file || busy || activeJob || !session?.access_token) return;
    setBusy(true);
    setError("");
    setMessage("");
    setJobStatus("uploading");
    setJobMessage("Uploading your video to the background processor…");
    const form = new FormData();
    form.append("file", file);
    form.append("captions_enabled", String(captionsEnabled));
    form.append("caption_language", captionLanguage);
    form.append("caption_style", captionStyle);
    form.append("caption_color", captionColor);
    form.append("caption_size", captionSize);
    form.append("output_resolution", outputResolution);
    form.append("encoding_priority", encodingPriority);
    form.append("framing", framing);
    try {
      const response = await fetch(`${apiBase}/api/jobs`, { method: "POST", body: form, headers: { Authorization: `Bearer ${session.access_token}` } });
      if (!response.ok) {
        let detail = "Could not queue the video for processing.";
        try { detail = (await response.json()).detail || detail; } catch {}
        throw new Error(detail);
      }
      const job = await response.json();
      setActiveJob(job.job_id);
      setJobStatus(job.status || "queued");
      setJobMessage(job.message || "Your video is queued. You can use another tab while it processes.");
      setMessage("Upload complete. Video processing is now running in the background.");
      setFile(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not connect to the video-processing backend.");
      setJobMessage("");
      setBusy(false);
    } finally {
      void checkBackend();
    }
  }

  const sizeLabel = (bytes: number) => bytes >= 1024 ** 3
    ? `${(bytes / 1024 ** 3).toFixed(2)} GB`
    : `${(bytes / 1024 ** 2).toFixed(1)} MB`;

  async function signInAdmin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAuthError("");
    if (!supabase) {
      setAuthError("Supabase is not configured on the Vercel frontend.");
      return;
    }
    if (!adminEmail) {
      setAuthError("Set NEXT_PUBLIC_ADMIN_EMAIL in Vercel before signing in.");
      return;
    }
    if (loginEmail.trim().toLowerCase() !== adminEmail) {
      setAuthError("Admin access only. This email is not the configured owner account.");
      return;
    }
    setAuthBusy(true);
    const { data, error } = await supabase.auth.signInWithPassword({
      email: loginEmail.trim(),
      password: loginPassword,
    });
    if (error || !data.session || (data.user.email || "").toLowerCase() !== adminEmail) {
      await supabase.auth.signOut();
      setAuthError(error?.message || "Sign-in failed. Check the admin account credentials.");
      setAuthBusy(false);
      return;
    }
    setSession(data.session);
    setLoginPassword("");
    setAuthBusy(false);
  }

  async function signOutAdmin() {
    if (supabase) await supabase.auth.signOut();
    setSession(null);
    setFile(null);
    setActiveJob(null);
    setBusy(false);
    setAuthError("");
  }


  if (!authReady) {
    return <main className="app-shell"><section className="panel" style={{ maxWidth: 520, margin: "15vh auto", padding: 28 }}><h1>Checking admin session</h1><p>Verifying your private workspace access…</p></section></main>;
  }

  if (!supabase || !adminEmail) {
    return <main className="app-shell"><section className="panel" style={{ maxWidth: 560, margin: "12vh auto", padding: 28 }}><h1>Admin setup required</h1><p>Supabase is connected in the project code, but the frontend environment variables are not complete.</p><p>Set <code>NEXT_PUBLIC_SUPABASE_URL</code>, <code>NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY</code>, and <code>NEXT_PUBLIC_ADMIN_EMAIL</code> in Vercel, then redeploy.</p></section></main>;
  }

  if (!session || (session.user.email || "").toLowerCase() !== adminEmail) {
    return <main className="app-shell">
      <div className="ambient ambient-one" /><div className="ambient ambient-two" />
      <header className="topbar"><a className="brand" href="#"><span className="brand-mark"><span>DE</span><i /></span><span className="brand-copy"><strong>FRAME<span>FLOW</span></strong><small>PRIVATE ADMIN WORKSPACE</small></span></a><span className="connection offline"><i /> ADMIN LOGIN REQUIRED</span></header>
      <section className="panel" style={{ maxWidth: 480, margin: "8vh auto", padding: 28 }}>
        <span className="section-kicker">PRIVATE ACCESS / OWNER ONLY</span>
        <h1 style={{ margin: "12px 0", fontSize: 30 }}>Sign in to FrameFlow</h1>
        <p style={{ color: "#a7a5bb", lineHeight: 1.7 }}>This video-processing workspace is restricted to the configured admin account. Public visitors cannot upload, process, or download videos.</p>
        <form onSubmit={signInAdmin} style={{ display: "grid", gap: 14, marginTop: 22 }}>
          <label style={{ display: "grid", gap: 7 }}>Admin email<input type="email" autoComplete="username" required value={loginEmail} onChange={e => setLoginEmail(e.target.value)} style={{ padding: 13, borderRadius: 8, background: "#101019", border: "1px solid #38324d", color: "#f6f4ff" }} /></label>
          <label style={{ display: "grid", gap: 7 }}>Password<input type="password" autoComplete="current-password" required value={loginPassword} onChange={e => setLoginPassword(e.target.value)} style={{ padding: 13, borderRadius: 8, background: "#101019", border: "1px solid #38324d", color: "#f6f4ff" }} /></label>
          {authError && <div className="notice error-notice" role="alert"><span>!</span><p>{authError}</p></div>}
          <button className="create-button" type="submit" disabled={authBusy} style={{ width: "100%" }}><span>{authBusy ? "VERIFYING ADMIN…" : "ADMIN SIGN IN"}</span><b>↗</b></button>
        </form>
        <p style={{ marginTop: 18, color: "#89869f", fontSize: 11 }}>No public sign-up is available. Create your single admin user in Supabase Authentication first.</p>
      </section>
      <footer className="footer"><span>PRIVATE WORKSPACE <i /> PCMDK369™ © 2026</span></footer>
    </main>;
  }

  return (
    <main className="app-shell">
      <div className="ambient ambient-one" />
      <div className="ambient ambient-two" />
      <header className="topbar">
        <a className="brand" href="#" aria-label="Drama Shorts home">
          <span className="brand-mark"><span>DE</span><i /></span>
          <span className="brand-copy"><strong>FRAME<span>FLOW</span></strong><small>DRAMA & ENTERTAINMENT</small></span>
        </a>
        <div className="topbar-right">
          <button className="icon-button" onClick={() => void signOutAdmin()} title="Sign out admin" aria-label="Sign out admin" style={{ width: "auto", padding: "0 10px", fontSize: 10 }}>SIGN OUT</button>
          <span className={`connection ${apiState}`}><i />{apiState === "online" ? "PROCESSOR ONLINE" : apiState === "checking" ? "CHECKING SERVER" : "SERVER OFFLINE"}</span>
          <button className="icon-button" onClick={() => void checkBackend()} title="Check backend connection" aria-label="Refresh backend connection">↻</button>
        </div>
      </header>

      <section className="hero">
        <div className="hero-copy">
          <div className="overline"><span className="overline-line" /> CREATOR TOOLKIT <span className="overline-number">01 / VIDEO</span></div>
          <h1>Your story.<br /><span>Shorter. Sharper.</span></h1>
          <p className="hero-description">Turn long-form drama into scroll-stopping vertical clips. Clean cuts, cinematic framing, consistent branding — all in one export.</p>
          <div className="hero-pills"><span><b>01</b> CUT</span><span><b>02</b> CROP</span><span><b>03</b> EXPORT</span></div>
        </div>
        <div className="hero-art" aria-label="Decorative vertical video preview">
          <div className="art-orbit orbit-a" /><div className="art-orbit orbit-b" />
          <div className="art-card art-back"><span>FRAME / 02</span><div className="art-lines" /></div>
          <div className="art-card art-front"><div className="art-play">▶</div><span className="art-caption">EVERY SECOND<br /><b>MATTERS.</b></span><span className="art-timestamp">00:60 <i /> 9:16</span></div>
          <div className="art-tag"><span className="sparkle">✳</span><span>MADE FOR<br /><b>THE FEED</b></span></div>
        </div>
      </section>

      <section className="workspace">
        <div className="section-heading"><div><span className="section-kicker">WORKSPACE / 01</span><h2>Create your shorts</h2></div><span className="private-tag"><i /> YOUR FILE STAYS IN YOUR WORKFLOW</span></div>
        <div className="workspace-grid">
          <div className="panel upload-panel">
            <div className="panel-heading"><span className="step-number">01</span><div><h3>Source video</h3><p>Choose a file to get started</p></div></div>
            <input ref={input} className="file-input" type="file" accept="video/mp4,video/quicktime,video/x-matroska,video/webm,.m4v" onChange={onInputChange} />
            {!file ? (
              <div className={`dropzone ${dragging ? "dragging" : ""}`}
                onDragOver={e => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                onClick={() => input.current?.click()}
                onKeyDown={e => { if (e.key === "Enter" || e.key === " ") input.current?.click(); }}
                role="button" tabIndex={0} aria-label="Choose or drop a video">
                <div className="upload-symbol"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M5 15v4h14v-4" /></svg></div>
                <strong>Drop your video here</strong><span>or <b>browse files</b> from your device</span>
                <div className="file-badges"><span>MP4</span><span>MOV</span><span>MKV</span><span>WEBM</span></div>
              </div>
            ) : (
              <div className="selected-file">
                <video className="video-preview" src={preview} controls playsInline />
                <div className="file-info"><span className="file-icon">▶</span><div className="file-name"><strong>{file.name}</strong><small>{sizeLabel(file.size)} · Video selected</small></div><button className="remove-file" onClick={() => { setFile(null); setError(""); setMessage(""); }} disabled={busy} aria-label="Remove selected video">×</button></div>
                <button className="replace-button" onClick={() => input.current?.click()} disabled={busy}>Replace video</button>
              </div>
            )}
            <div className="upload-foot"><span><i className="shield-icon">✓</i> Max file size: 2 GB</span><span>MP4 recommended</span></div>
          </div>

          <div className="panel settings-panel">
            <div className="panel-heading"><span className="step-number">02</span><div><h3>Output settings</h3><p>Processing preset</p></div></div>
            <div className="setting-block"><label>CLIP LENGTH</label><div className="setting-value"><span className="setting-icon">◷</span><div><strong>60 seconds</strong><small>Fixed-duration segments</small></div><span className="fixed-badge">FIXED</span></div></div>
            <div className="setting-block"><label>OUTPUT RESOLUTION</label><div className="setting-value"><span className="setting-icon">▯</span><div><strong>Video resolution</strong><small>Choose output size</small></div><select aria-label="Output resolution" value={outputResolution} onChange={e => setOutputResolution(e.target.value)}><option value="480p">480p</option><option value="720p">720p HD</option><option value="1080p">1080p Full HD</option><option value="2160p">2160p 4K</option></select></div></div>
            <div className="setting-block"><label>ENCODING PRIORITY</label><div className="setting-value"><span className="setting-icon">◴</span><div><strong>Quality and speed</strong><small>Controls FFmpeg encoder profile</small></div><select aria-label="Encoding priority" value={encodingPriority} onChange={e => setEncodingPriority(e.target.value)}><option value="fast">Fast</option><option value="balanced">Balanced</option><option value="quality">High quality</option></select></div></div>
            <div className="setting-block"><label>FRAMING</label><div className="setting-value"><span className="setting-icon">▣</span><div><strong>{framing === "portrait" ? "Fill vertical 9:16" : "Preserve full frame"}</strong><small>{framing === "portrait" ? "Crop edges to fill the frame" : "Fit video with black padding"}</small></div><select aria-label="Video framing" value={framing} onChange={e => setFraming(e.target.value)}><option value="portrait">Portrait crop</option><option value="pad">Preserve full frame</option></select></div></div>
            <div className="setting-block"><label>WATERMARK</label><div className="setting-value"><span className="setting-icon">✳</span><div><strong>Drama & Entertainment</strong><small>Bottom-right · White text</small></div><span className="check-mark">✓</span></div></div>
            <div className="setting-block"><label>EXPORT PACKAGE</label><div className="setting-value"><span className="setting-icon">▤</span><div><strong>MP4 clips in one ZIP</strong><small>Ready to download</small></div><span className="zip-badge">ZIP</span></div></div>
            <div className="settings-note"><span>i</span><p>Each clip is up to 60 seconds. The final clip can be shorter. Original audio is kept when available.</p></div>
          </div>
        </div>
        <div className="panel captions-panel">
          <div className="panel-heading"><span className="step-number">03</span><div><h3>Automatic captions</h3><p>Speech-to-text captions, styled and burned into each clip</p></div></div>
          <label className="caption-toggle"><input type="checkbox" checked={captionsEnabled} onChange={e => setCaptionsEnabled(e.target.checked)} /><span className="toggle-track" /><span><strong>Generate captions automatically</strong><small>Local speech recognition · no LLM used for routine processing</small></span></label>
          <div className="caption-controls">
            <label>CAPTION LANGUAGE<select value={captionLanguage} onChange={e => setCaptionLanguage(e.target.value)} disabled={!captionsEnabled}><option value="original">Original spoken language</option><option value="english">English</option><option value="hindi">Hindi</option></select></label>
            <label>TEMPLATE<select value={captionStyle} onChange={e => setCaptionStyle(e.target.value)} disabled={!captionsEnabled}><option value="auto">Auto recommend</option><option value="classic">Classic subtitle</option><option value="bold">Bold creator</option><option value="minimal">Minimal clean</option></select></label>
            <label>TEXT COLOR<select value={captionColor} onChange={e => setCaptionColor(e.target.value)} disabled={!captionsEnabled}><option value="white">White</option><option value="yellow">Yellow</option><option value="cyan">Cyan</option><option value="pink">Pink</option></select></label>
            <label>TEXT SIZE<select value={captionSize} onChange={e => setCaptionSize(e.target.value)} disabled={!captionsEnabled}><option value="small">Small</option><option value="medium">Medium · recommended</option><option value="large">Large</option></select></label>
          </div>
          <div className="caption-preview"><span className="preview-label">LIVE STYLE PREVIEW</span><span className={`caption-sample sample-${captionColor} sample-${captionSize} sample-${captionStyle === "auto" ? "bold" : captionStyle}`}>Your story, your words.</span><small>Auto recommendation optimizes readability for vertical video.</small></div>
          <div className="emergency-note"><strong>Emergency LLM fallback</strong><p>Optional server-side LLM is called only if local caption translation fails and a translation is requested. No API key is exposed to the browser. Configure <code>LLM_API_KEY</code>, <code>LLM_API_URL</code>, and <code>LLM_MODEL_ID</code> in the backend host environment.</p></div>
        </div>
        <div className="action-row"><div className="action-hint"><span className="live-dot" />{file ? `Ready to process · ${sizeLabel(file.size)}` : "Select a video to enable processing"}</div><button className="create-button" onClick={processVideo} disabled={!file || busy || Boolean(activeJob)}><span>{busy ? "STARTING BACKGROUND JOB…" : activeJob ? "PROCESSING IN BACKGROUND…" : "CREATE SHORTS"}</span><b>{busy ? <span className="spinner" /> : "↗"}</b></button></div>
        {message && <div className="notice success-notice" role="status"><span>✓</span><p>{message}</p></div>}
        {(activeJob || jobStatus === "completed") && <div className="notice success-notice" role="status"><span>↻</span><p><strong>Background job: {jobStatus}</strong><br />{jobMessage || "Processing is running on the server. Keep this page open to receive the automatic download."}</p></div>}
        {error && <div className="notice error-notice" role="alert"><span>!</span><p>{error}</p></div>}
        {apiState === "offline" && <div className="notice error-notice" role="status"><span>!</span><p>Video processor is unreachable. Start the FastAPI backend or configure NEXT_PUBLIC_API_URL to its public address, then tap refresh.</p></div>}
      </section>

      <section className="steps-section"><div className="section-heading"><div><span className="section-kicker">SIMPLE BY DESIGN</span><h2>From long to ready-to-post</h2></div></div><div className="steps-grid"><article><span className="step-art">↥</span><div><small>STEP 01</small><h3>Upload</h3><p>Select your source video from your device.</p></div></article><article><span className="step-art">◫</span><div><small>STEP 02</small><h3>Auto process</h3><p>60-second cuts, vertical crop and watermark.</p></div></article><article><span className="step-art">↓</span><div><small>STEP 03</small><h3>Download</h3><p>Get all MP4 clips together in one ZIP file.</p></div></article></div></section>
      <footer className="footer"><a className="footer-brand" href="#">FRAMEFLOW<span> / SHORTS CUTTER</span></a><span>BUILT FOR CREATORS <i /> PCMDK369™ © 2026</span></footer>
    </main>
  );
}
