# Wasserstein Distance

## 개요

기준 구간(reference)과 슬라이딩 윈도우(test) 사이의 Wasserstein 거리(Earth Mover's Distance)를 계산하여 분포 변화를 감지하는 drift 탐지 알고리즘이다. **분포 간 변화의 크기를 정량적으로 측정**할 수 있어, 변화의 심각도를 수치적으로 비교하고 싶을 때 적합하다.

---

## 알고리즘 원리

### 수학적 배경

Wasserstein 거리는 **최적 수송 이론**(Optimal Transport)에서 유래한 거리 측도로, 한 분포를 다른 분포로 "운반"하는 데 필요한 최소 비용을 측정한다.

**1차 Wasserstein 거리 (1D):**

$$W_1(F, G) = \int_{-\infty}^{\infty} |F(x) - G(x)| \, dx$$

여기서 $F$와 $G$는 각각 기준 구간과 테스트 윈도우의 누적분포함수(CDF)이다.

1차원에서 이 값은 두 분포의 **정렬된 값들 사이의 평균 절대 차이**와 동일하다:

$$W_1 = \frac{1}{n} \sum_{i=1}^{n} |F^{-1}(i/n) - G^{-1}(i/n)|$$

**일반적인 p차 Wasserstein 거리:**

$$W_p(F, G) = \left(\inf_{\pi \in \Pi(F, G)} \int \|x - y\|^p \, d\pi(x, y)\right)^{1/p}$$

여기서 $\Pi(F, G)$는 $F$와 $G$의 결합분포(coupling)의 집합이다.

### 3가지 검정 전략

#### 1. WWDD (Wasserstein-based Window Drift Detection)

기본 전략. 슬라이딩 윈도우의 Wasserstein 거리를 고정 임계값과 비교한다.

$$W_1(\text{ref}, \text{test}) > \text{threshold} \quad \Rightarrow \quad \text{drift}$$

장점: 간단하고 직관적. 단점: 임계값을 데이터 스케일에 맞게 설정해야 한다.

#### 2. EWMA + Wasserstein

Wasserstein 거리에 EWMA 평활화를 적용하여 노이즈를 줄이고 점진적 변화에 민감하게 반응한다.

$$W_t^{\text{ewma}} = \lambda \cdot W_t + (1 - \lambda) \cdot W_{t-1}^{\text{ewma}}$$

$$W_t^{\text{ewma}} > \text{threshold} \quad \Rightarrow \quad \text{drift}$$

장점: 일시적 변동에 견고. 점진적 분포 변화에 강함.

#### 3. Label Shift Detection

분류 모델의 출력 확률 분포에 대해 Wasserstein 거리를 계산하여 label shift를 감지한다. 모델 예측 분포가 학습 시와 달라지면 alarm을 발생시킨다.

### 슬라이스드 Wasserstein 근사 (Sliced Wasserstein)

고차원 데이터에서 정확한 Wasserstein 거리 계산은 $O(n^3 \log n)$의 비용이 든다. 슬라이스드 Wasserstein은 랜덤 1차원 투영을 사용하여 근사한다:

$$SW_p(F, G) = \left(\int_{S^{d-1}} W_p^p(F_\theta, G_\theta) \, d\theta\right)^{1/p}$$

여기서 $F_\theta$는 방향 $\theta$로의 투영 분포이다. 실제로는 유한 개의 랜덤 방향을 샘플링하여 근사한다:

$$\widehat{SW}_p \approx \frac{1}{L} \sum_{l=1}^{L} W_p(F_{\theta_l}, G_{\theta_l})$$

이 방식은 $O(Ln \log n)$으로 계산할 수 있어 고차원에서도 실용적이다.

**알람 조건:**

$$W_1(\text{ref}, \text{test}) > \text{threshold}$$

**Score:**

$$\text{score} = \frac{W_1}{\text{threshold}}$$

### 핵심 아이디어

Wasserstein 거리는 한 분포를 다른 분포로 "변환"하는 데 필요한 최소 작업량을 측정한다. 평균 이동, 분산 변화, 분포 형태 변화 등 모든 종류의 분포 차이에 민감하며, KS 검정과 달리 거리의 크기가 변화의 정도를 직접 반영한다.

---

## 파라미터

| 파라미터 | 기본값 | 설명 | 효과 |
|---|---|---|---|
| `window_size` | 50 | 테스트 슬라이딩 윈도우 크기 | 크면 안정적, 작으면 빠른 반응 |
| `reference_ratio` | 0.5 | 기준 구간 비율 | 기준 분포 추정에 사용 |
| `threshold` | 0.1 | Wasserstein 거리 임계값 | 데이터 스케일에 맞춰 조정 필요 |

### threshold 설정 가이드

threshold는 데이터의 스케일에 의존하므로 적절한 설정이 중요하다:

| 데이터 스케일 | 권장 threshold | 예시 |
|------|------|------|
| 0~1 범위 (비율) | 0.01~0.05 | 에러율, 확률 |
| 0~100 범위 | 1.0~5.0 | 점수, 백분율 |
| 자유 스케일 | $0.1 \times \text{std}(\text{ref})$ | 센서 값, 측정값 |

---

## 데이터 시나리오

### ds_wasserstein_4pattern — 4가지 분포 변화 패턴

| 구간 | 시점 | 패턴 | Wasserstein 반응 |
|------|------|------|------------------|
| 정상 | 0~149 | $N(0, 1)$ | $W_1 \approx 0$, threshold 이내 |
| 평균 이동 | 150~249 | $N(1.5, 1)$ | $W_1 \approx 1.5$ → alarm |
| 분산 증가 | 250~349 | $N(0, 4)$ | $W_1$ 증가 (분산 변화도 감지) |
| 형태 변화 | 350~449 | 이중봉 분포 | $W_1$ 추가 증가 (형태 변화도 반영) |
| 복귀 | 450~599 | $N(0, 1)$ | $W_1 \to 0$ 복귀 |

이 시나리오는 Wasserstein 거리의 **범용성**과 **정량적 비교 가능성**을 보여준다. 각 패턴에서의 $W_1$ 값이 변화의 크기를 직접 반영하므로, "평균 이동 1.5가 분산 증가보다 심각한가?"를 수치적으로 답할 수 있다.

---

## 다른 알고리즘과의 비교

| 특성 | Wasserstein | KS Test | CUSUM | Hotelling T² |
|------|-------------|---------|-------|-------------|
| 출력 | **거리 (정량적)** | D-stat + p-value | 누적합 | T² 통계량 |
| 분포 가정 | 비모수 | 비모수 | 정규 가정 | 다변량 정규 |
| 변화 크기 비교 | **직접 비교 가능** | 상대적 비교만 | 불가 | 불가 |
| 평균 변화 | 감지 | 감지 | **매우 강함** | 감지 |
| 분산 변화 | **감지** | **감지** | 불가 | 부분적 |
| 점진적 변화 | 보통 | 보통 | **강함** | 보통 |
| 고차원 | 슬라이스드 근사 | 변수별 개별 | 불가 | **네이티브** |

### 언제 Wasserstein을 선택하나?

- **분포 변화의 크기를 수치적으로 비교하고 싶다** → Wasserstein
- **분포가 어떻게 바뀌든 감지하고 싶다** → KS Test (p-value 기반) 또는 Wasserstein
- **평균의 미세한 변화를 빠르게 잡고 싶다** → CUSUM
- **여러 변수를 동시에 보고 싶다** → Hotelling T² 또는 MEWMA

---

## 탐지 로직

`detect()` 메서드의 동작 순서:

1. **구간 분리**: 데이터의 앞쪽 `reference_ratio` 비율을 기준 구간으로 설정한다.
2. **유효성 검사**: 기준 구간과 테스트 구간 모두 `window_size` 이상의 데이터가 필요하다.
3. **슬라이딩 윈도우 거리 계산**: 기준 구간 이후부터 `window_size` 크기의 윈도우를 이동하며 `scipy.stats.wasserstein_distance(reference, window)`를 계산한다.
4. **결과 기록**: 각 윈도우의 중간 지점(mid)에 거리 값을 기록한다.
5. **알람 판정**: 거리 > threshold이면 해당 시점을 alarm으로 표시한다.
6. **연속 알람 그룹화**: 인접한 알람 인덱스를 gap=5 기준으로 그룹화한다.
7. **이벤트 생성**: 각 그룹에서 거리가 가장 큰 시점을 peak로 선택하고, score = distance/threshold를 계산한다.
8. **심각도 판정**: score >= 2.0이면 critical, >= 1.0이면 warning, 그 외 normal.

---

## 차트 시각화

- **기본 차트**: Value 시계열 + drift 알람 마커
- **전문가 차트**:
  - Y축(좌): 원본 Value
  - Y2축(우): Wasserstein Distance
    - `Distance` (보라색 선): Wasserstein 거리 추이
    - `Threshold` (빨간색 수평선): 임계값

---

## 참고 문헌

- Vaserstein, L. N. (1969). "Markov Processes over Denumerable Products of Spaces." *Problems of Information Transmission*, 5(3), 64-72.
- Ramdas, A., Garcia, N., & Cuturi, M. (2017). "On Wasserstein Two-Sample Testing and Related Families of Nonparametric Tests." *Entropy*, 19(2), 47.
- Villani, C. (2008). *Optimal Transport: Old and New*. Springer.
- Bonneel, N., van de Panne, M., Paris, S., & Heidrich, W. (2015). "Sliced and Radon Wasserstein Barycenters of Measures." *Journal of Mathematical Imaging and Vision*, 51(1), 22-45.
