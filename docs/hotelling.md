# Hotelling T²

## 개요

Hotelling T² 통계량을 이용하여 슬라이딩 윈도우의 평균(벡터)이 기준 구간 평균에서 유의하게 벗어났는지를 검정하는 drift 탐지 알고리즘이다. 다변량 데이터에서 **변수 간 상관관계를 고려한 평균 변화**를 감지하는 데 적합하며, 다변량 SPC의 대표적인 방법이다.

---

## 알고리즘 원리

### 수학적 배경

Hotelling T²는 다변량 통계에서 평균 벡터의 변화를 검정하는 방법이다.

**다변량 T² 통계량:**

$$T^2 = n_w \cdot (\bar{\mathbf{x}}_w - \bar{\mathbf{x}}_{\text{ref}})^T \mathbf{S}_{\text{ref}}^{-1} (\bar{\mathbf{x}}_w - \bar{\mathbf{x}}_{\text{ref}})$$

여기서:
- $n_w$: 테스트 윈도우의 크기
- $\bar{\mathbf{x}}_w$: 테스트 윈도우의 평균 벡터
- $\bar{\mathbf{x}}_{\text{ref}}$: 기준 구간의 평균 벡터
- $\mathbf{S}_{\text{ref}}$: 기준 구간의 공분산 행렬

**단변량의 경우:**

$$T^2 = n_w \cdot \frac{(\bar{x}_w - \bar{x}_{\text{ref}})^2}{s_{\text{ref}}^2}$$

### 공분산 수축 (Shrinkage)

변수 수 $p$가 표본 수 $n$에 비해 클 때, 표본 공분산 행렬 $\mathbf{S}$는 불안정하거나 특이(singular)해질 수 있다. 공분산 수축은 표본 공분산과 구조화된 추정량(대각 행렬 등)을 혼합하여 안정적인 추정을 제공한다:

$$\hat{\Sigma} = (1 - \gamma) \mathbf{S} + \gamma \cdot \text{diag}(\mathbf{S})$$

여기서 $\gamma \in [0, 1]$는 수축 강도이며, Ledoit-Wolf 방법 등으로 자동 결정할 수 있다.

### F-분포 변환

$T^2$ 통계량을 F-분포로 변환하여 정확한 p-value를 계산할 수 있다:

$$F = \frac{n_{\text{ref}} + n_w - p - 1}{(n_{\text{ref}} + n_w - 2) \cdot p} \cdot T^2$$

$$F \sim F(p, n_{\text{ref}} + n_w - p - 1)$$

표본 크기가 충분히 크면 카이제곱 근사도 유효하다:

$$\text{UCL} = \chi^2_{1-\alpha}(df=p)$$

### 포인트 검정 vs 윈도우 검정

| 방식 | 설명 | 특징 |
|------|------|------|
| 포인트 검정 | 개별 관측값 $\mathbf{x}_t$와 기준 평균을 비교 | 실시간 모니터링, 민감하지만 노이즈에 취약 |
| 윈도우 검정 | 윈도우 평균 $\bar{\mathbf{x}}_w$와 기준 평균을 비교 | 안정적, 중심극한정리로 정규성 보강 |

현재 구현은 **윈도우 검정** 방식이다. 포인트 검정이 필요하면 `window_size=1`로 설정할 수 있으나, 이 경우 $T^2$ 값의 변동이 크다.

**알람 조건:**

$$T^2 > \text{UCL}$$

**Score:**

$$\text{score} = \frac{T^2}{\text{UCL}}$$

### 핵심 아이디어

기준 구간의 평균과 공분산을 안정 상태의 기준값으로 삼고, 슬라이딩 윈도우의 평균이 이 기준에서 통계적으로 유의하게 벗어났는지를 검정한다. 공분산 행렬을 사용하므로 변수 간 상관관계를 반영한 종합적인 판단이 가능하다.

---

## 파라미터

| 파라미터 | 기본값 | 설명 | 효과 |
|---|---|---|---|
| `alpha` | 0.01 | 유의수준 | 작을수록 보수적. UCL이 커져서 오탐 감소 |
| `window_size` | 50 | 테스트 슬라이딩 윈도우 크기 | 크면 안정적이나 지연 증가, 작으면 민감 |
| `reference_ratio` | 0.5 | 기준 구간 비율 | 기준 평균/공분산 추정에 사용 |

---

## 데이터 시나리오

### ds_hotelling_multivar — 5변량 3단계 변화

| 구간 | 시점 | 패턴 | Hotelling T² 반응 |
|------|------|------|-------------------|
| 정상 | 0~199 | 5개 변수 정상 ($\boldsymbol{\mu}_0, \Sigma_0$) | $T^2$ 낮음, UCL 이내 |
| 평균 이동 | 200~349 | 변수 2개 평균 1.5σ 이동 | $T^2$ 급상승 → 즉시 alarm |
| 상관 변화 | 350~499 | 변수 간 상관 구조 변화 | 공분산 기반이므로 탐지 가능 |

이 시나리오에서 Hotelling T²는 **급격한 다변량 평균 이동**을 윈도우 단위로 즉시 감지한다. 점진적 변화에서는 MEWMA가 더 빠르게 반응하지만, 급격한 변화에서는 Hotelling이 더 직접적이다.

---

## 다른 알고리즘과의 비교

| 특성 | Hotelling T² | MEWMA | KS Test | CUSUM |
|------|-------------|-------|---------|-------|
| 다변량 지원 | **네이티브** | **네이티브** | 변수별 개별 | 단변량 |
| 상관관계 고려 | **공분산 행렬** | **공분산 행렬** | 불가 | 불가 |
| 점진적 변화 | 보통 | **강함** | 보통 | **강함** |
| 급격한 변화 | **강함** | 보통 | 강함 | 강함 |
| 분산 변화 감지 | 부분적 | 부분적 | **가능** | 불가 |
| p-value 제공 | F-분포로 가능 | 카이제곱 근사 | **정확** | 불가 |

### 언제 Hotelling T²를 선택하나?

- **여러 변수의 급격한 평균 변화를 잡고 싶다** → Hotelling T²
- **여러 변수의 점진적 변화를 잡고 싶다** → MEWMA
- **단변량 평균 변화** → CUSUM 또는 EWMA
- **분포 자체의 변화** → KS Test

---

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

---

## 차트 시각화

- **기본 차트**: Value 시계열 + drift 알람 마커
- **전문가 차트**:
  - Y축(좌): 원본 Value
  - Y2축(우): T² 통계량
    - `T²` (파란색 선): Hotelling T² 통계량
    - `chi2 threshold` (빨간색 수평선): 카이제곱 임계값

---

## 참고 문헌

- Hotelling, H. (1947). "Multivariate Quality Control." *Techniques of Statistical Analysis*. McGraw-Hill.
- Montgomery, D. C. (2019). *Introduction to Statistical Quality Control*, 8th Edition. Wiley.
- Lowry, C. A., & Montgomery, D. C. (1995). "A Review of Multivariate Control Charts." *IIE Transactions*, 27(6), 800-810.
- Ledoit, O., & Wolf, M. (2004). "A well-conditioned estimator for large-dimensional covariance matrices." *Journal of Multivariate Analysis*, 88(2), 365-411.
