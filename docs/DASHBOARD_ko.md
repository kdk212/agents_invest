# 운영 대시보드 홈페이지

`dashboard/` 폴더는 agents_invest 진행상황과 운영 상태를 확인하는 정적 홈페이지입니다.

## GitHub Pages 주소

GitHub Pages가 활성화되면 기본 주소는 다음 형식입니다.

```text
https://kdk212.github.io/agents_invest/
```

실행 방법:

1. GitHub 저장소의 `Actions` 탭으로 이동합니다.
2. `pages-dashboard` 워크플로우를 선택합니다.
3. `Run workflow`를 실행합니다.
4. 완료 후 워크플로우 Summary 또는 `Settings > Pages`에서 실제 주소를 확인합니다.

저장소가 private이면 GitHub 요금제/설정에 따라 Pages가 제한될 수 있습니다. 이 경우 AWS EC2 방식으로 대시보드를 열어두는 것이 안정적입니다.

## AWS EC2에서 24시간 대시보드 열기

PC가 꺼져 있어도 보려면 EC2에서 정적 파일을 서빙합니다. 앱 실행은 `agents-invest` systemd 서비스가 담당하고, 대시보드는 별도 HTTP 서버나 nginx가 담당합니다.

간단 확인용:

```bash
cd /opt/agents_invest
.venv/bin/python scripts/export_dashboard_status.py --output dashboard/status.json
python3 -m http.server 8080 --directory dashboard
```

EC2 Security Group에서 8080 포트를 본인 IP에만 열면 다음 주소로 확인할 수 있습니다.

```text
http://EC2_PUBLIC_IP:8080/
```

운영용으로는 nginx를 권장합니다.

```bash
sudo apt-get install -y nginx
sudo tee /etc/nginx/sites-available/agents-invest-dashboard >/dev/null <<'EOF'
server {
    listen 80;
    server_name _;
    root /opt/agents_invest/dashboard;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }
}
EOF
sudo ln -sf /etc/nginx/sites-available/agents-invest-dashboard /etc/nginx/sites-enabled/agents-invest-dashboard
sudo nginx -t
sudo systemctl restart nginx
```

이후 주소:

```text
http://EC2_PUBLIC_IP/
```

## 상태 갱신

대시보드는 `dashboard/status.json`을 읽습니다. 비밀값 원문은 포함하지 않습니다.

수동 갱신:

```bash
cd /opt/agents_invest
.venv/bin/python scripts/export_dashboard_status.py --output dashboard/status.json
```

5분마다 자동 갱신하려면 cron을 사용할 수 있습니다.

```bash
crontab -e
```

추가할 줄:

```text
*/5 * * * * cd /opt/agents_invest && .venv/bin/python scripts/export_dashboard_status.py --output dashboard/status.json >/tmp/agents-invest-dashboard.log 2>&1
```

## 대시보드가 보여주는 것

- 운영 모드: paper/live
- PRISM 통합 상태
- Kill Switch 상태
- Paper validation 상태
- 비밀값 존재 여부 개수
- RiskGovernor/Startup Safety 상태
- 성과 피드백 준비 상태
- GitHub Actions, 체크리스트 이슈, AWS 콘솔 바로가기

## 주의

- 대시보드는 수익을 보장하지 않습니다.
- 실계좌 자동매매는 paper 검증, Telegram 알림, Kill Switch, RiskGovernor 확인 전까지 켜지 않습니다.
- EC2 보안 그룹에서 대시보드 포트는 가능하면 본인 IP만 허용합니다.
