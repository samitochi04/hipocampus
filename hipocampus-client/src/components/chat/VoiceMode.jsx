/**
 * src/components/chat/VoiceMode.jsx
 *
 * Full conversation voice panel with two modes:
 *
 *   MANUAL (default)
 *     Hold the mic button to speak, release to send.
 *     Good for precise control, noisy environments.
 *
 *   AUTO  (toggle with the "Auto" button)
 *     After AI finishes speaking, the panel auto-starts listening.
 *     Voice Activity Detection stops recording after 1.5 s of silence —
 *     no button interaction needed. Natural back-and-forth conversation.
 *     This is the "wow" feature for the demo.
 *
 * TTS playback:
 *   Primary — server MP3 from qwen-omni-turbo (attached to the response).
 *   Fallback — browser Web Speech API when server TTS fails.
 *              Guarantees the user always HEARS the AI, never sees silence.
 *
 * Document attachment:
 *   The panel has its own file picker. Drop a PDF/CSV/MD, then speak your
 *   question — the document is included in the AI context automatically.
 */

import { useEffect, useRef, useState } from "react";
import { uploadDocument, validateFile } from "../../api/upload.js";
import { base64ToBlob, sendVoiceMessage } from "../../api/voice.js";

// ── VAD constants ──────────────────────────────────────────────────────────
const VAD_SILENCE_THRESHOLD = 0.045;   // RMS below this = silence (raised: ignore keyboard/fan noise)
const VAD_SILENCE_MS        = 2000;    // 2 s of silence → auto-stop
const VAD_MIN_SPOKEN_MS     = 1800;    // must speak ≥ 1.8 s of real audio before auto-stop

