# 운영 대시보드 홈페이지

`dashboard/` 폴더는 agents_invest 진행상황과 운영 상태를 확인하는 정적 홈페이지입니다.

현재 저장소 `kdk212/agents_invest`는 private 저장소입니다. 그래서 GitHub Pages는 GitHub 요금제/저장소 설정에 따라 제한될 수 있습니다. PC가 꺼져 있어도 안정적으로 보려면 AWS EC2 nginx 대시보드를 주 경로로 사용하고, GitHub Pages는 가능하면 보조 경로로 사용합니다.

## 권장 주소

EC2 대시보드가 설치되면 현재 알려진 주소는 다음입니다.

```text
http://13.55.135.136/
```

아직 이 주소가 열리지 않는다면 EC2 접속 복구와 nginx 설치가 끝나지 않은 상태일 가능성이 큽니다.

현재 다음 단계:

```text
docs/NEXT_STEPS_ko.md
```

## AWS EC2에서 24시간 대시보드 열기

PC가 꺼져 있어도 보려면 EC2에서 정적 파일을 서빙합니다. 앱 실행은 `agents-invest` systemd 서비스가 담당하고, 대시보드는 nginx가 담당합니다.

먼저 Session Manager가 Online이어야 합니다. Offline이면 아래 문서를 따릅니다.

```text
docs/CLOUDSHELL_COPY_PASTE_SSM_ROLE_COMMAND_ko.md
docs/SSM_SESSION_MANAGER_TROUBLESHOOTING_ko.md
```

부트스트랩이 끝난 EC2에서 다음 명령을 실행합니다.

```bash
cd /opt/agents_invest
sudo bash deploy/aws/install_dashboard_nginx.sh
```

EC2 Security Group에서 80 포트를 본인 IP에만 열면 다음 주소로 확인할 수 있습니다.

```text
http://13.55.135.136/
```

다른 포트를 쓰고 싶으면 다음처럼 실행합니다.

```bash
cd /opt/agents_invest
sudo DASHBOARD_PORT=8080 bash deploy/aws/install_dashboard_nginx.sh
```

이 경우 주소는 다음입니다.

```text
http://13.55.135.136:8080/
```

## GitHub Pages 보조 경로

GitHub Pages가 활성화되면 기본 주소는 다음 형식입니다.

```text
https://kdk212.github.io/agents_invest/
```

실행 방법:

1. GitHub 저장소의 `Actions` 탭으로 이동합니다.
2. `pages-dashboard` 워크플로우를 선택합니다.
3. `Run workflow`를 실행합니다.
4. 완료 후 워크플로우 Summary 또는 `Settings > Pages`에서 실제 주소를 확인합니다.

private 저장소에서 Pages가 실패하거나 주소가 열리지 않으면 EC2 대시보드를 사용합니다.

## 상태 갱신

대시보드는 `dashboard/status.json`을 읽습니다. 비밀값 원문은 포함하지 않습니다.

자동 설치 스크립트는 5분마다 상태를 갱신하는 cron도 함께 설치합니다.

수동 갱신:

```bash
cd /opt/agents_invest
.venv/bin/python scripts/export_dashboard_status.py --output dashboard/status.json
```

상태 생성 스크립트는 다음 정보를 내보냅니다.

- 운영 모드: paper/live
- PRISM 통합 상태
- Kill Switch 상태
- Paper validation 상태
- 비밀값 존재 여부 개수
- RiskGovernor/Startup Safety 상태
- 성과 피드백 준비 상태
- 지금 해야 할 일 링크

## 대시보드가 보여주는 것

- AWS Session Manager 복구 단계
- PRISM 통합 Actions 실행 상태
- EC2 24시간 paper 설치 상태
- 운영 모드와 live 전환 차단 상태
- Kill Switch, RiskGovernor, 비밀값, Telegram 확인 상태
- GitHub Actions, 체크리스트 이슈, AWS 콘솔 바로가기

## 주의

- 대시보드는 수익을 보장하지 않습니다.
- 실계좌 자동매매는 paper 검증, Telegram 알림, Kill Switch, RiskGovernor 확인 전까지 켜지지 않습니다.
- EC2 보안 그룹에서 대시보드 포트는 가능하면 본인 IP만 허용합니다.
