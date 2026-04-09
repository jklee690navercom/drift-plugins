# CUSUM (Cumulative Sum)

## 개요

양방향 누적합(CUSUM) 통계량을 이용하여 시계열 평균의 상승 또는 하락을 감지하는 순차적 drift 탐지 알고리즘이다. 프로세스 평균의 **작고 지속적인 변화**(small persistent shift)를 조기에 탐지하는 데 가장 효과적이며, 제조 공정 모니터링, 센서 드리프트 감지, 품질 지표 추적 등에 적합하다.

---

## 알고리즘 원리

### 수학적 배경

CUSUM은 Page(1954)가 제안한 순차 탐지 기법으로, 관측값의 누적 편차를 추적한다.

**표준화 단계:**

입력 시계열을 robust 표준화(median + MAD)한다.

$$\sigma = 1.4826 \times \text{MAD}$$

$$z_i = \frac{x_i - \text{median}}{\sigma}$$

여기서 MAD(Median Absolute Deviation)는 `median(|x_i - median(x)|)` 이고, 1.4826은 정규분포 가정 하에서 MAD를 표준편차로 변환하는 상수이다.

**양방향 CUSUM 통계량:**

$$S_i^+ = \max(0, S_{i-1}^+ + z_i - k)$$

$$S_i^- = \max(0, S_{i-1}^- - z_i - k)$$

- $S^+$: 평균 상승을 감지하는 누적합
- $S^-$: 평균 하락을 감지하는 누적합
- $k$: slack value (허용 편차)

**알람 조건:**

$$S_i^+ > h \quad \text{또는} \quad S_i^- > h$$

### Bootstrap 캘리브레이션 (v2.1)

v2.1부터 `h="auto"` 설정 시 Bootstrap 캘리브레이션을 통해 임계값 $h$를 자동 결정한다.

**절차:**

1. 기준 구간(baseline)에서 데이터를 추출한다.
2. Bootstrap 재표본(기본 1000회)을 생성하여 각 재표본에 CUSUM을 적용한다.
3. 정상 데이터에서의 $\max(S^+, S^-)$ 분포를 구한다.
4. 해당 분포의 상위 백분위수(기본 99%)를 $h$로 설정한다.

$$h_{\text{auto}} = \text{quantile}_{1-\alpha}\left(\max_{i}(S_i^+, S_i^-)_{\text{bootstrap}}\right)$$

이 방식은 데이터의 실제 변동성을 반영하므로, 수동 튜닝 없이도 합리적인 임계값을 설정할 수 있다.

### FIR (Fast Initial Response)

FIR은 CUSUM의 초기 상태를 0이 아닌 양수로 설정하여, 프로세스 시작 직후의 이상을 빠르게 감지한다.

$$S_0^+ = S_0^- = \text{FIR\_value}$$

일반적으로 $\text{FIR\_value} = h/2$로 설정한다. FIR을 사용하면 CUSUM 통계량이 임계값에 도달하는 시간이 단축되어 초기 이탈을 더 빨리 잡을 수 있다.

### Baseline 분리

v2.1에서는 `baseline_ratio` 파라미터를 통해 표준화에 사용하는 기준 구간과 검정 구간을 명확히 분리한다. Baseline 구간의 median과 MAD만을 사용하여 표준화하고, 이후 구간에서 CUSUM 통계량을 계산한다.

### 핵심 아이디어

데이터가 정상 상태에서 벗어나면 CUSUM 통계량이 점진적으로 누적되어 증가한다. 임계값 $h$를 초과하는 순간 drift로 판단한다. slack value $k$는 작은 변동을 무시하고 의미 있는 변화만 누적하도록 한다.

---

## 파라미터

| 파라미터 | 기본값 | 설명 | 효과 |
|---|---|---|---|
| `k` | 0.25 | Slack value. 표준화된 단위에서 허용하는 편차. | 작을수록 민감 (0.1: 매우 민감, 0.5: 보수적) |
| `h` | 5.0 또는 `"auto"` | Threshold. 누적합 임계값. | `"auto"`: Bootstrap 자동 결정. 작을수록 빠른 탐지, 크면 오탐 감소 |
| `reset` | True | 알람 발생 후 CUSUM 통계량 리셋 여부. | True: 독립적 이벤트 탐지, False: 연속 모니터링 |
| `fir` | None | Fast Initial Response 초기값. | `h/2` 설정 시 초기 이탈 감지 속도 향상 |
| `baseline_ratio` | 0.3 | Baseline(표준화 기준) 구간 비율. | 크면 안정적 추정, 작으면 변화 탐지 구간 확대 |

