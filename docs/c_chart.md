# C Chart

## 개요

일정 단위에서 발생하는 결함/사건의 건수를 포아송 분포 기반 제어 한계로 모니터링하는 제어 차트(control chart) 기반 drift 탐지 알고리즘이다. **검사 단위 크기가 일정한 카운트 데이터**의 이상 감지에 적합하며, SPC의 가장 기본적인 속성형 관리도이다.

---

## 알고리즘 원리

### 수학적 배경

C Chart는 일정 크기의 검사 단위(inspection unit)에서 발생하는 결함 수(count)를 모니터링하는 속성형 제어 차트이다. 결함 수는 포아송 분포를 따른다고 가정한다.

**중심선 (Center Line):**

$$CL = \bar{c}$$

여기서 $\bar{c}$는 기준 구간의 평균 결함 수이다.

**제어 한계 (Control Limits):**

$$UCL = \bar{c} + 3\sqrt{\bar{c}}$$

$$LCL = \max(0, \bar{c} - 3\sqrt{\bar{c}})$$

포아송 분포에서 분산 = 평균이므로, 표준편차 $\sigma = \sqrt{\bar{c}}$이다.

**알람 조건:**

$$x_i > UCL \quad \text{또는} \quad x_i < LCL$$

**Score:**

$$\text{score} = \frac{\max|x_i - \bar{c}|}{3\sqrt{\bar{c}}}$$

### 핵심 아이디어

포아송 과정을 따르는 결함 수 데이터에서, 3-시그마 제어 한계를 벗어나면 프로세스가 관리 이탈(out-of-control) 상태임을 판단한다. 결함 수가 증가하면 품질 악화를, 감소하면 프로세스 개선을 의미할 수 있다.

---

## 파라미터

| 파라미터 | 기본값 | 설명 | 효과 |
|---|---|---|---|
| `reference_ratio` | 0.5 | 기준 구간 비율 | 기준 결함률 $\bar{c}$ 추정에 사용 |

---

## 데이터 시나리오

### ds_spc_defects — SPC 결함 데이터

| 구간 | 시점 | 패턴 | C Chart 반응 |
|------|------|------|-------------|
| 정상 | 0~99 | 결함 수 ~ Poisson($\lambda=5$) | UCL = 11.7, LCL = 0. 제어 이내 |
| 결함 증가 | 100~199 | 결함 수 ~ Poisson($\lambda=12$) | 다수 포인트가 UCL 초과 → alarm |
| 정상 복귀 | 200~299 | 결함 수 ~ Poisson($\lambda=5$) | 제어 한계 이내 복귀 |
| 결함 감소 | 300~399 | 결함 수 ~ Poisson($\lambda=1$) | LCL 미만 포인트 발생 (품질 개선 신호) |

이 시나리오는 C Chart의 기본적인 **카운트 데이터 모니터링** 능력을 검증한다. 결함 증가(품질 악화)와 결함 감소(품질 개선) 모두를 감지할 수 있다.

---

## 다른 알고리즘과의 비교

| 특성 | C Chart | P Chart | I-MR Chart | CUSUM |
|------|---------|---------|------------|-------|
| 데이터 유형 | **카운트 (정수)** | 비율 (0~1) | 연속형 | 연속형 |
| 분포 가정 | 포아송 | 이항 | 정규 | 정규 |
| 검사 단위 | 고정 크기 | 고정 샘플 | 개별값 | 개별값 |
| 파라미터 | 없음 (자동) | sample_size | 없음 (자동) | k, h |
| 점진적 변화 | 약함 | 약함 | 약함 | **강함** |

### 언제 C Chart를 선택하나?

- **결함 수, 에러 횟수, 사고 건수 등 카운트 데이터** → C Chart
- **불량률, 전환율 등 비율 데이터** → P Chart
- **연속형 개별 측정값** → I-MR Chart
- **작은 평균 이동을 빠르게 감지하고 싶다** → CUSUM

---

## 탐지 로직

`detect()` 메서드의 동작 순서:

1. **기준 구간 설정**: 데이터의 앞쪽 `reference_ratio` 비율을 기준 구간으로 사용한다 (최소 2개).
2. **중심선 계산**: 기준 구간의 평균 결함 수 $\bar{c}$를 계산한다.
3. **제어 한계 계산**: UCL = $\bar{c} + 3\sqrt{\bar{c}}$, LCL = $\max(0, \bar{c} - 3\sqrt{\bar{c}})$.
4. **알람 판정**: 전체 데이터에서 UCL 초과 또는 LCL 미만인 시점을 alarm으로 표시한다.
5. **연속 알람 그룹화**: 인접한 알람 인덱스를 gap=3 기준으로 그룹화한다.
6. **이벤트 생성**: 각 그룹에서 중심선으로부터 가장 크게 벗어난 시점을 peak로 선택하고, score를 계산한다.
7. **심각도 판정**: score >= 2.0이면 critical, >= 1.0이면 warning, 그 외 normal.

---

## 차트 시각화

- **기본 차트**: 결함 수(Defect Count) 시계열 + drift 알람 마커
- **전문가 차트**:
  - Y축: Count
    - `UCL` (주황색 수평선): 상한 제어 한계
    - `CL` (초록색 수평선): 중심선
    - `LCL` (주황색 수평선): 하한 제어 한계

---

## 참고 문헌

- Shewhart, W. A. (1931). *Economic Control of Quality of Manufactured Product*. Van Nostrand.
- Montgomery, D. C. (2019). *Introduction to Statistical Quality Control*, 8th Edition. Wiley.
- Wheeler, D. J. (1995). *Advanced Topics in Statistical Process Control*. SPC Press.
