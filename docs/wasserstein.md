# Wasserstein Distance

## 개요
기준 구간(reference)과 슬라이딩 윈도우(test) 사이의 Wasserstein 거리(Earth Mover's Distance)를 계산하여 분포 변화를 감지하는 drift 탐지 알고리즘이다.

## 알고리즘 원리

### 수학적 배경

Wasserstein 거리(1차, p=1)는 두 확률분포 사이의 "최소 운반 비용"으로 정의된다.

**1차 Wasserstein 거리 (1D):**

$$W_1(F, G) = \int_{-\infty}^{\infty} |F(x) - G(x)| \, dx$$

여기서 $F$와 $G$는 각각 기준 구간과 테스트 윈도우의 누적분포함수(CDF)이다.

1차원에서 이 값은 두 분포의 정렬된 값들 사이의 평균 절대 차이와 동일하다.

**알람 조건:**

$$W_1(\text{ref}, \text{test}) > \text{threshold}$$

**Score:**

$$\text{score} = \frac{W_1}{\text{threshold}}$$

### 핵심 아이디어

Wasserstein 거리는 한 분포를 다른 분포로 "변환"하는 데 필요한 최소 작업량을 측정한다. 평균 이동, 분산 변화, 분포 형태 변화 등 모든 종류의 분포 차이에 민감하며, KS 검정과 달리 거리의 크기가 변화의 정도를 직접 반영한다.

## 파라미터

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| `window_size` | 50 | 테스트 슬라이딩 윈도우의 크기 |
| `reference_ratio` | 0.5 | 전체 데이터에서 기준 구간이 차지하는 비율 |
| `threshold` | 0.1 | 알람을 발생시키는 Wasserstein 거리 임계값 |

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

## 차트 시각화

- **기본 차트**: Value 시계열 + drift 알람 마커
- **전문가 차트**:
  - Y축(좌): 원본 Value
  - Y2축(우): Wasserstein Distance
    - `Distance` (보라색 선): Wasserstein 거리 추이
    - `Threshold` (빨간색 수평선): 임계값

## 적합한 상황

### 효과적인 경우
- 분포 변화의 크기(magnitude)를 정량적으로 측정하고 싶을 때
- 평균 이동, 분산 변화, 분포 형태 변화를 모두 감지하고 싶을 때
- 거리 기반의 직관적인 해석이 필요할 때
- 두 분포 간 차이가 연속적으로 증가하는 패턴을 추적할 때

### 한계점
- threshold를 데이터의 스케일에 맞게 수동으로 설정해야 한다 (기본값 0.1은 범용적이지 않을 수 있음)
- 통계적 유의성(p-value)을 직접 제공하지 않으므로, 임계값 선택이 주관적일 수 있다
- 기준 구간(reference) 크기가 작으면 거리 추정이 불안정하다
- 고차원 데이터에는 계산 비용이 크게 증가한다 (현재 구현은 1D)

## 참고 문헌

- Vaserstein, L. N. (1969). "Markov Processes over Denumerable Products of Spaces." *Problems of Information Transmission*, 5(3), 64-72.
- Ramdas, A., Garcia, N., & Cuturi, M. (2017). "On Wasserstein Two-Sample Testing and Related Families of Nonparametric Tests." *Entropy*, 19(2), 47.
- Villani, C. (2008). *Optimal Transport: Old and New*. Springer.