---

## 데이터 시나리오

### ds_cusum_4phase — 4단계 프로세스 변화

| 구간 | 시점 | 패턴 | CUSUM 반응 |
|------|------|------|------------|
| Phase 1 | 0~99 | 정상 ($\mu=50, \sigma=2$) | $S^+, S^- \approx 0$ (관리 상태) |
| Phase 2 | 100~199 | 점진 하락 ($\mu: 50 \to 46$) | $S^-$가 서서히 누적, 약 130 부근에서 alarm |
| Phase 3 | 200~299 | 복귀 ($\mu=50$) | 리셋 후 $S^+, S^-$ 다시 안정 |
| Phase 4 | 300~399 | 급락 ($\mu=42$) | $S^-$가 급속 증가, 310 이전에 alarm (critical) |

이 데이터소스는 CUSUM의 핵심 강점인 **점진적 변화 조기 탐지**와 **급격한 변화 즉시 탐지**를 모두 검증한다. Phase 2에서 Shewhart 차트는 놓치지만 CUSUM은 잡아낸다.

---

## 다른 알고리즘과의 비교

### CUSUM vs EWMA vs Shewhart

| 특성 | CUSUM | EWMA | Shewhart (I-MR) |
|------|-------|------|-----------------|
| 작은 평균 이동 (0.5~1.5σ) | **매우 강함** | **강함** | 약함 |
| 큰 평균 이동 (>3σ) | 강함 | 강함 | **매우 강함** |
| 점진적 변화 | **매우 강함** | 강함 | 약함 |
| 급격한 변화 | 강함 | 보통 | **매우 강함** |
| 파라미터 수 | 2 (k, h) | 2 (λ, L) | 0 (자동) |
| 해석 용이성 | 보통 | 보통 | **매우 쉬움** |
| 분산 변화 감지 | 불가 | 불가 | MR 차트로 가능 |

### 언제 CUSUM을 선택하나?

- **평균이 서서히 빠지는 것을 빨리 잡고 싶다** → CUSUM
- **노이즈가 많아서 평활화가 필요하다** → EWMA
- **큰 이상만 빠르게 잡으면 된다** → Shewhart (I-MR)
- **분포 자체가 바뀌는지 확인하고 싶다** → KS Test
- **여러 변수를 동시에 보고 싶다** → Hotelling T² 또는 MEWMA

---

## 탐지 로직

`detect()` 메서드의 동작 순서:

1. **데이터 표준화**: 입력 시계열에서 median과 MAD를 계산하고, robust 표준화를 수행한다.
2. **CUSUM 통계량 계산**: 표준화된 값에 대해 양방향 CUSUM($S^+$, $S^-$)을 순차적으로 계산한다.
3. **알람 판정**: $S^+$ 또는 $S^-$가 임계값 $h$를 초과하면 해당 시점을 alarm으로 표시한다.
4. **리셋 처리**: `reset=True`이면 알람 발생 후 $S^+$와 $S^-$를 모두 0으로 초기화한다.
5. **연속 알람 그룹화**: 인접한 알람 인덱스를 gap=3 기준으로 그룹화한다.
6. **이벤트 생성**: 각 그룹에서 $\max(S^+, S^-)$가 가장 큰 시점을 peak로 선택하고, `score = max(S_pos, S_neg) / h`를 계산한다.
7. **심각도 판정**: score >= 2.0이면 critical, >= 1.0이면 warning, 그 외 normal.

---

## 차트 시각화

- **기본 차트**: Value 시계열 + drift 알람 마커
- **전문가 차트**:
  - Y축(좌): 원본 Value
  - Y2축(우): CUSUM 통계량
    - `S+` (빨간색 선): 상향 누적합
    - `S-` (초록색 선): 하향 누적합
    - `h` (주황색 수평선): 임계값 threshold

---

## 참고 문헌

- Page, E. S. (1954). "Continuous Inspection Schemes." *Biometrika*, 41(1/2), 100-115.
- Montgomery, D. C. (2019). *Introduction to Statistical Quality Control*, 8th Edition. Wiley.
- Hawkins, D. M., & Olwell, D. H. (1998). *Cumulative Sum Charts and Charting for Quality Improvement*. Springer.
- Lucas, J. M., & Crosier, R. B. (1982). "Fast Initial Response for CUSUM Quality-Control Schemes." *Technometrics*, 24(3), 199-205.
