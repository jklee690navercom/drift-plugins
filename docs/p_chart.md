# P Chart

## 개요

불량률(비율 데이터)을 이항분포 기반 제어 한계로 모니터링하는 제어 차트(control chart) 기반 drift 탐지 알고리즘이다. **합격/불합격 이진 판정 결과의 비율 변화**를 감지하는 데 적합하며, 품질 관리에서 불량률 추적의 표준 방법이다.

---

## 알고리즘 원리

### 수학적 배경

P Chart는 각 검사 그룹에서의 불량 비율(proportion defective)을 모니터링하는 속성형 제어 차트이다. 불량 수는 이항분포를 따른다고 가정한다.

**중심선 (Center Line):**

$$CL = \bar{p}$$

여기서 $\bar{p}$는 기준 구간의 평균 불량률이다.

**표준편차:**

$$\sigma = \sqrt{\frac{\bar{p}(1 - \bar{p})}{n}}$$

여기서 $n$은 각 검사 그룹의 샘플 크기(`sample_size`)이다.

**제어 한계 (Control Limits):**

$$UCL = \bar{p} + 3\sigma = \bar{p} + 3\sqrt{\frac{\bar{p}(1 - \bar{p})}{n}}$$

$$LCL = \max\left(0, \bar{p} - 3\sigma\right)$$

**알람 조건:**

$$p_i > UCL \quad \text{또는} \quad p_i < LCL$$

**Score:**

$$\text{score} = \frac{\max|p_i - \bar{p}|}{3\sigma}$$

### 핵심 아이디어

이항분포의 정규 근사를 이용하여 3-시그마 제어 한계를 설정한다. 불량률이 제어 한계를 벗어나면 프로세스 품질에 변화가 생긴 것으로 판단한다. 샘플 크기 $n$이 클수록 제어 한계가 좁아져서 작은 비율 변화도 감지할 수 있다.

---

## 파라미터

| 파라미터 | 기본값 | 설명 | 효과 |
|---|---|---|---|
| `sample_size` | 50 | 각 검사 그룹의 샘플 크기 | 크면 제어 한계가 좁아짐 (민감). 작으면 넓어짐 (둔감) |
| `reference_ratio` | 0.5 | 기준 구간 비율 | 기준 불량률 $\bar{p}$ 추정에 사용 |

---

## 데이터 시나리오

### ds_spc_defects — SPC 비율 데이터

| 구간 | 시점 | 패턴 | P Chart 반응 |
|------|------|------|-------------|
| 정상 | 0~99 | 불량률 ~ 3% ($\bar{p}=0.03$) | UCL, LCL 이내 |
| 불량 증가 | 100~199 | 불량률 ~ 8% | UCL 초과 포인트 다수 → alarm |
| 정상 복귀 | 200~299 | 불량률 ~ 3% | 제어 한계 이내 복귀 |
| 품질 개선 | 300~399 | 불량률 ~ 0.5% | LCL 미만 (양의 변화 감지) |

이 시나리오에서 `sample_size`의 효과를 확인할 수 있다. $n=50$일 때 $\sigma = \sqrt{0.03 \times 0.97 / 50} \approx 0.024$이므로 UCL $\approx$ 0.102. $n=200$이면 UCL $\approx$ 0.066으로 더 민감해진다.

---

## 다른 알고리즘과의 비교

| 특성 | P Chart | C Chart | EWMA | KS Test |
|------|---------|---------|------|---------|
| 데이터 유형 | **비율 (0~1)** | 카운트 (정수) | 연속형 | 모든 유형 |
| 분포 가정 | 이항 | 포아송 | 정규 | 비모수 |
| 추가 파라미터 | sample_size | 없음 | lambda, L | window_size, alpha |
| 점진적 변화 | 약함 | 약함 | **강함** | 보통 |
| 해석 용이성 | **매우 쉬움** | 매우 쉬움 | 보통 | 보통 |

### 언제 P Chart를 선택하나?

- **불량률, 오류율, 전환율 등 비율 데이터** → P Chart
- **결함 수, 에러 횟수 등 카운트 데이터** → C Chart
- **비율의 점진적 변화를 잡고 싶다** → EWMA (비율 데이터에 적용)
- **비율 분포 자체의 변화를 보고 싶다** → KS Test

---

## 탐지 로직

`detect()` 메서드의 동작 순서:

1. **기준 구간 설정**: 데이터의 앞쪽 `reference_ratio` 비율을 기준 구간으로 사용한다 (최소 2개).
2. **중심선 계산**: 기준 구간의 평균 불량률 $\bar{p}$를 계산한다.
3. **표준편차 계산**: $\sigma = \sqrt{\bar{p}(1-\bar{p})/n}$. $\bar{p}$가 0 또는 1이면 $\sigma = 10^{-8}$로 설정한다.
4. **제어 한계 계산**: UCL = $\bar{p} + 3\sigma$, LCL = $\max(0, \bar{p} - 3\sigma)$.
5. **알람 판정**: 전체 데이터에서 UCL 초과 또는 LCL 미만인 시점을 alarm으로 표시한다.
6. **연속 알람 그룹화**: 인접한 알람 인덱스를 gap=3 기준으로 그룹화한다.
7. **이벤트 생성**: 각 그룹에서 중심선으로부터 가장 크게 벗어난 시점을 peak로 선택하고, score를 계산한다.
8. **심각도 판정**: score >= 2.0이면 critical, >= 1.0이면 warning, 그 외 normal.

---

## 차트 시각화

- **기본 차트**: 불량률(Proportion Defective) 시계열 + drift 알람 마커
- **전문가 차트**:
  - Y축: Proportion
    - `UCL` (주황색 수평선): 상한 제어 한계
    - `CL` (초록색 수평선): 중심선 ($\bar{p}$)
    - `LCL` (주황색 수평선): 하한 제어 한계

---

## 참고 문헌

- Shewhart, W. A. (1931). *Economic Control of Quality of Manufactured Product*. Van Nostrand.
- Montgomery, D. C. (2019). *Introduction to Statistical Quality Control*, 8th Edition. Wiley.
- Ryan, T. P. (2011). *Statistical Methods for Quality Improvement*, 3rd Edition. Wiley.
