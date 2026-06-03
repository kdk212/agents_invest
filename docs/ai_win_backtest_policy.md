# AI WIN Backtest Selection Policy

AI WIN 운영 최적화는 과거 수익률을 그대로 믿기보다, 실전 운용 방식과 같은 조건으로 추천 개수(top-N)를 고릅니다.

## 기본 백테스트 기간

자동 운영 기본값은 다음 세 구간입니다.

- 최근 24개월
- 최근 18개월
- 최근 12개월

3개월, 6개월처럼 짧은 구간은 단기 급등장에 과최적화될 수 있어 자동 운영 기본값에서 제외합니다. 필요할 때만 수동 실험값으로 넣습니다.

예시:

```bash
PERIOD_MONTHS=24,18,12,6,3 bash scripts/run_ai_win_rebuild_and_validate.sh
```

## 체결 가정

- 전일 종가까지의 데이터로 추천 신호를 만듭니다.
- 다음 거래일 시초가에 매수한다고 가정합니다.
- 매도는 당일 장중 고가/저가를 기준으로 판단합니다.
- 같은 날 손절가와 목표가가 모두 닿으면 보수적으로 손절을 먼저 반영합니다.
- 매도 당일 같은 종목의 재진입은 막습니다.

## 추천 사유 확인

특정 종목이 왜 추천됐는지는 아래 명령으로 확인합니다.

```bash
.venv/bin/python scripts/explain_recommendation.py 001820
```

삼화콘덴서처럼 납득이 어려운 종목은 이 출력의 `recommendation_reason`과 `score_components`를 먼저 봅니다.
