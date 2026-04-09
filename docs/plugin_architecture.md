# Plugin Architecture — 운영 환경을 위한 Drift Plugin 설계

> 이 문서는 13개 drift plugin을 운영 환경(실시간 차트, 점진 데이터, 동시성, 재분석)에서
> 안정적으로 동작시키기 위한 아키텍처를 정의한다.
>
> 참조: `drift_framework/docs/design_principles.md` 20장(Intake/Subgroup 분리), 21장(Plugin 책임 분리)

---

## 1. 문제 정의

오픈소스 drift 라이브러리는 `f(data) → drift yes/no` 형태의 단발성 분석만 제공한다.
운영 환경에서는 이것만으로 충분하지 않다. 다음 문제들이 동시에 발생한다.

| 운영 환경의 요구 | 오픈소스의 한계 |
|---|---|
| 데이터가 5분마다 조금씩 도착한다 | 일괄 입력만 가정 |
| 데이터가 부족해도 차트가 멈추면 안 된다 | 차트 개념 없음 |
| 분석 도중에 차트 요청이 들어온다 | 동시성 고려 없음 |
| 같은 drift를 매 cycle 다시 보고하면 안 된다 | stateless, 이력 없음 |
| 파라미터를 바꾸고 재분석할 수 있어야 한다 | 지원 안 함 |
| baseline이 cycle마다 흔들리면 안 된다 | 한 번만 호출하니 문제 없음 |

이 문서는 위 문제들을 **plugin 아키텍처 수준에서 한 번에** 해결하는 표준 패턴을 정의한다.

---

## 2. 핵심 아키텍처

### 2.1 두 책임의 분리

plugin은 **표시**와 **분석** 두 책임을 별도 함수로 가진다.

```
┌─────────────────────────────────────────────────────┐
│  Framework                                           │
│                                                      │
│  scheduler ──(매 cycle)──► plugin.analyze(new_data)  │
│                                                      │
│  Flask worker ──(차트 요청)──► plugin.get_chart_payload() │
│                                                      │
│  두 호출은 서로 다른 스레드에서 독립적으로 발생한다.       │
└─────────────────────────────────────────────────────┘
```

| 책임 | 함수 | 트리거 | 입력 | 출력 |
|---|---|---|---|---|
| **표시** | `get_chart_payload()` | 차트 polling (Flask 워커) | cache 스냅샷 | raw + layer + events |
| **분석** | `analyze(new_data)` | scheduler cycle | 새 subgroup 슬라이스 | 새 drift events |

**핵심 효과**: 분석이 못 돌아도(데이터 부족 등) 표시는 정상 동작한다. 차트는 raw 데이터가 cache에 들어간 순간부터 즉시 그려진다.

### 2.2 analyze() 3단계 패턴

`analyze()`는 동시성 안전을 위해 반드시 3단계로 구성한다.

```
┌─────────────────────────────────────────────────────────┐
│ analyze(new_data)                                        │
│                                                          │
│ ┌──────────────────────────────┐                         │
│ │ 1단계: 누적 + 스냅샷 (락 안) │  ← 짧음 (ms 단위)       │
│ │  cache.append_and_snapshot() │                         │
│ │  → snapshot (raw 복사본)     │                         │
│ └──────────────────────────────┘                         │
│               │                                          │
│               ▼                                          │
│ ┌──────────────────────────────┐                         │
│ │ 2단계: 알고리즘 실행 (락 밖) │  ← 길 수 있음 (초 단위)  │
│ │  _run_algorithm(snapshot)    │                         │
│ │  → (events, layer_rows)     │                         │
│ └──────────────────────────────┘                         │
│               │                                          │
│               ▼                                          │
│ ┌──────────────────────────────┐                         │
│ │ 3단계: 커밋 (락 안)          │  ← 짧음 (ms 단위)       │
│ │  cache.commit_analysis()     │                         │
│ └──────────────────────────────┘                         │
└─────────────────────────────────────────────────────────┘
```

**왜 3단계인가**: 알고리즘(2단계)이 수백 ms~수 초 걸릴 수 있다. 이 동안 락을 잡고 있으면 차트 polling(`get_chart_payload()`)이 멈춘다. 락은 1단계와 3단계에서만 짧게 잡아 UI 응답성을 보장한다.

### 2.3 raw / layer 분리

PluginCache는 두 종류의 데이터를 **별도로** 보관한다.

| 구분 | 저장소 | 불변성 | 내용 | 예시 |
|---|---|---|---|---|
| **raw** | `cache.data` (list) | 불변 — 한 번 적재되면 변하지 않음 | timestamp + value (+ count) | `{timestamp: ..., value: 3.14}` |
| **layer** | `cache.layer_data` (dict) | 재계산 시 교체 가능 | 알고리즘이 산출한 부가 컬럼 | `{timestamp: ..., t2: 5.2, ucl: 7.8}` |

