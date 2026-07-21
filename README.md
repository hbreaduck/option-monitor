# 반도체 옵션 수급 모니터 (NVDA · MU · SKHY · SOXX)

미국 반도체 4종목의 **풋/콜 비율 · ATM IV · IV/HV · 실적 D-day**를 한 화면에서 보는 대시보드.
- **라이브 조회**: 버튼을 누른 순간의 옵션 수급 (미국 정규장에 눌러야 IV 정확)
- **자동 기록**: GitHub Actions가 미국장 시간에 자동 캡처 → 자는 동안의 IV 추이를 아침에 폰으로 확인

## 구성
| 파일 | 역할 |
|---|---|
| `options_monitor.py` | Streamlit 대시보드 (화면) |
| `monitor_core.py` | 공용 계산 로직 (IV 역산·HV·실적 등) |
| `capture.py` | 자동 캡처 스크립트 → `data/snapshots.csv`에 append |
| `.github/workflows/capture.yml` | 미국장 시간에 캡처를 자동 실행하는 cron |
| `requirements.txt` | 의존 패키지 |

## 로컬 실행
```bash
pip install -r requirements.txt
streamlit run options_monitor.py     # 대시보드
python capture.py                    # 스냅샷 1회 수동 캡처(테스트)
```

---

# 📱 클라우드 배포 (폰에서 아무 때나 보기)

> 목표: 자는 동안(미국장) 자동으로 라이브 IV를 캡처하고, 아침에 폰으로 추이를 확인.
> PC를 꺼둬도 GitHub 서버가 대신 돌아준다. **전부 무료.**

## 1단계 — GitHub 계정 & 저장소
1. https://github.com 에서 계정 생성(이미 있으면 생략)
2. 우측 상단 **＋ → New repository**
   - Repository name: 예) `option-monitor`
   - **Private** 선택해도 됨 (Actions·Streamlit Cloud 모두 무료 지원)
   - **Add a README 등은 체크하지 말 것** (빈 저장소로 생성)
3. 생성 후 나오는 저장소 주소를 복사 (예: `https://github.com/hbreaduck/option-monitor.git`)

## 2단계 — 이 폴더를 GitHub에 올리기
이 폴더(`C:\workspace\option`)에서 터미널을 열고:
```bash
git init
git add .
git commit -m "init: 반도체 옵션 수급 모니터"
git branch -M main
git remote add origin https://github.com/hbreaduck/option-monitor.git
git push -u origin main
```
> Windows에 git이 없으면 https://git-scm.com 에서 설치. push 때 GitHub 로그인 창이 뜨면 로그인.

## 3단계 — 자동 캡처(Actions) 켜기
1. GitHub 저장소 → **Actions** 탭 → "I understand my workflows, enable them" 클릭
2. 왼쪽 **capture-snapshots** → **Run workflow**(수동 실행)로 한 번 테스트
3. 성공하면 `data/snapshots.csv`에 새 줄이 커밋됨. 이후엔 **미국장 시간에 자동으로** 하루 3번 캡처
   - 캡처 시각(KST): **00:00 / 02:30 / 04:55** (마감 직전이 하루치 완성 ⭐)
   - ⚠️ GitHub cron은 몇 분~십몇 분 지연될 수 있음(정상). 미국 공휴일엔 직전 값이 기록될 수 있음.

## 4단계 — Streamlit Cloud 배포 (폰 접속용 URL)
1. https://share.streamlit.io 접속 → **GitHub으로 로그인**
2. **Create app → Deploy a public app from GitHub**
   - Repository: `hbreaduck/option-monitor`
   - Branch: `main`
   - Main file path: `options_monitor.py`
3. **Deploy** → 1~2분 후 `https://<앱이름>.streamlit.app` 주소가 생김
4. 이 주소를 **폰 홈 화면에 추가**하면 앱처럼 열림

## 완성 후 사용법
- **아침에 폰으로** 앱 열기 → "📈 지난 밤 자동 기록"에서 자는 동안의 **IV·풋/콜 추이**를 봄
- 미국장 중 깨어 있으면 "🔄 지금 조회"로 실시간도 가능
- 자동 커밋이 매일 발생하므로 저장소가 비활성으로 꺼지지 않음(Actions cron 유지됨)

---

## 참고 (한계)
- Yahoo Finance 데이터는 약 15분 지연 · 무료 소스라 간헐적 결측 가능
- 정규장이 아니면 IV는 '최종가 기준'(참고용). 자동 캡처는 장중에 돌아 이 문제를 피함
- 이 지표들은 **심리·변동성 맥락 파악용**이며, 주가 방향 예측·매매 신호가 아님
