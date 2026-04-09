# SHAP (Feature Importance Drift)

## 개요

단변량 시계열에서 rolling statistics를 feature로 추출한 뒤, 기준 구간과 테스트 윈도우 간 KS 검정으로 모든 feature의 분포가 동시에 변했는지를 감지하는 drift 탐지 알고리즘이다. **SHAP(TreeExplainer) 기반 feature importance 모니터링**의 개념을 차용하여, 데이터의 여러 통계적 특성이 동시에 변하는 복합적인 drift를 감지하는 데 적합하다.

---

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

### TreeExplainer와의 관계

SHAP의 TreeExplainer는 트리 기반 모델(XGBoost, LightGBM, Random Forest 등)의 예측을 각 feature의 기여도로 분해한다:

$$f(x) = \phi_0 + \sum_{i=1}^{M} \phi_i$$

여기서:
- $\phi_0$: 기대값 (base value)
- $\phi_i$: feature $i$의 SHAP value (기여도)

**Feature Importance Drift 감지 절차:**

1. 기준 구간에서 모델의 SHAP value 분포를 계산
2. 테스트 구간에서 동일 모델의 SHAP value 분포를 계산
3. 각 feature의 SHAP value 분포 변화를 KS 검정으로 비교
4. 유의하게 변한 feature가 있으면 → feature importance drift

이 구현에서는 모델 없이도 활용할 수 있도록, rolling statistics를 "feature"로 사용하여 동일한 로직을 적용한다.

### 핵심 아이디어

단일 값의 변화만 보는 것이 아니라, 데이터의 여러 통계적 특성(평균, 변동성, 변화율)이 동시에 변했는지를 확인한다. 모든 feature의 분포가 동시에 유의하게 변한 경우에만 drift로 판단하므로, 오경보를 줄이면서도 실질적인 데이터 패턴 변화를 감지할 수 있다.

---

## 파라미터

| 파라미터 | 기본값 | 설명 | 효과 |
|---|---|---|---|
| `window_size` | 50 | 테스트 슬라이딩 윈도우 크기 | 크면 안정적, 작으면 빠른 반응 |
| `reference_ratio` | 0.5 | 기준 구간 비율 | 기준 feature 분포 추정에 사용 |
| `alpha` | 0.05 | 각 feature별 KS 검정의 유의수준 | 작을수록 보수적 |

---

## 데이터 시나리오

### 센서 3변량 — feature importance 변화

| 구간 | 시점 | 패턴 | SHAP 반응 |
|------|------|------|-----------|
| 정상 | 0~199 | 센서 3개 안정 (온도, 진동, 압력) | rolling_mean, rolling_std, rolling_diff 모두 정상 분포 유지 |
| 진동 증가 | 200~299 | 진동 센서 변동성 증가 | rolling_std만 유의 → **미탐지** (전체 feature AND 조건 미충족) |
| 복합 변화 | 300~399 | 온도 상승 + 진동 증가 + 압력 변동 | rolling_mean, rolling_std, rolling_diff 모두 유의 → **alarm** |
| 복귀 | 400~499 | 정상 복귀 | 모든 feature 정상 → alarm 해제 |

이 시나리오는 SHAP 방식의 **AND 조건**이 어떻게 오탐을 줄이는지 보여준다. 하나의 통계 특성만 변하는 경우는 노이즈나 일시적 변동일 수 있으므로 무시하고, 모든 특성이 동시에 변하는 진정한 패턴 변화만 탐지한다.

---

## 다른 알고리즘과의 비교

| 특성 | SHAP | KS Test | OCDD | CUSUM |
|------|------|---------|------|-------|
| 감지 대상 | **복합 패턴 변화** | 모든 분포 변화 | 평균+분산 동시 변화 | 평균 변화 |
| 오탐율 | **매우 낮음** (AND) | 보통 | 매우 낮음 (AND) | 보통 |
| Feature 수 | 3 (rolling stats) | 1 (원본) | 2 (평균, 분산) | 1 (원본) |
| 모델 필요 | 불필요 (통계 기반) | 불필요 | 불필요 | 불필요 |
| 해석성 | 어떤 feature가 변했는지 | D-stat, p-value | z-score | 누적합 |

### 언제 SHAP를 선택하나?

- **평균, 변동성, 추세 변화를 동시에 고려하고 싶다** → SHAP
- **오탐을 최소화하면서 실질적인 패턴 변화를 잡고 싶다** → SHAP 또는 OCDD
- **어떤 특성이 변했는지 알고 싶다** → SHAP (feature별 KS stat 제공)
- **분포 변화를 범용적으로 감지하고 싶다** → KS Test
- **미세한 평균 변화만 잡으면 된다** → CUSUM

---

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

---

## 차트 시각화

- **기본 차트**: Value 시계열 + drift 알람 마커
- **전문가 차트**: 각 feature별 KS stat 추이를 표시하는 확장이 가능하다 (`layers: []`). 향후 rolling_mean, rolling_std, rolling_diff의 KS stat을 개별 선으로 시각화할 예정이다.

---

## 참고 문헌

- Lundberg, S. M., & Lee, S.-I. (2017). "A Unified Approach to Interpreting Model Predictions." *NeurIPS*.
- Lundberg, S. M., Erion, G., Chen, H., et al. (2020). "From Local Explanations to Global Understanding with Explainable AI for Trees." *Nature Machine Intelligence*, 2, 56-67.
- Lu, J., Liu, A., Dong, F., Gu, F., Gama, J., & Zhang, G. (2018). "Learning under Concept Drift: A Review." *IEEE TKDE*, 31(12), 2346-2363.
- Rabanser, S., Gunnemann, S., & Lipton, Z. C. (2019). "Failing Loudly: An Empirical Study of Methods for Detecting Dataset Shift." *NeurIPS*.