**왜 분리하는가**:
1. 재분석 시 raw는 보존하고 layer만 폐기하면 된다 — 데이터를 다시 받을 필요 없음
2. `get_chart_payload()`가 raw와 layer를 timestamp 기준으로 merge — 표시 시점에 합침
3. layer가 아직 없는 최신 raw도 차트에 즉시 표시됨 (꼬리에서 raw만 있는 상태는 정상)

### 2.4 누적 재실행 패턴

대부분의 알고리즘은 **매 cycle cache 전체 snapshot**에 처음부터 다시 실행한다.

```python
# analyze()가 받는 new_data는 이번 cycle의 새 슬라이스 (예: 3 rows)
# 하지만 알고리즘은 snapshot 전체 (예: 200 rows)로 실행한다
snapshot = self.cache.append_and_snapshot(new_data.to_dict("records"))
events, layer_rows = self._run_algorithm(snapshot)  # 전체 재실행
self.cache.commit_analysis(layer_rows, events, replace_events=True)
```

**왜 전체 재실행인가**: windowed 알고리즘(hotelling, ks-test 등)은 슬라이딩 윈도우를 쓰며, 그룹화/peak 선택이 데이터 길이에 따라 달라질 수 있다. 이번 cycle의 new_data만으로는 정확한 결과를 낼 수 없다. 전체 재실행은 단순하고, 결과가 항상 "현재 snapshot에 대한 one-shot 결과"와 일치한다.

**`replace_events=True`**: 매 cycle 전체 재실행이므로 events도 전체가 새로 나온다. 기존 events에 append하면 중복이 쌓이므로, cache의 events를 통째로 교체한다.

**dedup**: framework에 반환하는 값은 "이번 cycle에 새로 발견된 events"만이어야 한다. `_dedupe_events(all_events, previous_events)`로 이전에 이미 보고한 events를 걸러낸다.

---

## 3. 결정성 — incremental == one-shot

누적 재실행 패턴이 올바르게 동작하려면 **결정성**이 보장되어야 한다:

> 같은 데이터 200 rows를 한 번에 넣은 결과 == 40 rows씩 5 cycle에 나눠 넣은 결과

이 조건이 깨지면 dedup이 실패하고, 같은 drift가 반복 보고되거나 사라진다.

### 3.1 결정성을 깨는 요인과 해결책

| 요인 | 문제 | 해결책 |
|---|---|---|
| **`baseline_ratio` (비율)** | `int(n * 0.5)` — cycle마다 n이 달라지면 baseline 경계 이동. 같은 row가 baseline에 들어갔다 나왔다 함 | **`baseline_points` (고정 포인트 수)** 로 전환. `baseline_end = min(baseline_points, n)` — n이 아무리 커져도 baseline 경계 고정 |
| **`np.random` (비결정적 난수)** | 서브샘플링, bootstrap에서 seed 없이 난수 사용 → 매 cycle 다른 결과 | seed 고정 또는 난수 의존 코드 제거. bootstrap 캘리브레이션은 baseline 확정 후 1회만 실행하고 결과 캐시 |
| **external state mutation** | 루프 안에서 `reference = window.copy()` — 순차 실행 자체는 결정적이지만 `reference_ratio`와 결합하면 깨짐 | `baseline_points` 고정이면 reference 시작점 고정 → 이후 mutation 순서도 고정 → 결정적 |

### 3.2 baseline_points 전환 규칙

```
기존: baseline_end = int(n * baseline_ratio)     # n에 의존 — 비결정적
전환: baseline_end = min(baseline_points, n)      # 상수 — 결정적
```

| 파라미터 | 기존 값 | 전환 값 | 근거 |
|---|---|---|---|
| hat | `baseline_ratio=0.3` | `baseline_points=30` | ADWIN은 30 포인트면 충분 |
| hotelling | `baseline_ratio → 삭제` | `baseline_points=50` | T² 공분산 추정에 50+ 필요 |
| ocdd | `baseline_ratio → 삭제` | `baseline_points=100` | IQR 안정 추정에 100 권장 |
| shap | `baseline_ratio → 삭제` | `baseline_windows=50` | 통계 프로파일 50개 윈도우 |
| mewma | `baseline_ratio → 삭제` | `baseline_points=100` | 공분산 추정, 특성 수 의존 |
| **ewma** | `baseline_ratio=0.5` | `baseline_points=50` | EWMA 평균/표준편차 추정 |
| **cusum** | `baseline_ratio=0.5` | `baseline_points=50` | 표준화 μ0/σ0 추정 |
| **ks-test** | `reference_ratio=0.5` | `baseline_points=100` | KS 검정력 확보에 100+ |
| **wasserstein** | `reference_ratio=0.5` | `baseline_points=100` | 분포 비교 안정성 |
| **c-chart** | `baseline_ratio=0.5` | `baseline_points=30` | 포아송 평균 추정 |
| **p-chart** | `baseline_ratio=0.5` | `baseline_points=30` | 이항분포 비율 추정 |
| **imr-chart** | `baseline_ratio=0.5` | `baseline_points=30` | 이동범위 평균 추정 |
| **xbar-r-chart** | `baseline_ratio=0.5` | `baseline_points=30` | X̄-R 통계량 추정 (서브그룹 단위) |

