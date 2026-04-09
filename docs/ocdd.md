# OCDD (One-Class Drift Detector)

## 개요

기준 구간의 윈도우 통계량(평균, 표준편차) 분포를 학습한 뒤, 테스트 윈도우의 통계량이 z-score 기준으로 동시에 이상인지를 판단하는 drift 탐지 알고리즘이다. **One-Class SVM의 개념**을 통계적 프로파일링에 적용하여, 평균과 분산이 **동시에** 변하는 복합적인 regime change를 감지하는 데 적합하다.

---

## 알고리즘 원리

### 수학적 배경

OCDD는 One-Class 분류의 아이디어를 적용하여, 정상 상태(기준 구간)의 통계적 특성을 학습하고 이로부터의 이탈을 감지한다.

**기준 구간 윈도우 통계량 분포 추정:**

기준 구간에서 슬라이딩 윈도우를 이동하며 각 윈도우의 평균과 표준편차를 수집한다:

$$\mu_{\bar{x}} = \text{mean}(\{\bar{x}_{w_1}, \bar{x}_{w_2}, \ldots\})$$

$$\sigma_{\bar{x}} = \text{std}(\{\bar{x}_{w_1}, \bar{x}_{w_2}, \ldots\})$$

$$\mu_s = \text{mean}(\{s_{w_1}, s_{w_2}, \ldots\})$$

$$\sigma_s = \text{std}(\{s_{w_1}, s_{w_2}, \ldots\})$$

여기서 윈도우 간격(stride)은 $\max(1, \text{window\_size}/5)$이다.

**테스트 윈도우의 Z-score:**

$$z_{\text{mean}} = \frac{|\bar{x}_w - \mu_{\bar{x}}|}{\sigma_{\bar{x}}}$$

$$z_{\text{std}} = \frac{|s_w - \mu_s|}{\sigma_s}$$

### One-Class SVM과의 관계

One-Class SVM(OCSVM)은 정상 데이터만으로 학습하여 비정상 데이터를 탐지하는 비지도 학습 기법이다:

1. **학습 단계**: 정상 구간의 데이터 특성(윈도우 통계량)을 feature 공간에 매핑
2. **경계 설정**: 정상 데이터를 최대한 포함하는 최소 경계(hypersphere 또는 hyperplane) 설정
3. **이상치 판정**: 경계 밖의 데이터를 이상(drift)으로 판정

OCDD는 이 개념을 z-score 기반으로 단순화한다. 정상 구간에서의 통계량 분포(평균, 표준편차)를 학습하고, 새로운 윈도우의 통계량이 이 분포에서 크게 벗어나면 drift로 판단한다.

### 이상치 비율 추적

OCDD의 핵심 특징은 **이상치 비율**(outlier ratio)을 동적으로 추적하는 것이다:

$$\rho_t = \frac{\max(z_{\text{mean}}, z_{\text{std}})}{z_{\text{threshold}}}$$

$\rho_t > 1$이면 해당 윈도우가 이상 구간이다. 이 비율의 추이를 모니터링하여 drift의 진행 상황을 파악할 수 있다.

### 동적 윈도우 관리

기준 구간의 윈도우 통계량을 수집할 때, stride를 `window_size/5`로 설정하여 겹치는 윈도우를 사용한다. 이를 통해:

- **적은 데이터로도 충분한 통계량 수집**: 기준 구간이 짧아도 다수의 윈도우 통계량을 얻을 수 있다
- **통계량 분포의 안정적 추정**: 겹치는 윈도우로 자연스러운 평활화 효과

**알람 조건:**

평균과 표준편차 모두 임계값을 초과해야 drift로 판단한다:

$$z_{\text{mean}} > z_{\text{threshold}} \quad \text{AND} \quad z_{\text{std}} > z_{\text{threshold}}$$

**Score:**

$$\text{score} = \frac{\max(z_{\text{mean}}, z_{\text{std}})}{z_{\text{threshold}}}$$

### 핵심 아이디어

정상 상태에서 윈도우 평균과 표준편차가 어떤 범위에 분포하는지를 학습한 뒤, 새로운 윈도우의 통계량이 이 범위를 벗어나면 drift로 판단한다. 평균과 표준편차가 동시에 이상이어야 alarm을 발생시키므로, 평균만 변하거나 표준편차만 변하는 단순한 변화에는 반응하지 않는다.

---

## 파라미터

| 파라미터 | 기본값 | 설명 | 효과 |
|---|---|---|---|
| `window_size` | 50 | 슬라이딩 윈도우의 크기 | 크면 안정적이나 지연 증가 |
| `reference_ratio` | 0.5 | 기준 구간 비율 | 크면 정상 프로파일 추정 안정적 |
| `z_threshold` | 3.0 | Z-score 임계값 | 높을수록 보수적. 2.0: 민감, 3.0: 표준, 4.0: 보수적 |

---

## 데이터 시나리오

