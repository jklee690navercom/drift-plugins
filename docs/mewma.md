# MEWMA (Multivariate Exponentially Weighted Moving Average)

## 개요

다변량 지수가중이동평균(MEWMA) 관리도를 이용하여 **여러 변수의 평균 벡터가 동시에 변하는지**를 마할라노비스 거리 기반으로 감지하는 drift 탐지 알고리즘이다. 변수 간 상관관계를 고려하면서 점진적인 다변량 평균 이동을 탐지하는 데 적합하다.

---

## 알고리즘 원리

### 수학적 배경

MEWMA는 Lowry et al.(1992)이 제안한 방법으로, 단변량 EWMA를 다변량으로 확장한 것이다.

**다변량 EWMA 통계량 (벡터 버전):**

$$\mathbf{Z}_t = \Lambda \mathbf{X}_t + (\mathbf{I} - \Lambda) \mathbf{Z}_{t-1}$$

여기서:
- $\mathbf{Z}_t$: 시점 $t$에서의 $p$-차원 EWMA 벡터
- $\mathbf{X}_t$: 시점 $t$에서의 $p$-차원 관측 벡터
- $\Lambda = \text{diag}(\lambda_1, \lambda_2, \ldots, \lambda_p)$: 평활 상수 대각 행렬 (일반적으로 $\lambda_i = \lambda$)
- $\mathbf{I}$: 단위 행렬
- $\mathbf{Z}_0 = \boldsymbol{\mu}_0$ (기준 구간의 평균 벡터)

단변량의 경우 $p=1$이므로:

$$z_t = \lambda \cdot x_t + (1 - \lambda) \cdot z_{t-1}$$

**공분산 행렬:**

MEWMA 통계량의 공분산 행렬:

$$\Sigma_{\mathbf{Z}} = \frac{\lambda}{2 - \lambda}\left[1 - (1-\lambda)^{2t}\right] \Sigma$$

정상 상태에서:

$$\Sigma_{\mathbf{Z}} \approx \frac{\lambda}{2 - \lambda} \Sigma$$

여기서 $\Sigma$는 기준 구간의 공분산 행렬이다.

**마할라노비스 거리 (D² 통계량):**

$$D^2_t = (\mathbf{Z}_t - \boldsymbol{\mu}_0)^T \Sigma_{\mathbf{Z}}^{-1} (\mathbf{Z}_t - \boldsymbol{\mu}_0)$$

단변량에서는:

$$D^2_t = \frac{(z_t - \bar{x}_{\text{ref}})^2}{\text{Var}(x_{\text{ref}})}$$

**임계값 (카이제곱 분포):**

$$\text{UCL} = \chi^2_{1-\alpha}(df=p)$$

$p$는 변수의 수이다. 단변량이면 $df=1$, 5변량이면 $df=5$이다.

**알람 조건:**

$$D^2_t > \text{UCL}$$

**Score:**

$$\text{score} = \frac{D^2_{\text{peak}}}{\text{UCL}}$$

### 핵심 아이디어

다변량 EWMA 평활화로 각 변수의 단기 노이즈를 제거한 뒤, 평활화된 벡터가 기준 평균 벡터에서 얼마나 벗어났는지를 마할라노비스 거리로 측정한다. 마할라노비스 거리는 변수 간 상관관계를 반영하므로, 단순히 변수별로 따로 검정하는 것보다 정확한 다변량 이상 판단이 가능하다.

---

## 파라미터

| 파라미터 | 기본값 | 설명 | 효과 |
|---|---|---|---|
| `lambda_` | 0.1 | EWMA 평활 상수. | 작을수록 과거 데이터에 더 많은 가중치. 0.05~0.25 범위 권장 |
| `reference_ratio` | 0.5 | 기준 구간 비율. | 기준 평균 벡터와 공분산 행렬 추정에 사용 |
| `alpha` | 0.01 | 유의수준. | 작을수록 보수적 판단. UCL이 커져서 오탐 감소 |

---

## 데이터 시나리오

### ds_hotelling_multivar — 5변량 3단계 변화

| 구간 | 시점 | 패턴 | MEWMA 반응 |
|------|------|------|------------|
| 정상 | 0~199 | 5개 변수 정상 ($\boldsymbol{\mu}_0, \Sigma_0$) | $D^2_t \approx p$ 수준, UCL 이내 |
| 평균 이동 | 200~349 | 2개 변수 평균 1σ 이동 | $D^2_t$ 증가, EWMA 평활화로 230 부근에서 UCL 돌파 |
| 상관 변화 | 350~499 | 변수 간 상관 구조 변화 | 공분산 구조 변화로 $D^2_t$ 추가 증가 |

