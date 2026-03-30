# SHAP (Feature Importance Drift)

## 개요
단변량 시계열에서 rolling statistics를 feature로 추출한 뒤, 기준 구간과 테스트 윈도우 간 KS 검정으로 모든 feature의 분포가 동시에 변했는지를 감지하는 drift 탐지 알고리즘이다.

## 알고리즘 원리

### 수학적 배경

이 구현은 SHAP(SHapley Additive exPlanations) 기반 feature importance 모니터링의 아이디어를 차용하되, 단변량 시계열에서 rolling statistics를 feature로 추출하여 적용한다.

**Feature 추출:**

단변량 시계열에서 3개의 rolling 통계량을 계산한다:

1. **Rolling Mean**: $\bar{x}_{t,w} = \frac{1}{w}\sum_{i=t-w+1}^{t} x_i$
2. **Rolling Std**: $s_{t,w} = \sqrt{\frac{1}{w-1}\sum_{i=t-w+1}^{t}(x_i - \bar{x}_{t,w})^2}$
3. **Rolling Diff**: $\Delta x_t = x_t - x_{t-1}$

여기서 rolling window 크기 $w = \min(10, \text{window\_size} / 5)$ (최소 2).

**각 Feature의 KS 검정:**

각 feature에 대해 기준 구간과 테스트 윈도우의 분포를 비교한다:

$$D_f = \sup_x |F_{\text{ref}}^f(x) - F_{\text{test}}^f(x)|$$

**알람 조건:**

모든 feature에서 KS 검정의 p-value가 유의수준 $\alpha$ 미만이면 drift로 판단한다:

$$\forall f \in \{rolling\_mean, rolling\_std, rolling\_diff\}: \; p_f < \alpha$$

**Score:**

$$\text{score} = \frac{\max_f(D_f)}{0.5}$$

KS 통계량의 최대값을 0.5로 정규화한다 (KS stat = 0.5이면 score = 1.0).

### 핵심 아이디어

단일 값의 변화만 보는 것이 아니라, 데이터의 여러 통계적 특성(평균, 변동성, 변화율)이 동시에 변했는지를 확인한다. 모든 feature의 분포가 동시에 유의하게 변한 경우에만 drift로 판단하므로, 오경보를 줄이면서도 실질적인 데이터 패턴 변화를 감지할 수 있다.

## 파라미터

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| `window_size` | 50 | 테스트 슬라이딩 윈도우의 크기 |
| `reference_ratio` | 0.5 | 전체 데이터에서 기준 구간이 차지하는 비율 |
| `alpha` | 0.05 | 각 feature별 KS 검정의 유의수준 |

## 탐지 로직

`detect()` 메서드의 동작 순서:

1. **Feature 추출**: 전체 시계열에서 rolling_mean, rolling_std, rolling_diff를 계산한다.
   - Rolling window 크기: $\min(10, \text{window\_size}/5)$, 최소 2
2. **구간 분리**: 데이터의 앞쪽 `reference_ratio` 비율을 기준 구간으로 설정한다.
3. **슬라이딩 윈도우 다중 검정**: 기준 구간 이후부터 윈도우를 이동하며:
   - 각 feature에 대해 기준 구간의 feature 분포와 테스트 윈도우의 feature 분포를 KS 2-표본 검정으로 비교한다.
   - 유의한(p < alpha) feature 수를 센다.
   - 모든 feature(3개)가 유의하면 해당 시점(윈도우 중간)을 alarm으로 표시한다.
4. **연속 알람 그룹화**: 인접한 알람 인덱스를 gap=5 기준으로 그룹화한다.
5. **이벤트 생성**: 각 그룹에서 drift_score(max KS stat)가 가장 큰 시점을 peak로 선택하고, 각 feature별 KS stat을 detail에 포함한다.
6. **심각도 판정**: score >= 2.0이면 critical, >= 1.0이면 warning, 그 외 normal.

## 차트 시각화

- **기본 차트**: Value 시계열 + drift 알람 마커
- **전문가 차트**: 현재 커스텀 시각화가 필요하며, 기본 레이어는 비어 있다 (`layers: []`). 향후 각 feature별 KS stat 추이를 표시하는 확장이 가능하다.

## 적합한 상황

### 효과적인 경우
- 데이터의 여러 통계적 특성이 동시에 변하는 복합적인 drift를 감지할 때
- 단순한 평균 이동 외에 변동성, 추세 변화까지 고려하고 싶을 때
- 오경보를 줄이고 싶을 때 (모든 feature가 동시에 유의해야 alarm)
- Feature importance 기반 drift 모니터링의 개념을 단변량 데이터에 적용하고 싶을 때

### 한계점
- 3개의 feature가 모두 유의해야 하므로, 단일 특성만 변하는 미세한 drift를 놓칠 수 있다
- 매 윈도우마다 3회의 KS 검정을 수행하므로 계산 비용이 상대적으로 높다
- Rolling 통계량 간에 상관관계가 있어 독립 검정의 가정이 엄밀하지 않다
- Feature 선택이 고정되어 있어, 특정 도메인에서는 더 적합한 feature가 있을 수 있다

## 참고 문헌

- Lundberg, S. M., & Lee, S.-I. (2017). "A Unified Approach to Interpreting Model Predictions." *NeurIPS*.
- Lu, J., Liu, A., Dong, F., Gu, F., Gama, J., & Zhang, G. (2018). "Learning under Concept Drift: A Review." *IEEE TKDE*, 31(12), 2346-2363.
- Rabanser, S., Gunnemann, S., & Lipton, Z. C. (2019). "Failing Loudly: An Empirical Study of Methods for Detecting Dataset Shift." *NeurIPS*.