---

## 4. 동시성 모델

### 4.1 두 스레드의 접근 패턴

```
시간 ────────────────────────────────────────────►

scheduler 스레드:
  ┌─1─┐         ┌────2────┐  ┌─3─┐
  │락│         │ 계산    │  │락│         (analyze)
  └───┘         │ (락없음) │  └───┘
                └─────────┘

Flask 워커 스레드:
       ┌─락─┐                       ┌─락─┐
       │읽기│                       │읽기│  (get_chart_payload)
       └────┘                       └────┘
```

- 1단계(누적+스냅샷)와 3단계(커밋)만 락을 잡는다 — ms 단위
- 2단계(알고리즘)는 락 없이 snapshot 복사본으로 실행 — 초 단위 가능
- Flask 워커는 1단계/3단계 완료를 기다리지만 대기 시간은 ms 수준
- RLock 사용 — cache 메서드 안에서 다른 cache 메서드 호출해도 데드락 없음

### 4.2 일관성 보장

| 시점 | 차트가 보는 것 | 정상 여부 |
|---|---|---|
| 1단계 직후 ~ 3단계 직전 | raw는 최신, layer/event는 이전 cycle | 정상 — 꼬리에 raw만 있는 것은 허용 |
| 3단계 직후 | raw + layer + event 모두 최신 | 완전 일치 |
| `get_chart_payload()` 호출 시 | 한 번의 락 안에서 세 컬렉션 동시 스냅샷 | 시점 불일치 없음 |

### 4.3 같은 binding에 대한 직렬화

scheduler는 같은 binding에 대해 `analyze()`를 동시에 호출하지 않는다. 정기 분석과 재분석은 plugin 상태(`running` / `reanalyzing`)로 framework가 직렬화한다. plugin은 이 직렬화를 신뢰하고, `analyze()` 내부에 자체 동기화를 두지 않는다.

---

## 4A. Cache 생명주기

PluginCache는 plugin의 모든 상태를 메모리에 보관한다. 생성부터 폐기까지의 전 과정을 이해해야 cache가 무한히 커지거나, 재분석 시 오염되거나, 서버 재시작 시 사라지는 문제를 막을 수 있다.

### 4A.1 생성 — 서버 부팅 시

```
서버 부팅
  └─ loader._setup_drift_plugin()
       ├─ cache = PluginCache()          # 빈 cache 생성
       ├─ plugin.cache = cache           # plugin이 cache를 소유
       └─ app.config["PLUGIN_CACHES"][key] = cache  # framework가 참조 보관
```

- cache는 **plugin_key 단위**로 1개 생성된다 (현재 구현).
- 같은 plugin_key에 여러 binding이 묶이면 cache를 공유한다 (1.D.5에서 binding 단위 분리 예정).
- 생성 시 cache는 완전히 비어 있다 — raw도 layer도 event도 없음.

### 4A.2 초기 적재 — 첫 데이터 도착

```
scheduler._check_cycle()
  └─ calculated_until is None → 초기 로드
       ├─ store.get_earliest(stream) → 가장 오래된 timestamp
       ├─ plugin.set_calculated_until(earliest)
       └─ cache.calculated_until = earliest
```

첫 데이터가 도착하면 scheduler가 `calculated_until`을 설정하고, 이후 매 cycle마다 `analyze()`를 호출한다. `analyze()` 내부에서 `cache.append_and_snapshot()`이 raw를 누적하기 시작한다.

- 영속화된 히스토리가 있으면 `cache.load_history(data, events, calculated_until)`로 복원 가능.
- `load_history()`는 layer_data를 비운 채로 시작한다 — 다음 `analyze()` cycle에서 재계산.

### 4A.3 정상 운영 — 누적 성장

매 scheduler cycle마다:

```
analyze(new_data)
  1단계: cache.append_and_snapshot(new_data)  → raw 누적 (불변, 단조 증가)
  2단계: _run_algorithm(snapshot)             → events, layer_rows 산출
  3단계: cache.commit_analysis(layer_rows, events, replace_events=True)
         → layer_data 갱신 (timestamp 키로 덮어쓰기)
         → drift_events 교체 (replace) 또는 추가 (append)
```

**cache 크기 증가 요인**:

| 컬렉션 | 증가 패턴 | 크기 추정 (1년, 5분 간격) |
|---|---|---|
| `data` (raw) | 매 cycle 새 subgroup 추가. 절대 줄지 않음 (trim 전까지) | ~105,000 rows |
| `layer_data` | 매 cycle 전체 재계산으로 갱신. 크기 = raw 크기 | ~105,000 entries |
| `drift_events` | `replace_events=True`면 매 cycle 교체. event 수에 비례 | 수십~수백 개 |

### 4A.4 용량 제어 — trim