export default function VoiceMode({ sessionId, onTurn }) {
  const [phase,      setPhase]      = useState("idle");
  const [mode,       setMode]       = useState("manual");   // "manual" | "auto"
  const [seconds,    setSeconds]    = useState(0);
  const [errMsg,     setErrMsg]     = useState("");
  const [vadLevel,   setVadLevel]   = useState(0);
  const [lastPair,   setLastPair]   = useState(null);
  const [attachment, setAttachment] = useState(null);

  const recorderRef   = useRef(null);
  const chunksRef     = useRef([]);
  const timerRef      = useRef(null);
  const audioRef      = useRef(null);
  const mimeRef       = useRef("audio/webm");
  const fileInputRef  = useRef(null);
  const modeRef       = useRef("manual");
  const phaseRef      = useRef("idle");

  // Keep refs in sync
  useEffect(() => { modeRef.current  = mode;  }, [mode]);
  useEffect(() => { phaseRef.current = phase; }, [phase]);

  // Cleanup on unmount
  useEffect(() => () => {
    clearInterval(timerRef.current);
    audioRef.current?.pause();
    window.speechSynthesis?.cancel();
    recorderRef.current?.stream?.getTracks().forEach(t => t.stop());
  }, []);

  // ── File attachment ────────────────────────────────────────────────────────

  async function handleFileChange(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const v = validateFile(file);
    if (!v.valid) { setErrMsg(v.error); return; }
    setAttachment({ filename: file.name, status: "processing" });
    setErrMsg("");
    try {
      const res = await uploadDocument(file);
      setAttachment({ filename: res.filename, extractedText: res.extracted_text, status: "ready" });
    } catch (err) {
      setAttachment(null);
      setErrMsg(err.message ?? "Upload failed.");
    }
  }

  // ── Recording ──────────────────────────────────────────────────────────────

  function getSupportedMime() {
    return ["audio/webm;codecs=opus","audio/webm","audio/ogg;codecs=opus","audio/mp4"]
      .find(t => MediaRecorder.isTypeSupported(t)) ?? "";
  }

  async function startListening() {
    if (phaseRef.current !== "idle" && phaseRef.current !== "error") return;
    setErrMsg("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime   = getSupportedMime();
      mimeRef.current = mime || "audio/webm";
      const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : {});
      chunksRef.current = [];
      rec.ondataavailable = ev => { if (ev.data?.size > 0) chunksRef.current.push(ev.data); };
      rec.onstop = processRecording;
      rec.start(100);
      recorderRef.current = rec;
      setPhase("recording");
      setSeconds(0);
      timerRef.current = setInterval(() => setSeconds(s => s + 1), 1000);
      if (modeRef.current === "auto") startVAD(stream, rec);
    } catch {
      setErrMsg("Microphone access denied — check browser permissions.");
      setPhase("error");
    }
  }

  function startVAD(stream, rec) {
    const ctx      = new (window.AudioContext || window.webkitAudioContext)();
    const source   = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    source.connect(analyser);
    const data = new Float32Array(analyser.frequencyBinCount);
    let silenceStart = null;
    let spokenAt     = null;

    function tick() {
      if (recorderRef.current?.state !== "recording") { ctx.close(); return; }
      analyser.getFloatTimeDomainData(data);
      const rms = Math.sqrt(data.reduce((s, v) => s + v * v, 0) / data.length);
      setVadLevel(Math.min(rms * 12, 1));

      if (rms > VAD_SILENCE_THRESHOLD) {
        if (!spokenAt) spokenAt = Date.now();
        silenceStart = null;
      } else {
        const hasSpokenEnough = spokenAt && (Date.now() - spokenAt) > VAD_MIN_SPOKEN_MS;
        if (hasSpokenEnough) {
          if (!silenceStart) {
            silenceStart = Date.now();
          } else if (Date.now() - silenceStart > VAD_SILENCE_MS) {
            ctx.close();
            clearInterval(timerRef.current);
            rec.stop();
            stream.getTracks().forEach(t => t.stop());
            return;
          }
        }
      }
      requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  function stopManually() {
    if (phaseRef.current !== "recording") return;
    clearInterval(timerRef.current);
    recorderRef.current?.stop();
    recorderRef.current?.stream?.getTracks().forEach(t => t.stop());
  }

  // ── Handle pointer events for manual mode ─────────────────────────────────

  function handlePointerDown(e) {
    if (mode === "auto") return;
    // IMPORTANT: only call preventDefault() when we are actually going to start
    // recording. If we call it unconditionally, the browser suppresses the
    // subsequent click event — which means onClick={stopAudio} never fires
    // when the user taps the button while the AI is speaking.
    if (phase !== "idle" && phase !== "error") return;
    e.preventDefault();
    if (attachment?.status === "processing") { setErrMsg("Wait for document to finish loading."); return; }
    startListening();
  }

  function handlePointerUp(e) {
    e.preventDefault();
    if (modeRef.current === "auto") return;
    // Use phaseRef.current (not phase) to avoid stale closure —
    // phase captured at render time may not reflect the current speaking state.
    if (phaseRef.current === "speaking") { stopAudio(); return; }
    if (phaseRef.current !== "recording") return;
    stopManually();
  }

  function handleMicClick() {
    if (mode !== "auto") return;
    if (phase === "idle" || phase === "error") {
      if (attachment?.status === "processing") { setErrMsg("Wait for document to finish loading."); return; }
      startListening();
    } else if (phase === "recording") {
      stopManually();
    } else if (phase === "speaking") {
      stopAudio();  // handles both server audio and browser TTS
    }
  }

  // ── Process & play ─────────────────────────────────────────────────────────

  async function processRecording() {
    setPhase("processing");
    setVadLevel(0);
    if (!chunksRef.current.length) {
      setErrMsg(mode === "auto"
        ? "Nothing heard — tap the mic and speak."
        : "No audio — hold the mic button while speaking.");
      setPhase("error");
      return;
    }

    // Reject recordings that are too short to contain real speech.
    // A 48kbps WebM/Opus stream produces ~6 KB per second.
    // Less than 4 KB = under ~0.6 s — almost certainly noise, not speech.
    const totalBytes = chunksRef.current.reduce((s, c) => s + c.size, 0);
    if (totalBytes < 4000) {
      setErrMsg(mode === "auto"
        ? "Speak louder or longer — background noise detected."
        : "Recording too short — hold the button while speaking.");
      setPhase("error");
      if (modeRef.current === "auto") setTimeout(() => {
        phaseRef.current = "idle"; setPhase("idle");
      }, 2000);
      return;
    }

    const blob = new Blob(chunksRef.current, { type: mimeRef.current });
    try {
      const result = await sendVoiceMessage({
        audioBlob:  blob,
        sessionId,
        docContent: attachment?.status === "ready" ? attachment.extractedText : null,
        docName:    attachment?.status === "ready" ? attachment.filename      : null,
      });

      setLastPair({ user: result.transcription, ai: result.response });
      onTurn?.({
        transcription: result.transcription,
        response:      result.response,
        sessionId:     result.session_id,
        chatId:        result.chat_id,
        webSearched:   result.web_searched,
      });

      // ── Speak the response ────────────────────────────────────────────
      if (result.audio_base64) {
        try {
          await playServerAudio(result.audio_base64, result.audio_format);
        } catch {
          // Autoplay blocked (HTTP page) — fall back to browser TTS
          await playBrowserTTS(result.response);
        }
      } else {
        await playBrowserTTS(result.response);
      }

    } catch (err) {
      const msg = err.message ?? "Request failed — please try again.";
      const isShort = msg.toLowerCase().includes("too short");
      if (isShort && modeRef.current === "auto") {
        // Noise turn — silently reset and re-listen instead of showing error
        phaseRef.current = "idle";
        setPhase("idle");
        setTimeout(() => { if (phaseRef.current === "idle") startListening(); }, 800);
      } else {
        setErrMsg(msg);
        setPhase("error");
      }
    }
  }

  async function playServerAudio(b64, fmt) {
    return new Promise((resolve, reject) => {
      setPhase("speaking");
      const blob = base64ToBlob(b64, `audio/${fmt}`);
      const url  = URL.createObjectURL(blob);
      const aud  = new Audio(url);
      audioRef.current = aud;
      const done = () => { URL.revokeObjectURL(url); afterSpeech(); resolve(); };
      aud.onended = done;
      aud.onerror = done;
      aud.play().catch(err => {
        // Autoplay blocked (HTTP page, expired user-gesture window).
        // Clean up and reject so the caller can fall back to browser TTS.
        URL.revokeObjectURL(url);
        audioRef.current = null;
        setPhase("idle");
        reject(err);
      });
    });
  }

  async function playBrowserTTS(text) {
    return new Promise(resolve => {
      if (!window.speechSynthesis) { afterSpeech(); resolve(); return; }
      setPhase("speaking");
      // Truncate for browser TTS
      // No char limit — let the full response be spoken
    const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate  = 1.05;
      utterance.pitch = 1.0;
      const done = () => { afterSpeech(); resolve(); };
      utterance.onend   = done;
      utterance.onerror = done;
      window.speechSynthesis.speak(utterance);
    });
  }

  function afterSpeech() {
    // Update ref immediately — don't wait for the useEffect([phase]) round-trip.
    // Without this, startListening() may see phaseRef.current = "speaking" and bail.
    phaseRef.current = "idle";
    setPhase("idle");
    if (modeRef.current === "auto") {
      // Re-check phase inside the timeout in case the user manually started
      // a recording during the pause window (rare but possible).
      setTimeout(() => {
        if (phaseRef.current === "idle") startListening();
      }, 700);
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  const busy         = phase === "processing";
  const isRecording  = phase === "recording";
  const isSpeaking   = phase === "speaking";
  const isAuto       = mode === "auto";
  const idleInAuto   = isAuto && phase === "idle";

  return (
    <div style={s.wrap}>

      {/* Mode toggle + attach */}
      <div style={s.toolbar}>
        {/* Auto-continue toggle */}
        <button
          onClick={() => setMode(m => m === "auto" ? "manual" : "auto")}
          style={isAuto ? { ...s.modBtn, ...s.modBtnActive } : s.modBtn}
          title={isAuto ? "Switch to manual (hold to talk)" : "Switch to auto-continue mode"}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
            style={{ marginRight:4 }} aria-hidden="true">
            <polyline points="17 1 21 5 17 9"/>
            <path d="M3 11V9a4 4 0 0 1 4-4h14"/>
            <polyline points="7 23 3 19 7 15"/>
            <path d="M21 13v2a4 4 0 0 1-4 4H3"/>
          </svg>
          {isAuto ? "Auto ON" : "Auto OFF"}
        </button>

        {/* Attach document */}
        <input ref={fileInputRef} type="file" accept=".pdf,.csv,.md"
          onChange={handleFileChange} style={{ display:"none" }} />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={busy}
          style={attachment?.status === "ready"
            ? { ...s.attachBtn, ...s.attachBtnOn }
            : s.attachBtn}
          title="Attach a document (PDF, CSV, Markdown)"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
            aria-hidden="true">
            <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
          </svg>
          {attachment?.status === "ready"
            ? <><span style={s.attachName}>{attachment.filename}</span>
                <button onClick={e=>{e.stopPropagation();setAttachment(null);}}
                  style={s.chipX}>×</button></>
            : attachment?.status === "processing"
              ? "Loading…"
              : "Attach doc"
          }
        </button>
      </div>

      {/* VAD waveform bar (auto mode only, while recording) */}
      {isAuto && isRecording && (
        <div style={s.vadBar}>
          {[...Array(12)].map((_, i) => {
            const h = Math.max(4, Math.min(28, vadLevel * 28 +
              Math.sin((Date.now() / 120) + i) * 6));
            return <span key={i} style={{ ...s.vadSegment,
              height: `${h}px`,
              opacity: vadLevel > 0.05 ? 0.9 : 0.3 }} />;
          })}
        </div>
      )}

      {/* Mic button */}
      <button
        onPointerDown={!isAuto ? handlePointerDown : undefined}
        onPointerUp={!isAuto ? handlePointerUp : undefined}
        onPointerLeave={!isAuto && (isRecording || isSpeaking) ? handlePointerUp : undefined}
        onPointerCancel={!isAuto && (isRecording || isSpeaking) ? handlePointerUp : undefined}
        onClick={isAuto ? handleMicClick : undefined}
        disabled={busy}
        style={{
          ...s.mic,
          ...(isRecording  ? s.micRec  : {}),
          ...(isSpeaking   ? s.micPlay : {}),
          ...(idleInAuto   ? s.micAuto : {}),
          ...(busy         ? s.micBusy : {}),
        }}
        aria-label={
          isRecording ? "Recording — release to send"
          : isSpeaking ? "AI is speaking"
          : isAuto ? "Tap to speak (or auto-starts)"
          : "Hold to speak"
        }
      >
        {busy
          ? <span style={s.spin} />
          : isSpeaking
            ? <SpeakerIcon />
            : <MicIcon rec={isRecording} />}
      </button>

      {/* Status */}
      <div style={s.label} aria-live="polite">
        {phase === "idle" && !isAuto  && "Hold to speak"}
        {phase === "idle" &&  isAuto  && <span style={{ color:"var(--color-accent)" }}>● Listening — speak when ready</span>}
        {isRecording && !isAuto       && <Ticker s={seconds} />}
        {isRecording &&  isAuto       && <span style={{ display:"flex",alignItems:"center",gap:6 }}>
          <span style={{ width:8,height:8,borderRadius:"50%",background:"var(--color-error)",
            display:"inline-block",animation:"vp 1.2s ease-in-out infinite" }} />
          Listening · {String(Math.floor(seconds/60)).padStart(2,"0")}:{String(seconds%60).padStart(2,"0")}
        </span>}
        {phase === "processing"       && "Thinking…"}
        {phase === "speaking"         && (isAuto ? "Speaking — next question ready after…" : "Speaking · tap to stop")}
        {phase === "error"            && <span style={{ color:"var(--color-error)" }}>{errMsg}</span>}
      </div>

      {/* Last exchange */}
      {lastPair && (phase === "idle" || phase === "error") && (
        <div style={s.preview}>
          <div style={s.preUser}><MicTiny />{lastPair.user}</div>
          <div style={s.preAi}><span style={s.dot} /><span>{lastPair.ai.slice(0,140)}{lastPair.ai.length>140?"…":""}</span></div>
        </div>
      )}

      <p style={s.hint}>
        {isAuto
          ? "Auto mode: AI speaks → auto-listens → you speak → AI speaks…"
          : "Manual: hold to speak · release to send"}
      </p>

      <style>{`
        @keyframes vp{0%,100%{transform:scale(1);box-shadow:0 0 0 0 rgba(239,68,68,.4)}50%{transform:scale(1.06);box-shadow:0 0 0 12px rgba(239,68,68,0)}}
        @keyframes vs{to{transform:rotate(360deg)}}
        @keyframes apulse{0%,100%{box-shadow:0 0 0 0 rgba(255,255,255,.2)}50%{box-shadow:0 0 0 10px rgba(255,255,255,0)}}
      `}</style>
    </div>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────

function Ticker({ s }) {
  const m = String(Math.floor(s/60)).padStart(2,"0");
  const sec = String(s%60).padStart(2,"0");
  return <span style={{ display:"flex",alignItems:"center",gap:6 }}>
    <span style={{ width:8,height:8,borderRadius:"50%",background:"var(--color-error)",
      display:"inline-block",animation:"vp 1.2s ease-in-out infinite" }} />
    {m}:{sec} — release to send
  </span>;
}

function MicIcon({ rec }) {
  return <svg width="28" height="28" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={rec?2.2:1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
    <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
    <line x1="12" y1="19" x2="12" y2="23"/>
    <line x1="8" y1="23" x2="16" y2="23"/>
  </svg>;
}
function SpeakerIcon() {
  return <svg width="26" height="26" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
    <path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>
    <path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>
  </svg>;
}
function MicTiny() {
  return <svg width="10" height="10" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
    style={{ flexShrink:0,marginTop:2 }} aria-hidden="true">
    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
    <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
  </svg>;
}

// ── Styles ─────────────────────────────────────────────────────────────────
const s = {
  wrap: { display:"flex",flexDirection:"column",alignItems:"center",
    gap:"var(--sp-3)",padding:"var(--sp-4) var(--sp-4) var(--sp-4)",
    background:"var(--color-bg-surface)",borderTop:"1px solid var(--color-border)",
    minHeight:"210px",justifyContent:"center" },
  toolbar: { display:"flex",gap:"var(--sp-2)",alignSelf:"stretch",
    justifyContent:"center",flexWrap:"wrap" },
  modBtn: { display:"flex",alignItems:"center",padding:"var(--sp-1) var(--sp-3)",
    background:"transparent",borderWidth:"1px",borderStyle:"solid",
    borderColor:"var(--color-border)",borderRadius:"var(--radius-lg)",
    color:"var(--color-text-secondary)",fontSize:"var(--fs-xs)",cursor:"pointer",
    fontFamily:"var(--font-body)",transition:"all 150ms ease" },
  modBtnActive: { borderColor:"var(--color-accent)",color:"var(--color-accent)",
    background:"var(--color-accent-subtle)" },
  attachBtn: { display:"flex",alignItems:"center",gap:"var(--sp-2)",
    padding:"var(--sp-1) var(--sp-3)",background:"transparent",
    borderWidth:"1px",borderStyle:"solid",borderColor:"var(--color-border)",
    borderRadius:"var(--radius-lg)",color:"var(--color-text-secondary)",
    fontSize:"var(--fs-xs)",cursor:"pointer",fontFamily:"var(--font-body)",
    maxWidth:"200px" },
  attachBtnOn: { borderColor:"var(--color-accent)",color:"var(--color-text-primary)" },
  attachName: { overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap",
    maxWidth:"110px",display:"inline-block",verticalAlign:"middle" },
  chipX: { background:"transparent",border:"none",cursor:"pointer",
    color:"inherit",fontSize:"1rem",lineHeight:1,padding:"0 0 0 4px",
    fontFamily:"var(--font-body)" },
  vadBar: { display:"flex",alignItems:"center",gap:"3px",height:"32px" },
  vadSegment: { width:"4px",borderRadius:"2px",
    background:"var(--color-accent)",transition:"height 80ms ease" },
  mic: { width:"76px",height:"76px",borderRadius:"50%",
    borderWidth:"2px",borderStyle:"solid",borderColor:"var(--color-border)",
    background:"var(--color-bg-input)",color:"var(--color-text-primary)",
    cursor:"pointer",display:"flex",alignItems:"center",justifyContent:"center",
    transition:"all 180ms ease",flexShrink:0,userSelect:"none",touchAction:"none" },
  micRec: { borderColor:"var(--color-error)",background:"rgba(239,68,68,.1)",
    color:"var(--color-error)",animation:"vp 1.2s ease-in-out infinite" },
  micPlay: { borderColor:"var(--color-accent)",background:"var(--color-accent-subtle)",
    color:"var(--color-accent)" },
  micAuto: { borderColor:"var(--color-accent)",
    animation:"apulse 2s ease-in-out infinite" },
  micBusy: { opacity:.45,cursor:"not-allowed" },
  spin: { display:"inline-block",width:"22px",height:"22px",borderRadius:"50%",
    borderWidth:"3px",borderStyle:"solid",borderColor:"var(--color-border)",
    borderTopColor:"var(--color-text-secondary)",animation:"vs .8s linear infinite" },
  label: { fontSize:"var(--fs-sm)",color:"var(--color-text-secondary)",
    fontWeight:"var(--fw-medium)",minHeight:"22px",display:"flex",alignItems:"center",
    textAlign:"center" },
  preview: { width:"100%",maxWidth:"520px",display:"flex",flexDirection:"column",
    gap:"var(--sp-2)",padding:"var(--sp-3)",background:"var(--color-bg-input)",
    borderWidth:"1px",borderStyle:"solid",borderColor:"var(--color-border)",
    borderRadius:"var(--radius-sm)" },
  preUser: { display:"flex",gap:"var(--sp-2)",alignItems:"flex-start",
    fontSize:"var(--fs-xs)",color:"var(--color-text-secondary)" },
  preAi: { display:"flex",gap:"var(--sp-2)",alignItems:"flex-start",
    fontSize:"var(--fs-xs)",color:"var(--color-text-primary)" },
  dot: { width:"8px",height:"8px",borderRadius:"50%",background:"var(--color-accent)",
    flexShrink:0,marginTop:"3px",boxShadow:"var(--shadow-accent-glow)" },
  hint: { margin:0,fontSize:"var(--fs-xs)",color:"var(--color-text-placeholder)",
    textAlign:"center" },
};