# I-MR Chart (Individual-Moving Range Chart)

## 개요

개별 관측값(Individual)과 연속 관측값 간의 이동범위(Moving Range)를 동시에 모니터링하여 평균과 산포의 이상을 감지하는 제어 차트 기반 drift 탐지 알고리즘이다. **서브그룹을 구성할 수 없는 환경**(관측값이 한 번에 하나씩 도착)에서 평균과 단기 변동성을 동시에 감시하는 데 적합하다.

---

## 알고리즘 원리

### 수학적 배경

I-MR Chart는 서브그룹을 구성할 수 없을 때(관측값이 한 번에 하나씩 도착하는 경우) 사용하는 변수형 제어 차트이다.

**이동범위 (Moving Range):**

$$MR_i = |x_i - x_{i-1}|$$

연속된 두 관측값의 절대 차이이다.

**기준 통계량:**
- $\bar{x}_{\text{ref}}$: 기준 구간의 평균
- $\overline{MR}_{\text{ref}}$: 기준 구간 이동범위의 평균

**I 차트 (Individual Chart) 제어 한계:**

$$UCL_I = \bar{x}_{\text{ref}} + 2.66 \cdot \overline{MR}$$

$$LCL_I = \bar{x}_{\text{ref}} - 2.66 \cdot \overline{MR}$$

$$CL_I = \bar{x}_{\text{ref}}$$

여기서 $2.66 = 3/d_2$이고, $d_2 = 1.128$ (이동범위의 크기 $n=2$일 때의 상수)이다.

**MR 차트 (Moving Range Chart) 제어 한계:**

$$UCL_{MR} = D_4 \cdot \overline{MR} = 3.267 \cdot \overline{MR}$$

$$CL_{MR} = \overline{MR}$$

여기서 $D_4 = 3.267$ ($n=2$일 때의 상수)이다. LCL은 0이다.

**알람 조건:**

$$x_i > UCL_I \; \text{또는} \; x_i < LCL_I \; \text{또는} \; MR_i > UCL_{MR}$$

**Score:**

$$\text{score} = \frac{\max|x_i - \bar{x}_{\text{ref}}|}{2.66 \cdot \overline{MR}}$$

### 핵심 아이디어

서브그룹을 만들 수 없는 상황(예: 배치당 1개 측정, 파괴 검사 등)에서 개별값과 이동범위를 결합하여 프로세스를 모니터링한다. I 차트는 평균 변화를, MR 차트는 관측값 간 변동성 변화를 감지한다.

---

## 파라미터

| 파라미터 | 기본값 | 설명 | 효과 |
|---|---|---|---|
| `reference_ratio` | 0.5 | 기준 구간 비율 | 기준 평균과 이동범위 추정에 사용 |

---

## 데이터 시나리오

### ds_spc_measurement — SPC 연속형 측정 데이터

| 구간 | 시점 | 패턴 | I-MR Chart 반응 |
|------|------|------|----------------|
| 정상 | 0~99 | $\mu=100, \sigma=2$ | I 차트, MR 차트 모두 제어 이내 |
| 평균 이동 | 100~199 | $\mu=106, \sigma=2$ | I 차트 UCL 초과 → alarm. MR 차트는 정상 |
| 분산 증가 | 200~299 | $\mu=100, \sigma=6$ | MR 차트 UCL 초과 → alarm. I 차트 일부 초과 |
| 복합 변화 | 300~399 | $\mu=106, \sigma=6$ | I 차트, MR 차트 모두 초과 → alarm |

이 시나리오는 I-MR Chart의 **이중 모니터링** 능력을 보여준다. I 차트는 평균 변화를, MR 차트는 변동성 변화를 각각 감지하며, 복합 변화는 양쪽 모두에서 잡힌다. CUSUM이나 EWMA에는 없는 분산 변화 감지 기능이 MR 차트의 장점이다.

---

## 다른 알고리즘과의 비교

| 특성 | I-MR Chart | X-bar/R Chart | CUSUM | EWMA |
|------|-----------|---------------|-------|------|
| 서브그룹 필요 | **불필요** | 필요 (n=2~10) | 불필요 | 불필요 |
| 평균 변화 | 감지 (3σ) | 감지 (3σ) | **매우 강함** | **강함** |
| 분산 변화 | **MR 차트** | **R 차트** | 불가 | 불가 |
| 점진적 변화 | 약함 | 약함 | **강함** | **강함** |
| 파라미터 | 없음 (자동) | subgroup_size | k, h | lambda, L |
| 정규성 의존 | **높음** | 중간 (CLT) | 중간 | 중간 |

### 언제 I-MR Chart를 선택하나?

- **관측값이 하나씩 도착한다 (서브그룹 불가)** → I-MR Chart
- **서브그룹을 구성할 수 있다 (배치, 시간대)** → X-bar/R Chart
- **작은 평균 이동을 빠르게 잡고 싶다** → CUSUM 또는 EWMA
- **분산 변화도 함께 감시하고 싶다** → I-MR Chart (MR 차트)

---

## 탐지 로직

`detect()` 메서드의 동작 순서:

1. **이동범위 계산**: 전체 시계열에서 $MR_i = |x_i - x_{i-1}|$을 계산한다. 첫 번째 값은 $MR_0 = 0$으로 설정한다.
2. **기준 구간 설정**: 데이터의 앞쪽 `reference_ratio` 비율을 기준 구간으로 사용한다 (최소 2개).
3. **기준 통계량 계산**: $\bar{x}_{\text{ref}}$와 $\overline{MR}_{\text{ref}}$를 계산한다.
4. **I 차트 제어 한계 계산**: UCL/LCL = $\bar{x}_{\text{ref}} \pm 2.66 \cdot \overline{MR}$.
5. **MR 차트 제어 한계 계산**: $UCL_{MR} = 3.267 \cdot \overline{MR}$.
6. **알람 판정**: I 차트 또는 MR 차트에서 제어 한계를 벗어난 시점을 alarm으로 표시한다.
7. **연속 알람 그룹화**: 인접한 알람 인덱스를 gap=3 기준으로 그룹화한다.
8. **이벤트 생성**: 각 그룹에서 중심선으로부터 가장 크게 벗어난 시점을 peak로 선택하고, score를 계산한다.
9. **심각도 판정**: score >= 2.0이면 critical, >= 1.0이면 warning, 그 외 normal.

---

## 차트 시각화

- **기본 차트**: Individual 값 시계열 + drift 알람 마커
- **전문가 차트**:
  - Y축(좌): Value (Individual)
    - `UCL (I)` (주황색 수평선): I 차트 상한 제어 한계
    - `LCL (I)` (주황색 수평선): I 차트 하한 제어 한계
  - Y2축(우): Moving Range
    - `MR` (보라색 선): 이동범위 추이
    - `UCL (MR)` (빨간색 수평선): MR 차트 상한 제어 한계

---

## 참고 문헌

- Wheeler, D. J. (2010). *Understanding Statistical Process Control*, 3rd Edition. SPC Press.
- Montgomery, D. C. (2019). *Introduction to Statistical Quality Control*, 8th Edition. Wiley.
- Nelson, L. S. (1982). "Control Charts for Individual Measurements." *Journal of Quality Technology*, 14(3), 172-173.