cache가 무한히 커지는 것을 방지하기 위해 `trim(max_days)` 메서드가 존재한다.

```python
cache.trim(max_days=365)  # 365일보다 오래된 raw 삭제
```

**trim의 동작**:
1. `cutoff = now - max_days` 계산
2. `data`에서 `timestamp < cutoff`인 row 제거 (FIFO)
3. `layer_data`에서 같은 timestamp의 entry 함께 제거
4. `drift_events`는 **유지** — 과거 drift 이력은 보존
5. `cache_from`을 남은 data의 첫 timestamp으로 갱신

**trim 호출 시점** (현재 미구현, 향후 추가 필요):

| 전략 | 트리거 | 장점 | 단점 |
|---|---|---|---|
| 주기적 trim | scheduler가 N cycle마다 호출 | 예측 가능, 구현 단순 | cycle 수 튜닝 필요 |
| 크기 기반 trim | `cache.size > MAX_ROWS`이면 자동 | 메모리 상한 보장 | 오래된 데이터 갑자기 사라짐 |
| 시간 기반 trim | 매일 1회 `trim(MAX_HISTORY_DAYS)` | 자연스러움 | 하루 중 특정 시점에 부하 |

> **현재 상태**: `trim()`은 정의되어 있으나 호출하는 곳이 없다. `MAX_HISTORY_DAYS = 365`가 기본값이다. 운영 배포 시 scheduler에 trim 주기를 추가해야 한다.

**trim이 누적 재실행에 미치는 영향**:
- trim 후 cache의 raw가 줄어들면 `analyze()`는 줄어든 snapshot으로 알고리즘을 실행한다.
- baseline_points보다 raw가 적어지면 분석 불가 → events가 사라질 수 있다.
- 따라서 `trim`의 보존 기간은 baseline_points가 커버하는 시간보다 충분히 길어야 한다.
- 예: `baseline_points=100`, `subgroup_size=5분` → baseline은 ~8시간. 365일 보존이면 충분.

### 4A.5 재분석 — cache 부분 폐기

사용자가 파라미터를 변경하고 재분석을 요청하면:

```
reanalyzer.request_reanalysis(key, new_calculated_until)
  ├─ plugin.set_state("reanalyzing")     # scheduler에서 제외
  ├─ cache.clear_after(dt)               # 현재: raw + layer + events 모두 폐기
  │   (향후: cache.clear_layers_after(dt) # raw 보존, layer + events만 폐기)
  ├─ plugin.set_calculated_until(dt)     # 시점 되돌리기
  └─ 별도 스레드에서 store → aggregate → analyze() 반복
       └─ 현재 시점까지 따라잡으면 plugin.set_state("running") 복귀
```

**두 가지 clear 메서드의 차이**:

| 메서드 | raw | layer | events | 용도 |
|---|---|---|---|---|
| `clear_after(dt)` | dt 이후 삭제 | dt 이후 삭제 | dt 이후 삭제 | DataSource 재구성, 전면 재적재 |
| `clear_layers_after(dt)` | **보존** | dt 이후 삭제 | dt 이후 삭제 | 파라미터 변경 후 알고리즘만 재실행 |

- 현재는 `clear_after`를 사용하여 raw까지 폐기하고 store에서 다시 끌어온다.
- 1.D.4 변환 완료 후 `clear_layers_after` + `plugin.recompute()` 경로로 전환 예정.
  raw를 다시 받을 필요 없이 cache에 보존된 raw로 알고리즘만 재실행하면 된다.

### 4A.6 서버 재시작 — cache 소멸

**현재**: cache는 순수 메모리 객체이다. 서버가 재시작되면 모든 cache가 사라진다.

```
서버 재시작
  └─ loader._setup_drift_plugin()
       └─ cache = PluginCache()  # 빈 cache로 다시 시작
```

재시작 후 scheduler가 돌면서 store의 데이터를 다시 `analyze()`로 공급하면 cache가 재구축된다. 하지만 store도 `InMemoryStore`이면 같이 사라진다.

**영속화 설계**: SQLite 기반으로 raw + drift_events + calculated_until을 저장하고 부팅 시 `load_history()`로 복원한다. layer_data는 저장하지 않으며 `analyze()` 재실행으로 재계산한다. 상세 설계는 [cache_persistence.md](cache_persistence.md) 참조.

### 4A.7 cache 생명주기 전체 그림

```
             서버 부팅
                │
                ▼
         PluginCache() 생성 (빈 상태)
                │
                ├─── load_history() ←── 영속화 복원 (향후)
                │
                ▼
         ┌──────────────┐
         │  정상 운영     │◄─────────────────────┐
         │  analyze()    │                       │
         │  raw 단조 증가 │                       │
         │  layer 매 cycle│                       │
         │  갱신          │                       │
         └──────┬───────┘                       │
                │                                │
          ┌─────┴─────┐                          │
          │            │                          │
          ▼            ▼                          │
    trim(365d)    재분석 요청                     │
    오래된 raw     clear_after(dt)                │
    FIFO 삭제     또는 clear_layers_after(dt)     │
          │            │                          │
          │            ▼                          │
          │     재분석 스레드                      │
          │     store → analyze() 반복            │
          │            │                          │
          │            ▼                          │
          │     plugin.set_state("running")       │
          └────────────┴──────────────────────────┘
                │
                ▼
          서버 종료 → cache 소멸
          (향후: 영속화 → 다음 부팅 시 load_history)
```

