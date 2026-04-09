# EWMA (Exponentially Weighted Moving Average)

## 개요

지수가중이동평균(EWMA) 관리도를 이용하여 시계열 평균의 점진적 변화를 감지하는 순차적 drift 탐지 알고리즘이다. 노이즈가 많은 데이터에서 **평활화를 통해 작은 평균 이동을 안정적으로 탐지**하는 데 적합하며, CUSUM과 함께 소규모 변화 감지의 대표적인 방법이다.

---

## 알고리즘 원리

### 수학적 배경

EWMA 관리도는 Roberts(1959)가 제안한 방법으로, 과거 데이터에 지수적으로 감소하는 가중치를 부여하여 현재 상태를 평활화한다.

**EWMA 통계량:**

$$Z_t = \lambda X_t + (1 - \lambda) Z_{t-1}$$

여기서:
- $Z_t$: 시점 $t$에서의 EWMA 통계량
- $X_t$: 시점 $t$에서의 관측값
- $\lambda$: 평활 상수 ($0 < \lambda \leq 1$). 작을수록 과거 데이터에 더 많은 가중치를 부여한다.
- $Z_0 = \mu_0$ (목표 평균 또는 기준 구간 평균)

**EWMA의 분산:**

정상 상태(steady-state)에서 EWMA 통계량의 분산:

$$\text{Var}(Z_t) = \sigma^2 \cdot \frac{\lambda}{2 - \lambda} \left[1 - (1-\lambda)^{2t}\right]$$

$t$가 충분히 크면 정상 상태 분산으로 수렴한다:

$$\text{Var}(Z_{\infty}) = \sigma^2 \cdot \frac{\lambda}{2 - \lambda}$$

**제어 한계 (Control Limits):**

$$UCL = \mu_0 + L \cdot \sigma \cdot \sqrt{\frac{\lambda}{2 - \lambda}}$$

$$LCL = \mu_0 - L \cdot \sigma \cdot \sqrt{\frac{\lambda}{2 - \lambda}}$$

여기서:
- $\mu_0$: 기준 구간 평균
- $\sigma$: 기준 구간 표준편차
- $L$: 제어 한계 폭 (시그마 배수, 일반적으로 2.5~3.0)

**알람 조건 (양측검정):**

$$Z_t > UCL \quad \text{또는} \quad Z_t < LCL$$

**Score:**

$$\text{score} = \frac{\max(|Z_t - \mu_0|)}{L \cdot \sigma \cdot \sqrt{\lambda/(2-\lambda)}}$$

### Cooldown 메커니즘

연속된 알람이 하나의 이벤트에서 반복 보고되는 것을 방지하기 위해, 알람 발생 후 일정 시점(`cooldown` 포인트) 동안 추가 알람을 억제한다.

### 핵심 아이디어

EWMA는 과거 데이터에 지수적으로 감소하는 가중치를 부여하므로, 단기 노이즈를 평활화하면서도 지속적인 평균 변화에는 민감하게 반응한다. $\lambda$가 작을수록 평활 효과가 강해져서 점진적인 변화에 더 민감해진다.

---

## 파라미터

| 파라미터 | 기본값 | 설명 | 효과 |
|---|---|---|---|
| `lambda_` | 0.1 | EWMA 평활 상수. | 작을수록 과거 가중치 증가, 점진적 변화에 민감. 클수록 Shewhart에 가까워짐 |
| `L` | 3.0 | 제어 한계 폭 (시그마 배수). | 작을수록 민감 (2.5: 민감, 3.0: 표준, 3.5: 보수적) |
| `reference_ratio` | 0.5 | 기준 구간 비율. | 기준 평균/분산 추정에 사용 |
| `cooldown` | 10 | 알람 후 억제 기간 (포인트 수). | 크면 중복 알람 감소, 작으면 빠른 재탐지 |
| `sided` | `"two"` | 검정 방향. `"two"`, `"upper"`, `"lower"`. | `"two"`: 양측, `"upper"`: 상승만, `"lower"`: 하락만 |

