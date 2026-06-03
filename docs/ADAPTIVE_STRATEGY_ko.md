# 백테스트 기반 추천 로직 자동 보완

`ai_win_invest` 저장소의 추천 아이디어를 `agents_invest`에 직접 복사해 수정하지 않고, PRISM 후보 결과 위에 덧씌우는 방식으로 통합했습니다.

## 적용 방식

1. PRISM 원본이 오전/오후 후보를 생성합니다.
2. `runtime.prism_adaptive_strategy`가 후보별 과거 가격을 읽습니다.
3. 아래 지표로 `ai_win_score`를 계산합니다.
   - 20/60/120일 모멘텀
   - 20/60일 추세
   - 최근 상승일 비율
   - 눌림 후 회복력
   - 모멘텀 가속도
   - 거래대금 변화
   - 변동성/고점 대비 낙폭/과열 리스크
4. PRISM 점수와 `ai_win_score`를 합쳐 `adaptive_profit_score`를 만듭니다.
5. 손절/익절 값은 백테스트로 선택된 파라미터를 반영합니다.
6. 대시보드와 텔레그램은 보정된 JSON을 그대로 읽습니다.

기본 가중치:

```text
PRISM 점수 45%
ai_win_invest 방식 점수 55%
```

## 백테스트 자동 보완

`runtime/adaptive_strategy.json` 파일이 현재 적용 파라미터입니다.

주간 최적화는 다음 기간을 비교합니다.

- 최근 24개월
- 최근 18개월
- 최근 12개월

각 기간에서 아래 후보를 비교합니다.

- raw score threshold
- 변동성 손절 배수
- 익절 시작 수익률
- 익절 후 트레일링 폭

정렬 기준은 수익률 극대화에 맞춰 `total_return`, `CAGR`, `Sharpe`, `MDD` 순으로 봅니다.

## EC2에서 자동 타이머 켜기

```bash
cd /opt/agents_invest
git pull
bash scripts/install_adaptive_strategy_timer.sh
```

수동으로 한 번 실행하려면:

```bash
cd /opt/agents_invest
.venv/bin/python scripts/optimize_adaptive_strategy.py --periods 24,18,12 --top-n 7 --universe-size 160
sudo systemctl restart agents-invest
```

## 확인

```bash
cd /opt/agents_invest
cat runtime/adaptive_strategy.json
bash scripts/operator_status.sh
```

대시보드의 `prism_latest_morning.json` 또는 `prism_latest_afternoon.json` 안에 아래 값이 붙으면 정상입니다.

```text
ai_win_score
ai_win_score_100
forward_quality_score
adaptive_profit_score
adaptive_strategy_source
adaptive_selected_period_months
```

## 주의

이 기능은 수익을 보장하지 않습니다. 최근 구간 최적화는 과최적화 위험이 있으므로, 실거래 전에는 paper mode 결과와 실제 체결 가능성, 거래비용, 슬리피지, 공시/뉴스 리스크를 별도로 확인해야 합니다.