### 4A.8 plugin이 cache를 다루는 규칙

plugin 개발자가 지켜야 할 cache 사용 규칙을 정리한다.

| 규칙 | 이유 |
|---|---|
| **raw는 `append_and_snapshot()`으로만 추가한다** | 락 안에서 누적 + 스냅샷을 원자적으로 수행. 직접 `cache.data.append()` 금지 |
| **layer는 `commit_analysis()`로만 갱신한다** | events와 원자적 커밋. 직접 `cache.set_layers()` 단독 호출은 중간 상태 노출 |
| **raw에 layer 컬럼을 섞지 않는다** | raw는 불변. layer 컬럼이 섞이면 재분석 시 오염됨 |
| **알고리즘은 snapshot 복사본으로만 실행한다** | 2단계(락 밖)에서 `cache.data`를 직접 읽으면 다른 스레드의 mutation에 취약 |
| **`cache.size`로 분석 가능 여부를 판단한다** | `new_data` 크기가 아니라 **cache 누적분** 크기로 판단해야 점진 데이터에 안전 |
| **`self._buffer` 같은 instance 상태를 두지 않는다** | stateless — 모든 상태는 cache에. instance 공유 시 안전 |
| **trim 후에도 정상 동작해야 한다** | baseline_points 미달 시 분석 불가 → `return []`. raw가 줄어도 차트는 남은 raw로 표시 |

---

## 5. 알고리즘 분류와 변환 전략

13개 plugin을 알고리즘 특성에 따라 4가지 유형으로 분류한다. 유형마다 변환 시 주의점이 다르다.

### 유형 A: 순차 적응형 (Sequential Adaptive)

**알고리즘**: hat (ADWIN), ewma, cusum

**특성**: 데이터를 순차적으로 처리하며 내부 상태(윈도우, CUSUM 누적합, EWMA 값)를 유지한다. 하지만 이 상태는 알고리즘 루프 안의 지역 변수이지, `self._buffer` 같은 instance 상태가 아니다.

**결정성**: snapshot 전체를 처음부터 순차 처리하면 항상 같은 결과. `baseline_points` 고정이 전제.

**변환 시 주의점**:
- ewma의 `cooldown` (연속 alarm 억제) — 루프 지역 변수이므로 snapshot 재실행에 안전
- cusum의 `reset` (alarm 후 CUSUM 리셋) — 동일
- cusum의 bootstrap `h="auto"` — **비결정적** (아래 5.5절 참조)
- hat의 ADWIN 윈도우 축소 — 순차 결정적

### 유형 B: 슬라이딩 윈도우 (Sliding Window)

**알고리즘**: hotelling, ocdd, shap

**특성**: 고정 크기 윈도우를 밀면서 통계량(T², outlier ratio, profile distance)을 계산한다. 윈도우 크기와 baseline이 고정이면 완전히 결정적이다.

**결정성**: 자연스럽게 보장됨. `baseline_points` 고정만 하면 됨.

**변환 시 주의점**: 없음 — 가장 단순한 유형. (이미 변환 완료: hotelling, ocdd, shap)

### 유형 C: 참조 윈도우 갱신형 (Reference-Updating)

**알고리즘**: ks-test, wasserstein

**특성**: baseline(reference)과 test window를 비교하되, drift 감지 시 **reference를 새 데이터로 교체**한다. 이 교체가 이후 비교 결과에 영향을 준다.

**결정성**: reference 교체는 순차적이므로 snapshot 전체 재실행 시 같은 순서로 같은 교체가 일어남 → 결정적. 단, 다음이 전제:
- `baseline_points` 고정 (reference 시작점 고정)
- `np.random` 제거 또는 seed 고정 (ks-test의 reference 서브샘플링)

**변환 시 주의점**:
- `reference_ratio` → `baseline_points` 전환이 **필수** — 이것 없이는 결정성 불가
- ks-test의 `step` 건너뛰기는 유지 가능 — 계산 안 된 포인트는 layer 없이 raw만 표시
- wasserstein의 EWMA smoothing 초기값 `prev_smoothed = 0.0`은 항상 0에서 시작하므로 결정적

### 유형 D: 단순 제어 차트 (Simple Control Chart)

**알고리즘**: c-chart, p-chart, imr-chart, xbar-r-chart

**특성**: baseline 통계량(μ, σ, c̄, p̄, MR̄)을 계산하고, 고정 제어 한계(UCL/CL/LCL)와 비교한다. 슬라이딩 윈도우도 순차 상태도 없다.

