# CUSUM (Cumulative Sum)

## 개요
양방향 누적합(CUSUM) 통계량을 이용하여 시계열 평균의 상승 또는 하락을 감지하는 순차적 drift 탐지 알고리즘이다.

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

### 핵심 아이디어

데이터가 정상 상태에서 벗어나면 CUSUM 통계량이 점진적으로 누적되어 증가한다. 임계값 $h$를 초과하는 순간 drift로 판단한다. slack value $k$는 작은 변동을 무시하고 의미 있는 변화만 누적하도록 한다.

## 파라미터

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| `k` | 0.25 | Slack value. 표준화된 단위에서 허용하는 편차. 작을수록 민감하다. |
| `h` | 5.0 | Threshold. 표준화된 단위에서 알람을 발생시키는 누적합 임계값. |
| `reset` | True | 알람 발생 후 CUSUM 통계량을 0으로 리셋할지 여부. |

## 탐지 로직

`detect()` 메서드의 동작 순서:

1. **데이터 표준화**: 입력 시계열에서 median과 MAD를 계산하고, robust 표준화를 수행한다.
2. **CUSUM 통계량 계산**: 표준화된 값에 대해 양방향 CUSUM($S^+$, $S^-$)을 순차적으로 계산한다.
3. **알람 판정**: $S^+$ 또는 $S^-$가 임계값 $h$를 초과하면 해당 시점을 alarm으로 표시한다.
4. **리셋 처리**: `reset=True`이면 알람 발생 후 $S^+$와 $S^-$를 모두 0으로 초기화한다.
5. **연속 알람 그룹화**: 인접한 알람 인덱스를 gap=3 기준으로 그룹화한다.
6. **이벤트 생성**: 각 그룹에서 $\max(S^+, S^-)$가 가장 큰 시점을 peak로 선택하고, `score = max(S_pos, S_neg) / h`를 계산한다.
7. **심각도 판정**: score >= 2.0이면 critical, >= 1.0이면 warning, 그 외 normal.

## 차트 시각화

- **기본 차트**: Value 시계열 + drift 알람 마커
- **전문가 차트**:
  - Y축(좌): 원본 Value
  - Y2축(우): CUSUM 통계량
    - `S+` (빨간색 선): 상향 누적합
    - `S-` (초록색 선): 하향 누적합
    - `h` (주황색 수평선): 임계값 threshold

## 적합한 상황

### 효과적인 경우
- 프로세스 평균의 점진적(gradual) 변화를 감지할 때
- 작은 크기의 지속적인 평균 이동(small persistent shift)을 조기에 탐지할 때
- 실시간 순차 모니터링이 필요한 경우
- 양방향(상승/하락) 변화를 동시에 감시해야 할 때

### 한계점
- 분산(산포)의 변화만 있는 경우에는 효과적이지 않다
- 데이터 분포가 심하게 비대칭이면 MAD 기반 표준화가 부정확할 수 있다
- $k$와 $h$ 파라미터 튜닝이 필요하며, 잘못 설정하면 과다/과소 탐지가 발생한다
- 비정상(non-stationary) 시계열에는 직접 적용이 어렵다

## 참고 문헌

- Page, E. S. (1954). "Continuous Inspection Schemes." *Biometrika*, 41(1/2), 100-115.
- Montgomery, D. C. (2019). *Introduction to Statistical Quality Control*, 8th Edition. Wiley.
- Hawkins, D. M., & Olwell, D. H. (1998). *Cumulative Sum Charts and Charting for Quality Improvement*. Springer.
