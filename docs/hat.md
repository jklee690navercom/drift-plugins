# HAT (Hoeffding Adaptive Tree / ADWIN-like)

## 개요
Hoeffding bound를 이용하여 두 슬라이딩 윈도우(W0, W1)의 평균 차이가 통계적으로 유의한지를 판단하는 ADWIN 유사 drift 탐지 알고리즘이다.

## 알고리즘 원리

### 수학적 배경

이 알고리즘은 Hoeffding's inequality에 기반한 적응형(adaptive) drift 탐지기이다. ADWIN(Adaptive Windowing) 알고리즘의 핵심 아이디어를 구현한다.

**Hoeffding's Inequality:**

유계(bounded) 확률변수 $X \in [a, b]$에 대해, $n$개의 독립 관측값의 평균 $\bar{X}$에 대해:

$$P(|\bar{X} - E[X]| \geq \epsilon) \leq 2\exp\left(\frac{-2n\epsilon^2}{(b-a)^2}\right)$$

**Hoeffding Bound ($\epsilon$):**

두 윈도우 W0 (크기 $n_0$)와 W1 (크기 $n_1$)의 평균 차이에 대한 bound:

$$\epsilon = R \cdot \sqrt{\frac{\ln(2/\delta)}{2m}}$$

여기서:
- $R = \max(x) - \min(x)$: 데이터의 전체 범위
- $\delta$: 허용 오류 확률 (신뢰도 = $1 - \delta$)
- $m = \frac{2 n_0 n_1}{n_0 + n_1}$: $n_0$과 $n_1$의 조화 평균

**알람 조건:**

$$|\bar{x}_{W1} - \bar{x}_{W0}| > \epsilon$$

**Score:**

$$\text{score} = \frac{|\bar{x}_{W1} - \bar{x}_{W0}|}{\epsilon}$$

### 핵심 아이디어

최근 데이터(W1)와 이전 데이터(W0)의 평균을 비교하되, Hoeffding bound라는 이론적 경계를 사용하여 분포 가정 없이 통계적 유의성을 판단한다. Hoeffding bound는 데이터의 분포를 가정하지 않고, 데이터의 범위(range)만 알면 적용할 수 있다는 장점이 있다.

## 파라미터

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| `min_window` | 30 | 각 윈도우(W0, W1)의 최소 크기 |
| `delta` | 0.01 | Hoeffding bound의 오류 확률. 작을수록 보수적으로 판단한다. |
| `reference_ratio` | 0.5 | 기준 구간의 비율 (슬라이딩 시작 위치 결정) |

## 탐지 로직

`detect()` 메서드의 동작 순서:

1. **유효성 검사**: 기준 구간과 테스트 구간 모두 `min_window` 이상의 데이터가 필요하다.
2. **데이터 범위 계산**: 전체 데이터의 $R = \max - \min$을 구한다.
3. **슬라이딩 윈도우 비교**: `ref_end + min_window` 위치부터 데이터 끝까지 순회하며:
   - W0: `[i - 2*min_window, i - min_window)` 구간 (이전 윈도우)
   - W1: `[i - min_window, i)` 구간 (최근 윈도우)
   - 두 윈도우의 평균 차이 $|\bar{x}_{W1} - \bar{x}_{W0}|$를 계산한다.
   - Hoeffding bound $\epsilon$을 계산한다.
   - 평균 차이 > $\epsilon$이면 alarm으로 표시한다.
4. **연속 알람 그룹화**: 인접한 알람 인덱스를 gap=5 기준으로 그룹화한다.
5. **이벤트 생성**: 각 그룹에서 score가 가장 큰 시점을 peak로 선택한다.
6. **심각도 판정**: score >= 2.0이면 critical, >= 1.0이면 warning, 그 외 normal.

## 차트 시각화

- **기본 차트**: Value 시계열 + drift 알람 마커
- **전문가 차트**:
  - Y축(좌): 원본 Value
  - Y2축(우): Error Rate (score)
    - `Error Rate` (빨간색 선): score 추이 ($|\text{mean\_diff}| / \epsilon$)
    - `Threshold` (주황색 수평선): 1.0 (score = 1.0 이상이면 drift)

## 적합한 상황

### 효과적인 경우
- 데이터 분포에 대한 가정을 최소화하고 싶을 때 (분포 무관 bound)
- 온라인/스트리밍 환경에서 실시간으로 drift를 감지할 때
- 이론적 보장이 있는 탐지기가 필요할 때 (Hoeffding 부등식의 이론적 근거)
- 점진적인(gradual) 평균 변화와 급격한(abrupt) 변화 모두 감지하고 싶을 때

### 한계점
- Hoeffding bound는 매우 보수적(conservative)이어서, 실제로는 더 작은 변화도 유의할 수 있지만 놓칠 수 있다
- 데이터 범위($R$)에 이상치(outlier)가 있으면 bound가 과도하게 넓어진다
- 분산만 변하고 평균이 유지되는 경우에는 효과적이지 않다
- 윈도우 크기(`min_window`)에 의존하며, 크기가 너무 작으면 부정확하고 너무 크면 지연이 발생한다

## 참고 문헌

- Hoeffding, W. (1963). "Probability Inequalities for Sums of Bounded Random Variables." *Journal of the American Statistical Association*, 58(301), 13-30.
- Bifet, A., & Gavalda, R. (2007). "Learning from Time-Changing Data with Adaptive Windowing." *SIAM International Conference on Data Mining*.
- Domingos, P., & Hulten, G. (2000). "Mining High-Speed Data Streams." *KDD*.