**결정성**: 자연스럽게 보장됨. `baseline_points` 고정만 하면 됨.

**변환 시 주의점**:
- 가장 기계적인 변환 — raw/layer 분리 + `analyze()` 래핑만으로 충분
- xbar-r-chart의 자체 서브그룹화와 framework의 subgroup_size 관계 정리 필요

---

## 6. 플러그인별 이슈와 해결 매핑

### 6.1 공통 이슈 (8개 미변환 플러그인 모두)

| # | 이슈 | 아키텍처 해결 | 적용 방법 |
|---|---|---|---|
| C1 | 진입점이 `detect()` | 2.1절 — 책임 분리 | `analyze()` 구현, `detect()`는 `raise NotImplementedError` |
| C2 | raw/layer 혼합 적재 | 2.3절 — raw/layer 분리 | raw는 `append_and_snapshot()`, layer는 `commit_analysis(layer_rows=)` |
| C3 | `baseline_ratio` 사용 | 3절 — 결정성 | `baseline_points` 고정 포인트 수로 전환 |
| C4 | events append만 | 2.4절 — 누적 재실행 | `commit_analysis(replace_events=True)` + `_dedupe_events()` |
| C5 | detail에 전체 시계열 | — 비대화 방지 | layer_rows로 cache에 이미 보관. detail에서 시계열 배열 제거 |
| C6 | `get_chart_config()` layers 비어있음 | 2.1절 — 표시 분리 | layer 필드를 chart_config에 등록 |

### 6.2 ewma 고유 이슈

| # | 이슈 | 해결 | 비고 |
|---|---|---|---|
| E1 | 1.B placeholder (baseline 미달 시 가짜 ewma/ucl/lcl 적재) | 제거 | 2.1절: raw만 cache에 누적하면 차트 자동 표시 |
| E2 | cooldown 루프 상태 (`last_alarm` 변수) | 유지 | 5절 유형A: snapshot 전체 재실행이므로 결정적 |
| E3 | cache에 events 이중 적재 (`append_data` + `append_events`) | 통합 | `commit_analysis()`로 layer와 event 원자적 커밋 |

**layer 컬럼**: `ewma`, `ucl`, `lcl`, `mu0`, `alarm`
**chart_config layers**: `ewma` (line), `ucl` (line, dashed), `lcl` (line, dashed)

### 6.3 ks-test 고유 이슈

| # | 이슈 | 해결 | 비고 |
|---|---|---|---|
| K1 | 1.B placeholder (baseline 미달 시 가짜 ks/p 적재) | 제거 | 2.1절 |
| K2 | reference window mutation (루프 안에서 `reference = window.copy()`) | 유지 | 5절 유형C: `baseline_points` 고정이면 결정적. 교체 순서는 snapshot 재실행에 안전 |
| K3 | `np.random.choice` 비결정성 (reference 서브샘플링) | seed 고정 또는 제거 | 3.1절: `max_ref_size`를 충분히 크게 잡아 서브샘플링 자체를 피하거나, `np.random.RandomState(42)` 사용 |
| K4 | ECDF 데이터가 event detail에 (배열 4개) | detail에서 제거 | 필요 시 별도 API. detail은 metadata만 |
| K5 | step 건너뛰기 (`step = max(1, window_size // 5)`) | 유지 | layer에 계산된 포인트만 기록. 나머지는 raw만 표시 |

**layer 컬럼**: `ks`, `raw_p`, `corrected_p`, `alarm`
**chart_config layers**: `ks` (line, right axis), `corrected_p` (line, right axis)

### 6.4 wasserstein 고유 이슈

| # | 이슈 | 해결 | 비고 |
|---|---|---|---|
| W1 | 1.B placeholder (baseline 미달 시 가짜 distance 적재) | 제거 | 2.1절 |
| W2 | reference window mutation (alarm 시 `reference = window.copy()`) | 유지 | K2와 동일. `baseline_points` 고정이면 결정적 |
| W3 | EWMA smoothing 초기값 `prev_smoothed = 0.0` | 유지 | snapshot 전체 재실행 시 항상 0에서 시작 → 결정적 |
| W4 | baseline_distances 계산이 `baseline_ratio` 의존 | `baseline_points`로 전환 | 3.2절 |

**layer 컬럼**: `w_distance`, `w_smoothed`, `alarm`, `threshold`
**chart_config layers**: `w_smoothed` (line, right axis), `threshold` (line, dashed, right axis)

### 6.5 cusum 고유 이슈

| # | 이슈 | 해결 | 비고 |
|---|---|---|---|
| S1 | bootstrap 비결정성 (`h="auto"` 시 매 cycle 다른 h) | **seed 고정** | `np.random.default_rng(seed=42)` 사용. 같은 baseline → 같은 h |
| S2 | bootstrap 캘리브레이션 매 cycle 반복 (500회) | 최적화: baseline 확정 후 h 재사용 | baseline이 `baseline_points`로 고정이므로, `n >= baseline_points`가 된 첫 cycle에서 h를 확정하고 이후 cycle에서는 같은 baseline → 같은 seed → 같은 h가 자동 보장됨. 별도 캐싱 불필요 |
| S3 | FIR 초기값 (`fir * h`로 시작) | 유지 | snapshot 전체 재실행이므로 결정적 |

