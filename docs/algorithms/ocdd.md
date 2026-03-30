# OCDD (One-Class Drift Detector)

## 개요
기준 구간의 윈도우 통계량(평균, 표준편차) 분포를 학습한 뒤, 테스트 윈도우의 통계량이 z-score 기준으로 동시에 이상인지를 판단하는 drift 탐지 알고리즘이다.

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

**알람 조건:**

평균과 표준편차 모두 임계값을 초과해야 drift로 판단한다:

$$z_{\text{mean}} > z_{\text{threshold}} \quad \text{AND} \quad z_{\text{std}} > z_{\text{threshold}}$$

**Score:**

$$\text{score} = \frac{\max(z_{\text{mean}}, z_{\text{std}})}{z_{\text{threshold}}}$$

### 핵심 아이디어

정상 상태에서 윈도우 평균과 표준편차가 어떤 범위에 분포하는지를 학습한 뒤, 새로운 윈도우의 통계량이 이 범위를 벗어나면 drift로 판단한다. 평균과 표준편차가 동시에 이상이어야 alarm을 발생시키므로, 평균만 변하거나 표준편차만 변하는 단순한 변화에는 반응하지 않는다.

## 파라미터

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| `window_size` | 50 | 슬라이딩 윈도우의 크기 |
| `reference_ratio` | 0.5 | 전체 데이터에서 기준 구간이 차지하는 비율 |
| `z_threshold` | 3.0 | Z-score 임계값. 높을수록 보수적으로 판단한다. |

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

## 차트 시각화

- **기본 차트**: Value 시계열 + drift 알람 마커
- **전문가 차트**:
  - Y축(좌): 원본 Value
  - Y2축(우): Outlier Ratio
    - `Outlier Ratio` (파란색 선): $\max(z_{\text{mean}}, z_{\text{std}})$ 추이
    - `rho` (빨간색 수평선): z_threshold 임계값

## 적합한 상황

### 효과적인 경우
- 평균과 분산이 동시에 변하는 복합적인 drift를 감지할 때
- 정상 상태의 통계적 프로파일을 먼저 학습하고, 이로부터의 이탈을 모니터링하고 싶을 때
- One-Class 분류 개념을 적용한 이상 탐지가 필요할 때
- 평균만 변하거나 분산만 변하는 단순한 변동에 반응하지 않고 실질적인 regime change를 감지하고 싶을 때

### 한계점
- 평균만 변하거나 표준편차만 변하는 drift는 감지하지 못한다 (AND 조건)
- 기준 구간에서 윈도우 통계량의 분포 추정이 부정확하면 z-score가 부정확하다
- 기준 구간이 짧으면 윈도우 통계량 수집이 충분하지 않아 추정이 불안정하다
- z_threshold = 3.0은 정규분포 가정 하에서 약 0.27%의 오경보율에 해당하지만, 실제 분포가 비정규이면 달라질 수 있다

## 참고 문헌

- Tax, D. M. J., & Duin, R. P. W. (2004). "Support Vector Data Description." *Machine Learning*, 54(1), 45-66.
- Kuncheva, L. I. (2013). "Change Detection in Streaming Multivariate Data Using Likelihood Detectors." *IEEE TKDE*, 25(5), 1175-1180.
- Gama, J., Medas, P., Castillo, G., & Rodrigues, P. (2004). "Learning with Drift Detection." *SBIA*.
