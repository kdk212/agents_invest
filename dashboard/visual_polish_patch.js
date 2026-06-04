(() => {
  function translateStatus() {
    const node = document.getElementById("overallText");
    if (!node) return;
    const map = new Map([
      ["서비스 prism_batch_cycle_complete", "추천주 갱신 완료"],
      ["서비스 running_prism_batch", "추천주 계산 중"],
      ["서비스 prism_batch_cycle_failed", "추천주 갱신 실패"],
      ["prism_batch_cycle_complete", "추천주 갱신 완료"],
      ["running_prism_batch", "추천주 계산 중"],
      ["prism_batch_cycle_failed", "추천주 갱신 실패"],
    ]);
    for (const [from, to] of map.entries()) {
      if (node.textContent.includes(from)) node.textContent = node.textContent.replace(from, to);
    }
  }

  function addStatusLegend() {
    const panel = document.querySelector(".hero-panel");
    if (!panel || document.getElementById("statusLegend")) return;
    const legend = document.createElement("div");
    legend.id = "statusLegend";
    legend.className = "status-legend";
    legend.innerHTML = `
      <div><strong>포트</strong><span>보유 포트폴리오 구성 여부</span></div>
      <div><strong>백테</strong><span>백테스트 결과 반영 여부</span></div>
      <div><strong>런타임</strong><span>서버 실행 상태</span></div>
      <div><strong>운영</strong><span>모의운영 안전 상태</span></div>
    `;
    panel.appendChild(legend);
  }

  const parsePctLocal = (value) => {
    const number = Number(String(value ?? "0").replace("%", ""));
    return Number.isFinite(number) ? number / 100 : 0;
  };

  const formatPctLocal = (value) => `${(value * 100).toFixed(2)}%`;

  async function loadPortfolioForChart() {
    try {
      const response = await fetch("./portfolio_status.json", { cache: "no-store" });
      return response.ok ? await response.json() : null;
    } catch (_error) {
      return null;
    }
  }

  function drawPortfolioCanvasWithDateAxis(curve, portfolio = null) {
    const canvas = document.getElementById("portfolioCanvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    const left = 46;
    const right = canvas.width - 46;
    const top = 28;
    const bottom = canvas.height - 52;

    ctx.strokeStyle = "#d9e0dc";
    ctx.lineWidth = 1;
    for (let y = top + 12; y <= bottom; y += 42) {
      ctx.beginPath();
      ctx.moveTo(left, y);
      ctx.lineTo(right, y);
      ctx.stroke();
    }

    if (!curve || !curve.length) {
      ctx.fillStyle = "#62706c";
      ctx.font = "15px system-ui";
      ctx.fillText("포트폴리오 수익률 데이터 대기", left, 130);
      return;
    }

    const values = curve.map((row) => parsePctLocal(row.return_pct));
    const min = Math.min(...values, 0);
    const max = Math.max(...values, 0.01);
    const range = max - min || 0.01;

    ctx.strokeStyle = "#287c61";
    ctx.lineWidth = 3;
    ctx.beginPath();
    values.forEach((value, index) => {
      const x = left + ((right - left) * index) / Math.max(values.length - 1, 1);
      const y = bottom - ((value - min) / range) * (bottom - top);
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    const startDate = curve[0]?.date || portfolio?.start_date || "";
    const latestDate = curve[curve.length - 1]?.date || portfolio?.end_date || "";

    ctx.fillStyle = "#17201d";
    ctx.font = "13px system-ui";
    ctx.textAlign = "left";
    ctx.fillText(`최저 ${formatPctLocal(min)} · 최고 ${formatPctLocal(max)}`, left, 18);
    ctx.fillText(startDate, left, canvas.height - 14);

    ctx.textAlign = "right";
    ctx.fillText(latestDate, right, canvas.height - 14);

    ctx.fillStyle = "#62706c";
    ctx.font = "11px system-ui";
    ctx.textAlign = "left";
    ctx.fillText("시작", left, canvas.height - 31);
    ctx.textAlign = "right";
    ctx.fillText("최근", right, canvas.height - 31);
    ctx.textAlign = "left";
  }

  async function redrawPortfolioChartAxis() {
    const portfolio = await loadPortfolioForChart();
    if (!portfolio) return;
    drawPortfolioCanvasWithDateAxis(portfolio.equity_curve || [], portfolio);
  }

  function addStyle() {
    if (document.getElementById("visual-polish-style")) return;
    const style = document.createElement("style");
    style.id = "visual-polish-style";
    style.textContent = `
      .hero { grid-template-columns: minmax(0, 1fr) 390px; min-height: 260px; }
      h1#page-title { font-size: clamp(38px, 5.8vw, 68px); line-height: 1.05; white-space: nowrap; }
      .subtitle { max-width: 840px; font-size: 16px; line-height: 1.55; }
      .hero-panel { gap: 10px; }
      #statusCanvas { max-height: 150px; }
      .status-legend { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; padding-top: 4px; }
      .status-legend div { border: 1px solid var(--line); background: var(--surface-3); border-radius: 6px; padding: 8px; min-width: 0; }
      .status-legend strong { display: block; font-size: 12px; color: var(--text); }
      .status-legend span { display: block; margin-top: 2px; font-size: 11px; line-height: 1.35; color: var(--muted); }
      .candidate-score small { display: block; color: var(--muted); font-size: 11px; margin-top: 2px; font-weight: 700; }
      .candidate-facts { grid-template-columns: repeat(4, minmax(0, 1fr)); }
      @media (max-width: 960px) { .hero { grid-template-columns: 1fr; } h1#page-title { white-space: normal; } }
    `;
    document.head.appendChild(style);
  }

  function run() {
    addStyle();
    addStatusLegend();
    translateStatus();
    redrawPortfolioChartAxis();
    setTimeout(translateStatus, 900);
    setTimeout(redrawPortfolioChartAxis, 700);
    setTimeout(redrawPortfolioChartAxis, 1600);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run);
  else run();
})();