**layer 컬럼**: `s_pos`, `s_neg`, `z`, `alarm`, `threshold_h`
**chart_config layers**: `s_pos` (line), `s_neg` (line), `threshold_h` (line, dashed)

### 6.6 c-chart / p-chart 이슈

| # | 이슈 | 해결 | 비고 |
|---|---|---|---|
| CP1 | 공통 이슈(C1~C6)만 해당 | 기계적 변환 | 유형D: 가장 단순 |
| CP2 | p-chart `sample_size` 파라미터 | 유지 | 기존 동작 보존 |

**c-chart layer 컬럼**: `ucl`, `cl`, `lcl`, `alarm`
**p-chart layer 컬럼**: `ucl`, `cl`, `lcl`, `alarm`
**chart_config layers**: `ucl` (line, dashed), `cl` (line), `lcl` (line, dashed)

### 6.7 imr-chart 이슈

| # | 이슈 | 해결 | 비고 |
|---|---|---|---|
| I1 | MR 값이 layer에 없음 (event detail에만) | layer에 추가 | I Chart + MR Chart 동시 표시 가능 |

**layer 컬럼**: `mr`, `ucl`, `cl`, `lcl`, `ucl_mr`, `cl_mr`, `alarm`
**chart_config layers**: `ucl`/`cl`/`lcl` (I chart), `mr` (line, right axis)

### 6.8 xbar-r-chart 이슈

| # | 이슈 | 해결 | 비고 |
|---|---|---|---|
| X1 | 자체 서브그룹 reshape | 정리 필요 | framework가 이미 `subgroup_size`로 집계하여 넘기므로 이중 그룹화 검토. framework의 subgroup과 xbar-r의 자체 subgroup이 1:1이면 reshape 제거 |
| X2 | R chart layer 누락 | layer에 추가 | X̄ + R 동시 표시 |

**layer 컬럼**: `xbar`, `r_value`, `ucl_xbar`, `cl_xbar`, `lcl_xbar`, `ucl_r`, `cl_r`, `lcl_r`, `alarm`
**chart_config layers**: `ucl_xbar`/`cl_xbar`/`lcl_xbar` (X̄), `r_value` (line, right axis)

---

## 7. 표준 변환 절차

모든 plugin에 공통으로 적용하는 변환 절차이다.

### 7.1 코드 변환 체크리스트

```
□ 1. DEFAULT_PARAMS에서 baseline_ratio/reference_ratio → baseline_points 전환
□ 2. analyze() 메서드 추가 (3단계 패턴)
     □ 2a. 1단계: cache.append_and_snapshot(new_data.to_dict("records"))
     □ 2b. 분석 가능 조건 검사 (cache 누적분 크기로 판단, new_data 크기가 아님)
     □ 2c. 2단계: _run_algorithm(snapshot, ...) — 순수 계산, 락 없음
     □ 2d. _dedupe_events(all_events, previous_events)
     □ 2e. 3단계: cache.commit_analysis(layer_rows, events, replace_events=True)
□ 3. detect() → raise NotImplementedError
□ 4. _run_algorithm() 분리 — raw/layer 혼합 제거
     □ 4a. return (events, layer_rows) — events는 DriftEvent 리스트, layer_rows는 dict 리스트
     □ 4b. layer_rows: 각 row에 "timestamp" + 알고리즘 산출 컬럼
     □ 4c. raw 컬럼(value)은 layer에 넣지 않음
□ 5. 1.B placeholder 코드 제거 (해당 시)
□ 6. event detail에서 전체 시계열 배열 제거
□ 7. get_chart_config()에 layer 필드 등록
□ 8. _dedupe_events() 정적 메서드 추가
□ 9. np.random 비결정성 제거 (해당 시)
```

### 7.2 analyze() 표준 템플릿

```python
def analyze(self, new_data, data_ids, stream, params,
            calculated_until=None, previous_events=None):
    if new_data.empty or self.cache is None:
        return []

    # ── 1단계: 누적 + 스냅샷 (락 안, 짧음) ──
    snapshot = self.cache.append_and_snapshot(
        new_data.to_dict("records")
    )
    n = len(snapshot)

    params = {**self.DEFAULT_PARAMS, **params}
    baseline_points = int(params["baseline_points"])
    baseline_end = min(baseline_points, n)

    # 분석 가능 조건 — 미달이면 raw만 cache에 남기고 종료
    if baseline_end < MINIMUM or (n - baseline_end) < MINIMUM:
        return []

    # ── 2단계: 계산 (락 밖) ──
    all_events, layer_rows = self._run_algorithm(
        snapshot, stream, baseline_end, ...
    )
    new_events = self._dedupe_events(all_events, previous_events)

    # ── 3단계: 커밋 (락 안, 짧음) ──
    self.cache.commit_analysis(
        layer_rows=layer_rows, events=all_events, replace_events=True,
    )
    return new_events

def detect(self, data, data_ids, stream, params,
           calculated_until=None, previous_events=None):
    raise NotImplementedError("XxxDetector는 analyze()를 사용한다.")
```

