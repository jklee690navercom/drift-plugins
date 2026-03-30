# Hotelling T²

## 개요
Hotelling T² 통계량을 이용하여 슬라이딩 윈도우 평균이 기준 구간 평균과 유의하게 다른지를 카이제곱 검정으로 판단하는 drift 탐지 알고리즘이다.

## 알고리즘 원리

### 수학적 배경

Hotelling T²는 다변량 통계에서 평균 벡터의 변화를 검정하는 방법이다. 이 구현에서는 단변량에 적용한다.

**T² 통계량 (단변량):**

$$T^2 = n_w \cdot \frac{(\bar{x}_w - \bar{x}_{\text{ref}})^2}{s_{\text{ref}}^2}$$

여기서:
- $n_w$: 테스트 윈도우의 크기 (`window_size`)
- $\bar{x}_w$: 테스트 윈도우의 평균
- $\bar{x}_{\text{ref}}$: 기준 구간의 평균
- $s_{\text{ref}}^2$: 기준 구간의 분산 (ddof=1, 불편분산)

**임계값:**

$$\text{threshold} = \chi^2_{1-\alpha}(df=1)$$

카이제곱 분포의 상위 $\alpha$ 백분위수를 임계값으로 사용한다. 예를 들어 $\alpha=0.01$일 때 $\chi^2_{0.99}(1) \approx 6.635$이다.

**알람 조건:**

$$T^2 > \text{threshold}$$

**Score:**

$$\text{score} = \frac{T^2}{\text{threshold}}$$

### 핵심 아이디어

기준 구간의 평균과 분산을 안정 상태의 기준값으로 삼고, 슬라이딩 윈도우의 평균이 이 기준에서 통계적으로 유의하게 벗어났는지를 카이제곱 검정으로 판단한다.

## 파라미터

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| `alpha` | 0.01 | 유의수준. 작을수록 보수적으로 판단한다. |
| `window_size` | 50 | 테스트 슬라이딩 윈도우의 크기 |
| `reference_ratio` | 0.5 | 전체 데이터에서 기준 구간이 차지하는 비율 |

## 탐지 로직

`detect()` 메서드의 동작 순서:

1. **구간 분리**: 데이터의 앞쪽 `reference_ratio` 비율을 기준 구간으로 설정한다.
2. **기준 통계량 계산**: 기준 구간의 평균(`ref_mean`)과 불편분산(`ref_var`, ddof=1)을 계산한다.
3. **임계값 결정**: `scipy.stats.chi2.ppf(1 - alpha, df=1)`로 카이제곱 임계값을 구한다.
4. **슬라이딩 윈도우 T² 계산**: 기준 구간 이후부터 윈도우를 이동하며, 각 윈도우의 평균과 기준 평균의 차이로 T² 값을 계산한다.
5. **알람 판정**: T² > threshold이면 해당 시점(윈도우 중간)을 alarm으로 표시한다.
6. **연속 알람 그룹화**: 인접한 알람 인덱스를 gap=3 기준으로 그룹화한다.
7. **이벤트 생성**: T²가 가장 큰 알람 시점을 peak로 선택하고, score = T²/threshold를 계산한다.
8. **심각도 판정**: score >= 2.0이면 critical, >= 1.0이면 warning, 그 외 normal.

## 차트 시각화

- **기본 차트**: Value 시계열 + drift 알람 마커
- **전문가 차트**:
  - Y축(좌): 원본 Value
  - Y2축(우): T² 통계량
    - `T²` (파란색 선): Hotelling T² 통계량
    - `chi2 threshold` (빨간색 수평선): 카이제곱 임계값

## 적합한 상황

### 효과적인 경우
- 프로세스 평균의 변화(mean shift)를 감지할 때
- 데이터가 대략적으로 정규분포를 따를 때
- 기준 구간이 안정적(in-control)임이 확실할 때
- 다변량 확장이 필요한 경우의 기초 알고리즘으로 활용할 때

### 한계점
- 분산만 변하고 평균은 그대로인 경우에는 탐지하지 못한다
- 기준 구간의 분산이 0에 가까우면 T²가 과도하게 커져서 오경보가 발생할 수 있다
- 정규분포 가정에 의존하므로, 극단적인 비정규 데이터에는 부정확할 수 있다
- 현재 구현은 단변량이므로 변수 간 상관관계를 고려하지 않는다

## 참고 문헌

- Hotelling, H. (1947). "Multivariate Quality Control." *Techniques of Statistical Analysis*. McGraw-Hill.
- Montgomery, D. C. (2019). *Introduction to Statistical Quality Control*, 8th Edition. Wiley.
- Lowry, C. A., & Montgomery, D. C. (1995). "A Review of Multivariate Control Charts." *IIE Transactions*, 27(6), 800-810.
