(() => {
  function patchTimeline() {
    const doneTitles = [
      "AWS Session Manager 복구",
      "PRISM 원본 통합",
      "EC2 24시간",
      "EC2 24시간 paper 설치",
      "EC2 24시간 모의운영 설치",
    ];
    document.querySelectorAll("#timeline li").forEach((li) => {
      const title = li.querySelector(".item-title")?.textContent || "";
      if (!doneTitles.some((target) => title.includes(target))) return;
      const dot = li.querySelector(".status-dot");
      const detail = li.querySelector(".item-detail");
      if (dot) dot.className = "status-dot done";
      if (detail && title.includes("AWS Session Manager")) detail.textContent = "EC2 접속과 대시보드 응답 확인 완료";
      if (detail && title.includes("PRISM")) detail.textContent = "prism-insight 폴더 확인 완료";
      if (detail && title.includes("EC2 24시간")) detail.textContent = "systemd 서비스와 nginx 대시보드 동작 확인 완료";
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => setTimeout(patchTimeline, 800));
  else setTimeout(patchTimeline, 800);
})();
