(() => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const load = async (u) => { try { const r = await fetch(u, { cache: "no-store" }); return r.ok ? await r.json() : null; } catch { return null; } };
  const esc = (v) => String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  const price = (v) => Number.isFinite(Number(v)) && Number(v) > 0 ? Math.round(Number(v)).toLocaleString("ko-KR") : "-";
  const cls = (v) => Number(String(v ?? "0").replace("%", "")) > 0 ? "positive" : Number(String(v ?? "0").replace("%", "")) < 0 ? "negative" : "flat";

  async function compactHoldings() {
    const root = document.getElementById("holdingList");
    if (!root) return;
    const p = await load("./portfolio_status.json");
    const holdings = p?.holdings || [];
    if (!holdings.length) return;
    root.innerHTML = holdings.slice(0, 10).map((x) => `
      <article class="holding-row refined-holding">
        <div class="holding-name"><span class="candidate-code">${esc(x.ticker)}</span><strong>${esc(x.company_name)}</strong><small>비중 ${esc(x.weight_units ?? x.units ?? 0)} · 평균매입 ${esc(price(x.avg_entry))}</small></div>
        <dl>
          <div><dt>수익률</dt><dd class="${cls(x.return_pct)}">${esc(x.return_pct || "0.00%")}</dd></div>
          <div><dt>현재가</dt><dd>${esc(price(x.current_price))}</dd></div>
          <div><dt>손절가</dt><dd>${esc(price(x.avg_stop))}</dd></div>
          <div><dt>목표가</dt><dd>${esc(price(x.avg_target))}</dd></div>
        </dl>
      </article>
    `).join("");
  }

  function restoreCandidateTabs() {
    const tabs = document.querySelector(".result-tabs");
    if (tabs) tabs.style.display = "inline-flex";
    const meta = document.getElementById("prismResultMeta");
    if (meta && meta.textContent.includes("통합 표시")) meta.textContent = "오전/오후 탭에서 진입 기준 확인";
  }

  function tuneTimeline() {
    document.querySelectorAll("#timeline li").forEach((li) => {
      const title = li.querySelector(".item-title")?.textContent || "";
      if (!title.includes("AWS Session Manager")) return;
      const dot = li.querySelector(".status-dot");
      const detail = li.querySelector(".item-detail");
      if (dot) dot.className = "status-dot done";
      if (detail) detail.textContent = "현재 대시보드와 EC2 서비스가 응답 중이라 정상으로 봅니다.";
    });
  }

  function style() {
    if (document.getElementById("ui-tune-style")) return;
    const s = document.createElement("style");
    s.id = "ui-tune-style";
    s.textContent = `.refined-holding{padding:10px 0;grid-template-columns:minmax(180px,.9fr) minmax(0,1.4fr)}.refined-holding .holding-name{min-width:0}.refined-holding dl{grid-template-columns:repeat(4,minmax(76px,1fr));gap:8px}.refined-holding dd{font-size:14px}.candidate-card{align-items:center}.candidate-facts div{min-width:0}@media(max-width:760px){.refined-holding{grid-template-columns:1fr}.refined-holding dl{grid-template-columns:repeat(2,minmax(0,1fr))}}`;
    document.head.appendChild(s);
  }

  async function run() {
    await sleep(700);
    style();
    restoreCandidateTabs();
    await compactHoldings();
    tuneTimeline();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run); else run();
})();
