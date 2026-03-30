# MEWMA (Multivariate Exponentially Weighted Moving Average)

## 개요
EWMA 평활화된 값의 D² 통계량을 이용하여 평균 변화를 감지하는 drift 탐지 알고리즘이다. 단변량 시계열에 적용되며, 카이제곱 검정으로 유의성을 판단한다.

## 알고리즘 원리

### 수학적 배경

MEWMA는 지수가중이동평균(EWMA)을 다변량으로 확장한 것으로, 이 구현에서는 단변량에 적용한다.

**EWMA 평활화:**

$$z_t = \lambda \cdot x_t + (1 - \lambda) \cdot z_{t-1}$$

여기서:
- $z_t$: 시점 $t$에서의 평활화된 값
- $x_t$: 시점 $t$에서의 관측값
- $\lambda$: 평활 상수 (0 < $\lambda$ <= 1). 작을수록 과거 데이터에 더 많은 가중치를 준다.
- $z_0 = x_0$ (초기값)

**D² 통계량 (단변량):**

$$D^2_t = \frac{(z_t - \bar{x}_{\text{ref}})^2}{\text{Var}(x_{\text{ref}})}$$

여기서:
- $\bar{x}_{\text{ref}}$: 기준 구간의 평균
- $\text{Var}(x_{\text{ref}})$: 기준 구간의 분산 (ddof=0)

**임계값:**

$$\text{threshold} = \chi^2_{1-\alpha}(df=1)$$

**알람 조건:**

$$D^2_t > \text{threshold} \quad (t > \text{ref\_end})$$

**Score:**

$$\text{score} = \frac{D^2_{\text{peak}}}{\text{threshold}}$$

### 핵심 아이디어

EWMA 평활화로 단기 노이즈를 제거한 뒤, 평활화된 값이 기준 구간의 평균에서 얼마나 벗어났는지를 D² 통계량으로 측정한다. $\lambda$가 작을수록 평활 효과가 강해져서 점진적인 변화에 민감해진다.

## 파라미터

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| `lambda_` | 0.1 | EWMA 평활 상수. 작을수록 과거 데이터에 더 많은 가중치를 부여한다. |
| `reference_ratio` | 0.5 | 전체 데이터에서 기준 구간이 차지하는 비율 |
| `alpha` | 0.01 | 유의수준. 작을수록 보수적으로 판단한다. |

## 탐지 로직

`detect()` 메서드의 동작 순서:

1. **구간 분리**: 데이터의 앞쪽 `reference_ratio` 비율을 기준 구간으로 설정한다. 최소 10개 데이터가 필요하다.
2. **기준 통계량 계산**: 기준 구간의 평균(`ref_mean`)과 분산(`ref_var`, ddof=0)을 계산한다.
3. **EWMA 평활화**: 전체 시계열에 대해 EWMA를 계산한다 ($z_0 = x_0$).
4. **D² 통계량 계산**: $(z_t - \text{ref\_mean})^2 / \text{ref\_var}$를 전체 시점에 대해 계산한다.
5. **임계값 결정**: `scipy.stats.chi2.ppf(1 - alpha, df=1)`로 카이제곱 임계값을 구한다.
6. **알람 판정**: 기준 구간 이후의 시점에서 D² > threshold이면 alarm으로 표시한다.
7. **연속 알람 그룹화**: 인접한 알람 인덱스를 gap=5 기준으로 그룹화한다.
8. **이벤트 생성**: 각 그룹에서 D²가 가장 큰 시점을 peak로 선택하고, score = D²/threshold를 계산한다.
9. **심각도 판정**: score >= 2.0이면 critical, >= 1.0이면 warning, 그 외 normal.

## 차트 시각화

- **기본 차트**: Value 시계열 + drift 알람 마커
- **전문가 차트**:
  - Y축(좌): 원본 Value
  - Y2축(우): D² 통계량
    - `D²` (파란색 선): D² 통계량 추이
    - `UCL` (빨간색 수평선): 카이제곱 임계값 (Upper Control Limit)

## 적합한 상황

### 효과적인 경우
- 점진적이고 작은 크기의 평균 이동을 감지할 때 (CUSUM과 유사한 강점)
- 노이즈가 많은 데이터에서 평활화를 통해 안정적인 탐지가 필요할 때
- $\lambda$ 값을 조절하여 탐지 민감도를 세밀하게 제어하고 싶을 때
- 다변량 확장이 가능한 프레임워크가 필요할 때

### 한계점
- 분산만 변하고 평균이 유지되는 경우에는 효과적이지 않다
- $\lambda$ 값에 따라 탐지 특성이 크게 달라지므로 적절한 튜닝이 필요하다
- 초기 평활화 구간에서는 $z_t$가 안정화되지 않아 부정확할 수 있다
- 정규분포 가정에 기반한 카이제곱 임계값을 사용하므로, 비정규 데이터에서는 보정이 필요하다

## 참고 문헌

- Lowry, C. A., Woodall, W. H., Champ, C. W., & Rigdon, S. E. (1992). "A Multivariate Exponentially Weighted Moving Average Control Chart." *Technometrics*, 34(1), 46-53.
- Roberts, S. W. (1959). "Control Chart Tests Based on Geometric Moving Averages." *Technometrics*, 1(3), 239-250.
- Montgomery, D. C. (2019). *Introduction to Statistical Quality Control*, 8th Edition. Wiley.