이 시나리오는 **다변량 평균 이동**과 **상관 구조 변화**에 대한 MEWMA의 감지 능력을 검증한다. 단변량 EWMA로는 개별 변수의 미세한 이동을 놓칠 수 있지만, MEWMA는 여러 변수의 동시 이동을 결합하여 탐지한다.

---

## 다른 알고리즘과의 비교

### EWMA(단변량) vs MEWMA(다변량)

| 특성 | EWMA (단변량) | MEWMA (다변량) |
|------|---------------|----------------|
| 입력 데이터 | 1차원 시계열 | $p$차원 시계열 |
| 상관관계 고려 | 불가 | **공분산 행렬로 반영** |
| 통계량 | $Z_t$ (스칼라) | $\mathbf{Z}_t$ (벡터) → $D^2_t$ |
| 임계값 | UCL/LCL (대칭) | $\chi^2$ UCL (단측) |
| 해석 | 방향 해석 가능 (상승/하락) | 방향 해석 어려움 (거리만 제공) |
| 변수 수 증가 시 | 변수별 개별 차트 필요 | 단일 $D^2$ 차트로 통합 |
| 계산 비용 | $O(n)$ | $O(np^2)$ (역행렬 계산) |
| 적합 상황 | 개별 지표 모니터링 | **다변량 프로세스 종합 모니터링** |

### 언제 MEWMA를 선택하나?

- **여러 변수의 동시 변화를 하나의 지표로 보고 싶다** → MEWMA
- **변수 간 상관관계가 중요하다** → MEWMA (Hotelling T²도 가능)
- **단일 변수만 모니터링한다** → EWMA
- **점진적 다변량 변화를 잡고 싶다** → MEWMA (Hotelling보다 우수)
- **급격한 다변량 변화를 잡고 싶다** → Hotelling T²

---

## 탐지 로직

`detect()` 메서드의 동작 순서:

1. **구간 분리**: 데이터의 앞쪽 `reference_ratio` 비율을 기준 구간으로 설정한다. 최소 10개 데이터가 필요하다.
2. **기준 통계량 계산**: 기준 구간의 평균(`ref_mean`)과 분산(`ref_var`, ddof=0)을 계산한다. 다변량의 경우 평균 벡터와 공분산 행렬을 계산한다.
3. **EWMA 평활화**: 전체 시계열에 대해 EWMA를 계산한다 ($z_0 = x_0$).
4. **D² 통계량 계산**: 평활화된 값과 기준 평균 사이의 마할라노비스 거리를 계산한다.
5. **임계값 결정**: `scipy.stats.chi2.ppf(1 - alpha, df=p)`로 카이제곱 임계값을 구한다.
6. **알람 판정**: 기준 구간 이후의 시점에서 $D^2 > \text{UCL}$이면 alarm으로 표시한다.
7. **연속 알람 그룹화**: 인접한 알람 인덱스를 gap=5 기준으로 그룹화한다.
8. **이벤트 생성**: 각 그룹에서 $D^2$가 가장 큰 시점을 peak로 선택하고, score = $D^2$/UCL을 계산한다.
9. **심각도 판정**: score >= 2.0이면 critical, >= 1.0이면 warning, 그 외 normal.

---

## 차트 시각화

- **기본 차트**: Value 시계열 + drift 알람 마커
- **전문가 차트**:
  - Y축(좌): 원본 Value
  - Y2축(우): D² 통계량
    - `D²` (파란색 선): 마할라노비스 거리 추이
    - `UCL` (빨간색 수평선): 카이제곱 임계값 ($\chi^2_{1-\alpha}(p)$)

---

## 참고 문헌

- Lowry, C. A., Woodall, W. H., Champ, C. W., & Rigdon, S. E. (1992). "A Multivariate Exponentially Weighted Moving Average Control Chart." *Technometrics*, 34(1), 46-53.
- Roberts, S. W. (1959). "Control Chart Tests Based on Geometric Moving Averages." *Technometrics*, 1(3), 239-250.
- Montgomery, D. C. (2019). *Introduction to Statistical Quality Control*, 8th Edition. Wiley.
- Prabhu, S. S., & Runger, G. C. (1997). "Designing a Multivariate EWMA Control Chart." *Journal of Quality Technology*, 29(1), 8-15.
