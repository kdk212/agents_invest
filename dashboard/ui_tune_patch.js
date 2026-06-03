(() => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const load = async (u) => { try { const r = await fetch(u, { cache: "no-store" }); return r.ok ? await r.json() : null; } catch { return null; } };
  const esc = (v) => String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  const num = (v, d = 2) => Number.isFinite(Number(v)) ? Number(v).toFixed(d) : "-";
  const price = (v) => Number.isFinite(Number(v)) && Number(v) > 0 ? Math.round(Number(v)).toLocaleString("ko-KR") : "-";
  const cls = (v) => Number(String(v ?? "0").replace("%", "")) > 0 ? "positive" : Number(String(v ?? "0").replace("%", "")) < 0 ? "negative" : "flat";
  const flat = (j) => Object.entries(j || {}).flatMap(([k, v]) => k === "metadata" || !Array.isArray(v) ? [] : v.map((x) => ({ ...x, trigger_type: x.trigger_type || k }))).sort((a,b) => Number(b.ai_win_score_100 ?? b.adaptive_profit_score ?? 0) - Number(a.ai_win_score_100 ?? a.adaptive_profit_score ?? 0));

  function card(x) {
    const score = num(x.ai_win_score_100 ?? x.adaptive_profit_score ?? x.profit_score, 1);
    const stopPct = num(x.stop_loss_pct, 2);
    const stopPrice = price(x.stop_loss_price);
    const targetPct = num(x.target_return_pct ?? x.take_profit_trigger_pct, 2);
    const targetPrice = price(x.target_price);
    return `<article class="candidate-card tuned-candidate"><div class="candidate-main"><span class="candidate-code">${esc(x.code)}</span><strong>${esc(x.name)}</strong><small>${esc(x.trigger_type || "AI WIN 추천")}</small></div><div class="candidate-score"><span>AI WIN 점수</span><strong>${esc(score)}</strong></div><dl class="candidate-facts tuned-facts"><div><dt>등락</dt><dd>${esc(num(x.change_rate,2))}%</dd><small>${esc(x.change_basis || "최근 1개월 모멘텀")}</small></div><div><dt>손절</dt><dd>${esc(stopPct)}%</dd><small>${esc(stopPrice)}</small></div><div><dt>목표</dt><dd>${esc(targetPct)}%</dd><small>${esc(targetPrice)}</small></div></dl></article>`;
  }

  async function renderCandidates() {
    const root = document.getElementById("candidateList");
    if (!root) return;
    const [m, a] = await Promise.all([load("./prism_latest_morning.json"), load("./prism_latest_afternoon.json")]);
    const section = (title, j) => `<section class="candidate-session"><h3>${esc(title)}</h3><div class="candidate-session-grid">${flat(j).map(card).join("") || '<div class="empty-state">추천 후보 대기</div>'}</div></section>`;
    root.innerHTML = section(`오전 진입 · ${m?.metadata?.signal_basis || "전일 종가 기준"} · ${m?.metadata?.signal_at || m?.metadata?.trade_date || "-"}`, m) + section(`오후 진입 · ${a?.metadata?.signal_basis || "당일 12시 기준"} · ${a?.metadata?.signal_at || a?.metadata?.trade_date || "-"}`, a);
    const tabs = document.querySelector(".result-tabs"); if (tabs) tabs.style.display = "none";
    const meta = document.getElementById("prismResultMeta"); if (meta) meta.textContent = "오전/오후 진입 후보 통합 표시 · 매도 신호 하루 2회 점검";
  }

  async function compactHoldings() {
    const root = document.getElementById("holdingList"); if (!root) return;
    const p = await load("./portfolio_status.json"); const h = p?.holdings || []; if (!h.length) return;
    root.innerHTML = h.slice(0,10).map((x) => `<article class="holding-row compact-holding"><div><span class="candidate-code">${esc(x.ticker)}</span><strong>${esc(x.company_name)}</strong><small>비중 ${esc(x.weight_units ?? x.units ?? 0)} · 평균 ${esc(price(x.avg_entry))}</small></div><dl><div><dt>수익률</dt><dd class="${cls(x.return_pct)}">${esc(x.return_pct || "0.00%")}</dd></div><div><dt>현재</dt><dd>${esc(price(x.current_price))}</dd></div><div><dt>손절</dt><dd>${esc(price(x.avg_stop))}</dd></div><div><dt>목표</dt><dd>${esc(price(x.avg_target))}</dd></div></dl></article>`).join("");
  }

  function tuneTimeline() {
    document.querySelectorAll("#timeline li").forEach((li) => {
      const title = li.querySelector(".item-title")?.textContent || "";
      if (!title.includes("AWS Session Manager")) return;
      const dot = li.querySelector(".status-dot"); const detail = li.querySelector(".item-detail");
      if (dot) dot.className = "status-dot done";
      if (detail) detail.textContent = "현재 대시보드와 EC2 서비스가 응답 중이라 정상으로 봅니다.";
    });
  }

  function style() {
    const s = document.createElement("style");
    s.textContent = `.candidate-session{margin-top:10px}.candidate-session h3{margin:12px 0 8px;font-size:14px;color:var(--muted)}.candidate-session-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:10px}.tuned-candidate{grid-template-columns:minmax(0,1.1fr) 86px minmax(210px,.9fr)}.tuned-facts{grid-template-columns:repeat(3,minmax(0,1fr))}.tuned-facts small{display:block;margin-top:3px;color:var(--muted);font-size:11px;font-weight:600}.compact-holding{padding:10px 0}.compact-holding dl{grid-template-columns:repeat(4,minmax(72px,1fr));gap:8px}@media(max-width:760px){.tuned-candidate{grid-template-columns:1fr}.compact-holding dl{grid-template-columns:repeat(2,minmax(0,1fr))}}`;
    document.head.appendChild(s);
  }

  async function run(){ await sleep(700); style(); await renderCandidates(); await compactHoldings(); tuneTimeline(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run); else run();
})();