### $\lambda$ 선택 가이드

| $\lambda$ | 특성 | 탐지 대상 |
|-----------|------|-----------|
| 0.05 | 강한 평활, 느린 반응 | 0.5σ 이하의 미세한 변화 |
| 0.10 | 중간 평활 (기본값) | 0.5~1.0σ 변화 |
| 0.20 | 약한 평활, 빠른 반응 | 1.0~2.0σ 변화 |
| 0.40 | 최소 평활 | 2.0σ 이상 큰 변화 (Shewhart에 근접) |
| 1.00 | 평활 없음 | Shewhart 차트와 동일 |

---

## 데이터 시나리오

### ds_ewma_gradual — 에러율 점진적 증가

| 구간 | 시점 | 패턴 | EWMA 반응 |
|------|------|------|-----------|
| 정상 | 0~149 | 에러율 5% ($\mu=0.05, \sigma=0.01$) | $Z_t \approx \mu_0$, 제어 한계 이내 |
| 점진 증가 | 150~349 | 에러율 5% → 20% 선형 증가 | $Z_t$가 서서히 상승, 약 200~220에서 UCL 돌파 |
| 고정 | 350~499 | 에러율 20% ($\mu=0.20$) | $Z_t$가 UCL 위에 지속 유지 |

이 시나리오는 EWMA의 핵심 강점인 **점진적 변화 조기 탐지**를 검증한다. Shewhart 차트는 에러율이 $\mu_0 + 3\sigma$ (약 8%)를 넘어야 알람이 발생하지만, EWMA는 누적 효과로 더 이른 시점에 탐지한다.

---

## 다른 알고리즘과의 비교

### EWMA vs CUSUM

| 특성 | EWMA | CUSUM |
|------|------|-------|
| 접근 방식 | 지수가중 평활화 | 누적 편차 합산 |
| 과거 데이터 반영 | 지수적 감소 가중치 | 동일 가중치 (임계값까지) |
| 파라미터 | $\lambda$, $L$ | $k$, $h$ |
| 작은 변화 감지 | 강함 ($\lambda$ 조절) | **매우 강함** |
| 변화 방향 해석 | UCL/LCL로 직관적 | $S^+/S^-$로 구분 가능 |
| 정상 복귀 반응 | 자연스럽게 감소 | 리셋 필요 (`reset=True`) |
| 제어도 표준 | EWMA 관리도 표준 | CUSUM 관리도 표준 |

### 언제 EWMA를 선택하나?

- **노이즈가 심하고 평활화가 필요하다** → EWMA
- **누적 효과로 미세한 변화를 잡고 싶다** → CUSUM
- **제어 한계를 시각적으로 보고 싶다** → EWMA (UCL/LCL이 직관적)
- **변화 후 정상 복귀를 자연스럽게 추적하고 싶다** → EWMA
- **다변량으로 확장해야 한다** → MEWMA

---

## 차트 시각화

- **기본 차트**: Value 시계열 + drift 알람 마커
- **전문가 차트**:
  - Y축(좌): 원본 Value
  - Y2축(우): EWMA 통계량
    - `EWMA` (파란색 선): $Z_t$ 추이
    - `UCL` (빨간색 수평선): 상한 제어 한계
    - `LCL` (빨간색 수평선): 하한 제어 한계
    - `CL` (초록색 수평선): 중심선 ($\mu_0$)

---

## 참고 문헌

- Roberts, S. W. (1959). "Control Chart Tests Based on Geometric Moving Averages." *Technometrics*, 1(3), 239-250.
- Lucas, J. M., & Saccucci, M. S. (1990). "Exponentially Weighted Moving Average Control Schemes: Properties and Enhancements." *Technometrics*, 32(1), 1-12.
- Montgomery, D. C. (2019). *Introduction to Statistical Quality Control*, 8th Edition. Wiley.
- Hunter, J. S. (1986). "The Exponentially Weighted Moving Average." *Journal of Quality Technology*, 18(4), 203-210.