### 7.3 검증 체크리스트

```
□ 1. 빈 입력 → 빈 리스트 반환, cache 불변
□ 2. 데이터 부족 → 빈 리스트, raw는 cache에 누적
□ 3. 5 cycles 점진 누적 → events 발생, cache.size == 전체 row 수
□ 4. layer merge → snapshot_for_display()에서 raw + layer 합쳐짐
□ 5. dedup → previous_events와 겹치는 events 제거
□ 6. 결정성 → 5 cycle incremental == 1 cycle one-shot (events 동일)
□ 7. chart_config → layers에 필드 등록됨
```

---

## 8. 이슈 해결 매트릭스

모든 이슈가 아키텍처의 어느 부분에 의해 해결되는지 한 눈에 보는 표이다.

| 이슈 | 해결 메커니즘 | 해당 플러그인 |
|---|---|---|
| 차트가 데이터 부족 시 멈춤 | **표시/분석 분리** (2.1절) — raw 즉시 cache | ewma(E1), ks-test(K1), wasserstein(W1) |
| 분석 중 차트 응답 지연 | **3단계 패턴** (2.2절) — 락은 ms만, 계산은 락 밖 | 전체 |
| raw와 layer가 뒤섞임 | **raw/layer 분리** (2.3절) — 재분석 시 raw 보존 | 전체 미변환 8개 (C2) |
| cycle마다 baseline 경계 이동 | **baseline_points 고정** (3절) — n 무관 | 전체 미변환 8개 (C3) |
| 동일 drift 중복 보고 | **replace_events + dedup** (2.4절) | 전체 미변환 8개 (C4) |
| event detail 비대화 | **전체 시계열 제거** — layer로 이미 보관 | 전체 미변환 8개 (C5) |
| 차트에 layer가 안 그려짐 | **chart_config layers 등록** (6.2~6.8절) | 전체 미변환 8개 (C6) |
| reference mutation 비결정성 | **baseline_points 고정** → 교체 순서 고정 | ks-test(K2), wasserstein(W2) |
| np.random 비결정성 | **seed 고정 또는 제거** (3.1절) | ks-test(K3), cusum(S1) |
| bootstrap 매 cycle 반복 비용 | **seed 고정** → 같은 baseline이면 같은 h 자동 보장 | cusum(S2) |
| MR/R chart layer 누락 | **layer 확장** (6.7~6.8절) | imr-chart(I1), xbar-r-chart(X2) |
| xbar-r 이중 서브그룹화 | **framework subgroup과 정합 검토** (6.8절) | xbar-r-chart(X1) |

---

## 9. 변환 순서

이미 변환 완료된 5개(hat, hotelling, ocdd, shap, mewma)를 제외한 8개를 다음 순서로 변환한다.

| 순서 | Batch | 플러그인 | 유형 | 난이도 | 이유 |
|---|---|---|---|---|---|
| 1 | C | ewma | A (순차 적응형) | 중 | 1.B 제거 + cooldown 상태 확인 |
| 2 | D | ks-test | C (참조 갱신형) | 상 | reference mutation + np.random + step |
| 3 | D | wasserstein | C (참조 갱신형) | 상 | reference mutation + baseline 거리 |
| 4 | E | cusum | A (순차 적응형) | 중 | bootstrap 결정성 |
| 5 | E | c-chart | D (단순 제어) | 하 | 기계적 변환 |
| 6 | E | p-chart | D (단순 제어) | 하 | 기계적 변환 |
| 7 | E | imr-chart | D (단순 제어) | 중하 | MR layer 추가 |
| 8 | E | xbar-r-chart | D (단순 제어) | 중하 | R layer 추가 + 서브그룹 정리 |

---

## 부록 A: 이미 변환 완료된 플러그인 참조

| 플러그인 | 유형 | 검증 상태 | 특이사항 |
|---|---|---|---|
| hat | A (순차 적응형) | ✅ incremental == one-shot (9 events 동일) | `baseline_points=30`, ADWIN 윈도우 축소 |
| hotelling | B (슬라이딩 윈도우) | ✅ incremental == one-shot | `baseline_points=50`, shrinkage 정규화 |
| ocdd | B (슬라이딩 윈도우) | ✅ incremental == one-shot | `baseline_points=100`, IQR 기반 |
| shap | B (슬라이딩 윈도우) | ✅ incremental == one-shot | `baseline_windows=50`, 4-dim 프로파일 |
| mewma | B (슬라이딩 윈도우) | ✅ incremental == one-shot (1 event 동일) | `baseline_points=100`, 다변량 EWMA |
