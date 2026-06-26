/**
 * src/pages/AnalysePage.jsx
 *
 * Public read-only analytics dashboard at /analyse.
 * No authentication required — accessible directly by hackathon judges.
 *
 * Shows live aggregate statistics from all four Hipocampus memory tiers:
 *   Working (Redis) · Episodic · Semantic · Procedural (all PostgreSQL)
 *
 * Auto-refreshes every 30 seconds. Never displays raw prompts, responses,
 * or user identifiers.
 *
 * Used by: src/App.jsx (public route, no ProtectedRoute wrapper).
 */

import { useCallback, useEffect, useState } from "react";

// ---------------------------------------------------------------------------
// Data fetching
// ---------------------------------------------------------------------------

async function fetchStats() {
  const res = await fetch("/api/v1/analyse");
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// AnalysePage
// ---------------------------------------------------------------------------

export default function AnalysePage() {
  const [stats,   setStats]   = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);
  const [lastAt,  setLastAt]  = useState(null);

  const load = useCallback(async () => {
    try {
      const data = await fetchStats();
      setStats(data);
      setLastAt(new Date());
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load + 30 s auto-refresh
  useEffect(() => {
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <div style={s.page}>
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <header style={s.hero}>
        <div style={s.heroBadge}>QWEN CLOUD HACKATHON · TRACK 1: MEMORYAGENT</div>
        <h1 style={s.heroTitle}>Hipocampus</h1>
        <p style={s.heroSub}>Memory Analytics Dashboard</p>
        <p style={s.heroDesc}>
          Live statistics from the four-tier hippocampal memory system.
          All data is read-only. No authentication required.
        </p>
        {lastAt && (
          <p style={s.heroTs}>
            Last updated {lastAt.toLocaleTimeString()} · auto-refreshes every 30 s
          </p>
        )}
      </header>

      <main style={s.main}>
        {loading && !stats && <Spinner />}
        {error && <ErrorBox message={error} onRetry={load} />}

        {stats && (
          <>
            {/* ── Overview ───────────────────────────────────────────── */}
            <Section title="Overview">
              <div style={s.grid6}>
                <StatCard label="Users"               value={stats.overview.users}               icon="👤" />
                <StatCard label="Chats"               value={stats.overview.chats}               icon="💬" />
                <StatCard label="Messages"            value={stats.overview.messages}            icon="📝" />
                <StatCard label="Episodes"            value={stats.overview.episodes}            icon="🧩" />
                <StatCard label="Semantic Facts"      value={stats.overview.semantic_facts}      icon="🔮" />
                <StatCard label="Procedural Patterns" value={stats.overview.procedural_patterns} icon="⚙️" />
              </div>
            </Section>

            {/* ── Memory tier flow ───────────────────────────────────── */}
            <Section title="Four-Tier Memory Architecture">
              <div style={s.tierRow}>
                <TierCard
                  tier="Working"
                  storage="Redis"
                  color="#FFFFFF"
                  description="Sliding window of the last 10 messages per session. 1-hour TTL. Drives the AI context window."
                  stat="~10 msgs / session"
                  icon="⚡"
                />
                <TierArrow />
                <TierCard
                  tier="Episodic"
                  storage="PostgreSQL + pgvector"
                  color="#CCCCCC"
                  description="Every significant exchange scored by importance. Only turns scoring ≥ 0.45 are persisted."
                  stat={`${stats.overview.episodes} episodes stored`}
                  icon="📼"
                />
                <TierArrow />
                <TierCard
                  tier="Semantic"
                  storage="PostgreSQL + pgvector"
                  color="#999999"
                  description="Long-term preferences and facts extracted by Qwen-Max during the nightly sleep consolidation cycle."
                  stat={`${stats.overview.semantic_facts} facts extracted`}
                  icon="🧠"
                />
                <TierArrow />
                <TierCard
                  tier="Procedural"
                  storage="PostgreSQL + pgvector"
                  color="#666666"
                  description="Behavioural patterns learned from repeated successful interactions across sessions."
                  stat={`${stats.overview.procedural_patterns} patterns learned`}
                  icon="🔄"
                />
              </div>
            </Section>

            {/* ── Episode health ─────────────────────────────────────── */}
            <Section title="Episodic Memory Health">
              <div style={s.grid2}>
                <div style={s.card}>
                  <div style={s.cardLabel}>Promotion Rate</div>
                  <div style={s.bigNum}>{stats.episode_health.promoted_pct}%</div>
                  <div style={s.cardSub}>
                    {stats.episode_health.promoted} promoted · {stats.episode_health.pending} pending consolidation
                  </div>
                  <BarH value={stats.episode_health.promoted_pct} max={100} />
                </div>
                <div style={s.card}>
                  <div style={s.cardLabel}>Average Importance Score</div>
                  <div style={s.bigNum}>{stats.episode_health.avg_importance.toFixed(3)}</div>
                  <div style={s.cardSub}>
                    Scale 0 – 1 · threshold 0.45 to save · 0.60 to consolidate
                  </div>
                  <BarH value={stats.episode_health.avg_importance} max={1} />
                </div>
              </div>
            </Section>

            {/* ── Importance distribution ────────────────────────────── */}
            <Section title="Episode Importance Distribution">
              <div style={s.card}>
                <p style={s.cardNote}>
                  Episodes below 0.45 are discarded at write time — never stored.
                  All episodes shown here were deemed significant enough to persist.
                </p>
                <div style={s.distTable}>
                  <DistRow
                    label="Saved"
                    range="0.45 – 0.60"
                    value={stats.importance_distribution.saved}
                    total={stats.overview.episodes}
                    color="#888888"
                  />
                  <DistRow
                    label="Candidate"
                    range="0.60 – 0.80"
                    value={stats.importance_distribution.candidate}
                    total={stats.overview.episodes}
                    color="#BBBBBB"
                  />
                  <DistRow
                    label="High"
                    range="0.80 – 1.00"
                    value={stats.importance_distribution.high}
                    total={stats.overview.episodes}
                    color="#FFFFFF"
                  />
                </div>
              </div>
            </Section>

            {/* ── Semantic memory health ─────────────────────────────── */}
            <Section title="Semantic Memory Health">
              <div style={s.grid2}>
                <div style={s.card}>
                  <div style={s.cardLabel}>Confidence Distribution</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-3)", marginTop: "var(--sp-3)" }}>
                    <DistRow label="High"   range="≥ 0.80" value={stats.semantic_health.high}   total={stats.semantic_health.total || 1} color="#FFFFFF" />
                    <DistRow label="Medium" range="0.50–0.80" value={stats.semantic_health.medium} total={stats.semantic_health.total || 1} color="#AAAAAA" />
                    <DistRow label="Low"    range="< 0.50"  value={stats.semantic_health.low}    total={stats.semantic_health.total || 1} color="#555555" />
                  </div>
                </div>
                <div style={s.card}>
                  <div style={s.cardLabel}>Average Confidence</div>
                  <div style={s.bigNum}>{stats.semantic_health.avg_confidence.toFixed(3)}</div>
                  <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-3)", marginTop: "var(--sp-4)" }}>
                    <span style={s.conflictBadge}>⚡ {stats.semantic_health.conflicted}</span>
                    <span style={s.cardSub}>conflicted facts pending resolution</span>
                  </div>
                  {stats.procedural_health.total > 0 && (
                    <div style={{ marginTop: "var(--sp-4)" }}>
                      <div style={s.cardLabel}>Procedural Avg Success Rate</div>
                      <div style={{ fontSize: "var(--fs-xl)", fontWeight: "var(--fw-bold)", color: "var(--color-text-primary)", margin: "var(--sp-1) 0" }}>
                        {(stats.procedural_health.avg_success_rate * 100).toFixed(1)}%
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </Section>

            {/* ── Last 24 h ──────────────────────────────────────────── */}
            <Section title="Activity · Last 24 Hours">
              <div style={s.grid4}>
                <ActivityCard label="New Episodes" value={stats.activity_24h.new_episodes} icon="🧩" />
                <ActivityCard label="New Facts"    value={stats.activity_24h.new_facts}    icon="🔮" />
                <ActivityCard label="New Messages" value={stats.activity_24h.new_messages} icon="📝" />
                <ActivityCard label="New Chats"    value={stats.activity_24h.new_chats}    icon="💬" />
              </div>
            </Section>

            {/* ── How it works (judge note) ──────────────────────────── */}
            <Section title="How It Works">
              <div style={s.howGrid}>
                <HowStep
                  step="1"
                  title="User Sends a Message"
                  body="The message is pushed to the Redis working-memory buffer (last 10 turns, 1 h TTL). Hipocampus retrieves relevant context from all four tiers via pgvector cosine search and injects it into the Qwen-Max system prompt."
                />
                <HowStep
                  step="2"
                  title="Importance Scoring"
                  body="Every exchange is scored 0–1 using four signals: recency weight, topic frequency, cosine surprise delta from the user's semantic centroid, and an explicit-commitment multiplier (2× for 'always', 'never', 'require'). Turns below 0.45 are discarded."
                />
                <HowStep
                  step="3"
                  title="Sleep Consolidation"
                  body="A nightly Celery Beat task (or on-demand via the Memory page) sends batches of episodes to Qwen-Max for semantic extraction. Facts are embedded with text-embedding-v3 (1 024 dims) and stored in pgvector. Contradictions are flagged for user review."
                />
                <HowStep
                  step="4"
                  title="Biological Forgetting"
                  body="Promoted episodes decay at 0.96× per day. Those below 0.30 confidence after 90 days are pruned. Semantic facts retain their confidence score independently — high-signal preferences persist indefinitely."
                />
              </div>
            </Section>

            {/* Footer */}
            <footer style={s.footer}>
              <p>Hipocampus · Built for Qwen Cloud Hackathon 2026 · Track 1: MemoryAgent</p>
              <p style={{ color: "var(--color-text-placeholder)", marginTop: "var(--sp-1)" }}>
                This page is public and read-only. All data shown is aggregate — no user identifiers or message content is exposed.
              </p>
            </footer>
          </>
        )}
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Internal sub-components
// ---------------------------------------------------------------------------

function Section({ title, children }) {
  return (
    <section style={s.section}>
      <h2 style={s.sectionTitle}>{title}</h2>
      {children}
    </section>
  );
}

function StatCard({ label, value, icon }) {
  return (
    <div style={s.statCard}>
      <span style={s.statIcon}>{icon}</span>
      <div style={s.statValue}>{value.toLocaleString()}</div>
      <div style={s.statLabel}>{label}</div>
    </div>
  );
}

function TierCard({ tier, storage, color, description, stat, icon }) {
  return (
    <div style={{ ...s.tierCard, borderTopColor: color }}>
      <div style={{ fontSize: "1.5rem", marginBottom: "var(--sp-2)" }}>{icon}</div>
      <div style={{ ...s.tierName, color }}>{tier}</div>
      <div style={s.tierStorage}>{storage}</div>
      <p style={s.tierDesc}>{description}</p>
      <div style={{ ...s.tierStat, color }}>{stat}</div>
    </div>
  );
}

function TierArrow() {
  return (
    <div style={s.arrow} aria-hidden="true">→</div>
  );
}

function DistRow({ label, range, value, total, color }) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <div style={s.distRow}>
      <div style={s.distMeta}>
        <span style={{ ...s.distLabel, color }}>{label}</span>
        <span style={s.distRange}>{range}</span>
        <span style={s.distCount}>{value} ({pct}%)</span>
      </div>
      <div style={s.barTrack}>
        <div style={{ ...s.barFill, width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

function BarH({ value, max }) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  return (
    <div style={{ ...s.barTrack, marginTop: "var(--sp-3)" }}>
      <div style={{ ...s.barFill, width: `${pct}%`, background: "#FFFFFF" }} />
    </div>
  );
}

function ActivityCard({ label, value, icon }) {
  return (
    <div style={s.actCard}>
      <span style={s.actIcon}>{icon}</span>
      <div style={s.actValue}>+{value}</div>
      <div style={s.actLabel}>{label}</div>
    </div>
  );
}

function HowStep({ step, title, body }) {
  return (
    <div style={s.howCard}>
      <div style={s.howStep}>{step}</div>
      <h3 style={s.howTitle}>{title}</h3>
      <p style={s.howBody}>{body}</p>
    </div>
  );
}

function Spinner() {
  return (
    <div style={{ display: "flex", justifyContent: "center", padding: "var(--sp-16)" }}>
      <div style={s.spinner} />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

function ErrorBox({ message, onRetry }) {
  return (
    <div style={s.errorBox}>
      <p>Failed to load stats: {message}</p>
      <button onClick={onRetry} style={s.retryBtn}>Retry</button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const s = {
  page: {
    minHeight: "100vh",
    background: "var(--color-bg-base)",
    color: "var(--color-text-primary)",
    fontFamily: "var(--font-body)",
  },

  hero: {
    padding: "var(--sp-12) var(--sp-8) var(--sp-10)",
    textAlign: "center",
    borderBottom: "1px solid var(--color-border)",
    background: "var(--color-bg-surface)",
  },
  heroBadge: {
    display: "inline-block",
    fontSize: "var(--fs-xs)",
    fontWeight: "var(--fw-bold)",
    letterSpacing: "0.12em",
    color: "var(--color-text-secondary)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-lg)",
    padding: "var(--sp-1) var(--sp-3)",
    marginBottom: "var(--sp-4)",
    textTransform: "uppercase",
  },
  heroTitle: {
    fontFamily: "var(--font-display)",
    fontSize: "clamp(2.5rem, 6vw, 4rem)",
    fontWeight: "var(--fw-bold)",
    color: "var(--color-text-primary)",
    letterSpacing: "-0.03em",
    margin: 0,
  },
  heroSub: {
    fontSize: "var(--fs-lg)",
    color: "var(--color-text-secondary)",
    margin: "var(--sp-2) 0 var(--sp-4)",
    fontWeight: "var(--fw-medium)",
  },
  heroDesc: {
    fontSize: "var(--fs-sm)",
    color: "var(--color-text-placeholder)",
    maxWidth: "480px",
    margin: "0 auto",
    lineHeight: "1.6",
  },
  heroTs: {
    fontSize: "var(--fs-xs)",
    color: "var(--color-text-placeholder)",
    marginTop: "var(--sp-4)",
  },

  main: {
    maxWidth: "1100px",
    margin: "0 auto",
    padding: "var(--sp-8) var(--sp-4) var(--sp-16)",
    display: "flex",
    flexDirection: "column",
    gap: "var(--sp-10)",
  },

  section: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--sp-4)",
  },
  sectionTitle: {
    fontFamily: "var(--font-display)",
    fontSize: "var(--fs-md)",
    fontWeight: "var(--fw-bold)",
    color: "var(--color-text-primary)",
    letterSpacing: "-0.01em",
    borderBottom: "1px solid var(--color-border)",
    paddingBottom: "var(--sp-3)",
  },

  // ── Grids ──────────────────────────────────────────────────────────────
  grid6: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))",
    gap: "var(--sp-3)",
  },
  grid2: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
    gap: "var(--sp-4)",
  },
  grid4: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
    gap: "var(--sp-3)",
  },

  // ── Stat cards ─────────────────────────────────────────────────────────
  statCard: {
    background: "var(--color-bg-surface)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-md)",
    padding: "var(--sp-4) var(--sp-3)",
    textAlign: "center",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: "var(--sp-1)",
  },
  statIcon: { fontSize: "1.4rem" },
  statValue: {
    fontFamily: "var(--font-display)",
    fontSize: "var(--fs-2xl)",
    fontWeight: "var(--fw-bold)",
    color: "var(--color-text-primary)",
    lineHeight: 1.1,
  },
  statLabel: { fontSize: "var(--fs-xs)", color: "var(--color-text-secondary)" },

  // ── Tier cards ─────────────────────────────────────────────────────────
  tierRow: {
    display: "flex",
    alignItems: "stretch",
    gap: "var(--sp-2)",
    overflowX: "auto",
    paddingBottom: "var(--sp-2)",
  },
  tierCard: {
    flex: "1 1 180px",
    minWidth: "160px",
    background: "var(--color-bg-surface)",
    border: "1px solid var(--color-border)",
    borderTop: "3px solid #FFFFFF",
    borderRadius: "var(--radius-md)",
    padding: "var(--sp-4)",
    display: "flex",
    flexDirection: "column",
    gap: "var(--sp-1)",
  },
  tierName: {
    fontFamily: "var(--font-display)",
    fontSize: "var(--fs-md)",
    fontWeight: "var(--fw-bold)",
  },
  tierStorage: {
    fontSize: "var(--fs-xs)",
    color: "var(--color-text-placeholder)",
    marginBottom: "var(--sp-2)",
  },
  tierDesc: {
    fontSize: "var(--fs-xs)",
    color: "var(--color-text-secondary)",
    lineHeight: "1.5",
    flex: 1,
  },
  tierStat: {
    fontSize: "var(--fs-xs)",
    fontWeight: "var(--fw-bold)",
    marginTop: "var(--sp-2)",
  },
  arrow: {
    display: "flex",
    alignItems: "center",
    color: "var(--color-text-placeholder)",
    fontSize: "var(--fs-md)",
    flexShrink: 0,
    padding: "0 var(--sp-1)",
  },

  // ── Generic card ───────────────────────────────────────────────────────
  card: {
    background: "var(--color-bg-surface)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-md)",
    padding: "var(--sp-5)",
  },
  cardLabel: {
    fontSize: "var(--fs-xs)",
    fontWeight: "var(--fw-bold)",
    color: "var(--color-text-secondary)",
    textTransform: "uppercase",
    letterSpacing: "0.06em",
  },
  cardSub: {
    fontSize: "var(--fs-xs)",
    color: "var(--color-text-placeholder)",
    marginTop: "var(--sp-1)",
  },
  cardNote: {
    fontSize: "var(--fs-xs)",
    color: "var(--color-text-placeholder)",
    lineHeight: "1.5",
    marginBottom: "var(--sp-4)",
  },
  bigNum: {
    fontFamily: "var(--font-display)",
    fontSize: "var(--fs-2xl)",
    fontWeight: "var(--fw-bold)",
    color: "var(--color-text-primary)",
    margin: "var(--sp-2) 0",
  },

  // ── Distribution rows ──────────────────────────────────────────────────
  distTable: { display: "flex", flexDirection: "column", gap: "var(--sp-4)" },
  distRow:   { display: "flex", flexDirection: "column", gap: "var(--sp-2)" },
  distMeta:  { display: "flex", alignItems: "center", gap: "var(--sp-3)" },
  distLabel: { fontSize: "var(--fs-sm)", fontWeight: "var(--fw-bold)", minWidth: "80px" },
  distRange: { fontSize: "var(--fs-xs)", color: "var(--color-text-placeholder)", flex: 1 },
  distCount: { fontSize: "var(--fs-xs)", color: "var(--color-text-secondary)" },

  // ── Bar chart ──────────────────────────────────────────────────────────
  barTrack: {
    height: "6px",
    background: "var(--color-bg-input)",
    borderRadius: "var(--radius-lg)",
    overflow: "hidden",
  },
  barFill: {
    height: "100%",
    borderRadius: "var(--radius-lg)",
    transition: "width 800ms cubic-bezier(0.4, 0, 0.2, 1)",
  },

  // ── Activity cards ─────────────────────────────────────────────────────
  actCard: {
    background: "var(--color-bg-surface)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-md)",
    padding: "var(--sp-4)",
    textAlign: "center",
    display: "flex",
    flexDirection: "column",
    gap: "var(--sp-1)",
    alignItems: "center",
  },
  actIcon:  { fontSize: "1.2rem" },
  actValue: {
    fontFamily: "var(--font-display)",
    fontSize: "var(--fs-xl)",
    fontWeight: "var(--fw-bold)",
    color: "var(--color-text-primary)",
  },
  actLabel: { fontSize: "var(--fs-xs)", color: "var(--color-text-secondary)" },

  // ── How it works ───────────────────────────────────────────────────────
  howGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
    gap: "var(--sp-4)",
  },
  howCard: {
    background: "var(--color-bg-surface)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-md)",
    padding: "var(--sp-5)",
    display: "flex",
    flexDirection: "column",
    gap: "var(--sp-2)",
  },
  howStep: {
    width: "28px",
    height: "28px",
    borderRadius: "50%",
    border: "1px solid var(--color-accent)",
    color: "var(--color-accent)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontFamily: "var(--font-display)",
    fontWeight: "var(--fw-bold)",
    fontSize: "var(--fs-sm)",
    flexShrink: 0,
  },
  howTitle: {
    fontFamily: "var(--font-display)",
    fontSize: "var(--fs-sm)",
    fontWeight: "var(--fw-bold)",
    color: "var(--color-text-primary)",
  },
  howBody: {
    fontSize: "var(--fs-xs)",
    color: "var(--color-text-secondary)",
    lineHeight: "1.6",
  },

  // ── Misc ───────────────────────────────────────────────────────────────
  conflictBadge: {
    display: "inline-flex",
    alignItems: "center",
    gap: "var(--sp-1)",
    padding: "var(--sp-1) var(--sp-3)",
    background: "rgba(251, 191, 36, 0.10)",
    border: "1px solid rgba(251, 191, 36, 0.25)",
    borderRadius: "var(--radius-lg)",
    color: "var(--color-warning)",
    fontWeight: "var(--fw-bold)",
    fontSize: "var(--fs-sm)",
  },
  footer: {
    borderTop: "1px solid var(--color-border)",
    paddingTop: "var(--sp-6)",
    textAlign: "center",
    fontSize: "var(--fs-xs)",
    color: "var(--color-text-secondary)",
    lineHeight: "1.6",
  },
  spinner: {
    width: "28px",
    height: "28px",
    border: "2px solid var(--color-border)",
    borderTopColor: "var(--color-accent)",
    borderRadius: "50%",
    animation: "spin 0.8s linear infinite",
  },
  errorBox: {
    padding: "var(--sp-6)",
    background: "rgba(248,113,113,0.06)",
    border: "1px solid rgba(248,113,113,0.2)",
    borderRadius: "var(--radius-md)",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "var(--sp-4)",
    fontSize: "var(--fs-sm)",
    color: "var(--color-error)",
  },
  retryBtn: {
    padding: "var(--sp-2) var(--sp-4)",
    background: "transparent",
    border: "1px solid var(--color-error)",
    borderRadius: "var(--radius-sm)",
    color: "var(--color-error)",
    fontSize: "var(--fs-sm)",
    cursor: "pointer",
    fontFamily: "var(--font-body)",
    flexShrink: 0,
  },
};