### ds_ocdd_sudden — 급격한 복합 변화

| 구간 | 시점 | 패턴 | OCDD 반응 |
|------|------|------|-----------|
| 정상 | 0~199 | $\mu=50, \sigma=2$ | $z_{\text{mean}}, z_{\text{std}}$ 모두 낮음 |
| 평균만 이동 | 200~299 | $\mu=55, \sigma=2$ | $z_{\text{mean}}$ 높지만 $z_{\text{std}}$ 정상 → **미탐지** |
| 분산만 증가 | 300~399 | $\mu=50, \sigma=6$ | $z_{\text{std}}$ 높지만 $z_{\text{mean}}$ 정상 → **미탐지** |
| 동시 변화 | 400~499 | $\mu=55, \sigma=6$ | $z_{\text{mean}}, z_{\text{std}}$ 모두 높음 → **alarm** |

이 시나리오는 OCDD의 **AND 조건**의 의미를 명확히 보여준다. 평균만 또는 분산만 변하는 경우는 무시하고, 둘 다 변하는 진정한 regime change만 탐지한다. 이 특성은 용도에 따라 장점(오탐 감소)이 될 수도 있고 단점(미탐지)이 될 수도 있다.

---

## 다른 알고리즘과의 비교

| 특성 | OCDD | CUSUM | EWMA | KS Test |
|------|------|-------|------|---------|
| 평균 변화 감지 | AND 조건 | **단독 감지** | **단독 감지** | 감지 |
| 분산 변화 감지 | AND 조건 | 불가 | 불가 | **감지** |
| 복합 변화 | **전문** | 불가 | 불가 | 감지 |
| 오탐율 | **매우 낮음** | 조절 가능 | 조절 가능 | 조절 가능 |
| 학습 필요 | 기준 프로파일 | 불필요 | 기준 구간 | 기준 구간 |

### 언제 OCDD를 선택하나?

- **평균과 분산이 동시에 변하는 regime change만 잡고 싶다** → OCDD
- **오탐을 최소화하고 싶다 (AND 조건)** → OCDD
- **평균 변화만이라도 잡고 싶다** → CUSUM 또는 EWMA
- **모든 종류의 분포 변화를 잡고 싶다** → KS Test

---

## 탐지 로직

`detect()` 메서드의 동작 순서:

1. **구간 분리**: 데이터의 앞쪽 `reference_ratio` 비율을 기준 구간으로 설정한다.
2. **기준 통계량 계산**: 기준 구간의 전체 평균/표준편차를 계산한다.
3. **기준 윈도우 통계량 분포 추정**: 기준 구간에서 `window_size` 크기의 윈도우를 stride(`window_size/5`)씩 이동하며 각 윈도우의 평균과 표준편차를 수집한다. 이들의 평균과 표준편차를 구하여 정상 범위를 정의한다.
4. **슬라이딩 윈도우 Z-score 계산**: 기준 구간 이후부터 윈도우를 이동하며:
   - 윈도우 평균의 z-score ($z_{\text{mean}}$)와 표준편차의 z-score ($z_{\text{std}}$)를 계산한다.
   - 윈도우 중간 지점(mid)에 기록한다.
5. **알람 판정**: $z_{\text{mean}} > z_{\text{threshold}}$ AND $z_{\text{std}} > z_{\text{threshold}}$이면 alarm으로 표시한다.
6. **연속 알람 그룹화**: 인접한 알람 인덱스를 gap=5 기준으로 그룹화한다.
7. **이벤트 생성**: 각 그룹에서 $\max(z_{\text{mean}}, z_{\text{std}})$가 가장 큰 시점을 peak로 선택하고, score를 계산한다.
8. **심각도 판정**: score >= 2.0이면 critical, >= 1.0이면 warning, 그 외 normal.

---

## 차트 시각화

- **기본 차트**: Value 시계열 + drift 알람 마커
- **전문가 차트**:
  - Y축(좌): 원본 Value
  - Y2축(우): Outlier Ratio
    - `Outlier Ratio` (파란색 선): $\max(z_{\text{mean}}, z_{\text{std}})$ 추이
    - `rho` (빨간색 수평선): z_threshold 임계값

---

## 참고 문헌

- Tax, D. M. J., & Duin, R. P. W. (2004). "Support Vector Data Description." *Machine Learning*, 54(1), 45-66.
- Scholkopf, B., Platt, J. C., Shawe-Taylor, J., Smola, A. J., & Williamson, R. C. (2001). "Estimating the Support of a High-Dimensional Distribution." *Neural Computation*, 13(7), 1443-1471.
- Kuncheva, L. I. (2013). "Change Detection in Streaming Multivariate Data Using Likelihood Detectors." *IEEE TKDE*, 25(5), 1175-1180.
- Gama, J., Medas, P., Castillo, G., & Rodrigues, P. (2004). "Learning with Drift Detection." *SBIA*.
