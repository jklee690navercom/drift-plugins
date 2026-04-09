# KS Test (Kolmogorov-Smirnov Test)

## 개요

Kolmogorov-Smirnov(KS) 검정은 두 표본의 경험적 누적분포함수(ECDF)를 비교하여 분포 차이를 감지하는 **비모수적 검정**이다. 정규분포를 가정하지 않으므로 평균, 분산, 형태 등 **어떤 종류의 분포 변화도 감지**할 수 있다.

기준 구간(reference)과 슬라이딩 윈도우(test)를 반복 비교하여 분포가 변한 시점을 탐지한다.

---

## 알고리즘 원리

### 수학적 배경

**경험적 누적분포함수 (ECDF):**

표본 크기 $n$인 데이터 $X_1, X_2, \dots, X_n$에 대해:

$$F_n(x) = \frac{1}{n} \sum_{i=1}^{n} \mathbf{1}(X_i \le x)$$

여기서 $\mathbf{1}(\cdot)$은 지시함수이다.

**KS 통계량:**

$$D = \sup_x |F_{\text{ref}}(x) - F_{\text{test}}(x)|$$

두 ECDF 사이의 **최대 수직 거리**이다.

**가설 검정:**

- 귀무가설 ($H_0$): 두 표본은 동일한 분포에서 추출되었다.
- 대립가설 ($H_1$): 두 표본은 서로 다른 분포에서 추출되었다.

**p-value 계산 (점근적 분포):**

$$\lambda = \left(\sqrt{\frac{n_1 n_2}{n_1 + n_2}} + 0.12 + \frac{0.11}{\sqrt{\frac{n_1 n_2}{n_1 + n_2}}}\right) \cdot D$$

$$p = 2 \sum_{k=1}^{\infty} (-1)^{k-1} e^{-2\lambda^2 k^2}$$

p-value가 유의수준 $\alpha$ 미만이면 귀무가설을 기각하고 drift로 판단한다.

**Score 계산:**

$$\text{score} = \min\left(\frac{-\log_{10}(\max(p, 10^{-300}))}{10}, 5.0\right)$$

score가 높을수록 분포 차이가 심각하다.

### 핵심 아이디어

```
reference 구간        슬라이딩 윈도우
[■■■■■■■■■■]         [□□□□□]→→→→→
                          ↓
                     ks_2samp(reference, window)
                          ↓
                     D-statistic, p-value
                          ↓
                     p < alpha? → drift!
```

분포의 형태(평균, 분산, 왜도 등)가 어떻게 변하든, 두 분포 간의 차이가 있으면 감지할 수 있는 범용 검정이다.

---

## 파라미터

### 기본 파라미터

| 파라미터 | 기본값 | 설명 | 효과 |
|---|---|---|---|
| `window_size` | 100 | 테스트 슬라이딩 윈도우의 크기 | 크면 안정적이나 지연 증가 |
| `alpha` | 0.05 | 유의수준 | 작을수록 보수적 판단 |
| `reference_ratio` | 0.5 | 기준 구간 비율 | 기준 분포 추정에 사용 |

### 확장 파라미터

| 파라미터 | 기본값 | 설명 | 효과 |
|---|---|---|---|
| `correction` | `"bh"` | 다중 검정 보정 방법 | `"none"`, `"bonferroni"`, `"bh"` |
| `update_reference` | `true` | drift 후 기준 윈도우 갱신 | 연속 alarm 방지 |
| `remove_outliers` | `false` | IQR 기반 이상치 제거 | ECDF 왜곡 방지 |
| `method` | `"asymptotic"` | 검정 방법 | `"asymptotic"`, `"exact"`, `"bootstrap"` |

### 파라미터 상세 설명

#### correction — 다중 검정 보정

슬라이딩 윈도우로 수백 회 검정하면 동일 분포에서도 ~5%가 오탐된다.

| 방법 | 원리 | 특징 |
|------|------|------|
| `none` | 보정 없음. 원시 p-value 사용 | 빠른 탐색용. false positive 높음 |
| `bonferroni` | $\alpha_{\text{adj}} = \alpha / N_{\text{tests}}$ | 보수적. false negative 증가 |
| `bh` | Benjamini-Hochberg FDR 제어 | **권장**. 균형 잡힌 성능 |

**Benjamini-Hochberg 절차:**

1. $N$개의 p-value를 오름차순 정렬: $p_{(1)} \le p_{(2)} \le \dots \le p_{(N)}$
2. 임계값 계산: $\text{threshold}_i = \frac{i}{N} \cdot \alpha$
3. $p_{(i)} \le \text{threshold}_i$를 만족하는 최대 $i$를 찾음
4. $p_{(1)}, \dots, p_{(i)}$에 해당하는 검정을 유의하다고 판정

#### update_reference — 기준 윈도우 갱신

```
update_reference = false (기본 기준 고정):
  reference: [■■■■■■■■]  (데이터 앞부분 고정)
  drift 후에도 같은 reference로 비교
  → 한번 drift 시작되면 이후 모든 윈도우가 alarm

update_reference = true (drift 후 갱신):
  reference: [■■■■■■■■]  → drift 탐지!
  reference: [□□□□□□□□]  (현재 윈도우로 교체)
  → 새로운 정상 상태 기준으로 다음 drift 탐지
```

#### remove_outliers — 이상치 처리

IQR(사분위 범위) 기반으로 극단값을 제거한 후 KS 검정을 수행한다.

```python
Q1, Q3 = np.percentile(data, [25, 75])
IQR = Q3 - Q1
mask = (data >= Q1 - 1.5 * IQR) & (data <= Q3 + 1.5 * IQR)
clean_data = data[mask]
```

이상치가 ECDF를 왜곡하여 잘못된 탐지를 유발하는 문제를 방지한다.

#### method — 검정 방법

| 방법 | 원리 | 권장 상황 |
|------|------|----------|
| `asymptotic` | 점근적 분포 사용 (기본) | $n \ge 100$ |
| `exact` | 정확한 분포 계산 | $n < 50$ (작은 샘플) |
| `bootstrap` | 재표본 추출 (1000회) | 신뢰구간 추정 필요 시 |

---

## 데이터 시나리오

### ds_ks_distribution — 분포 변화 3단계

| 구간 | 시점 | 패턴 | KS Test 반응 |
|------|------|------|-------------|
| 정상 | 0~199 | $N(0, 1)$ 정규분포 | $D \approx 0$, p-value 높음 (정상) |
| 분산 증가 | 200~349 | $N(0, 4)$ 분산 4배 | $D$ 상승, p-value 급락 → drift |
| 평균 이동 | 350~449 | $N(2, 1)$ 평균 2 이동 | $D$ 대폭 상승, p-value $\approx 0$ → critical |
| 복귀 | 450~599 | $N(0, 1)$ 원래 분포 복귀 | `update_reference=false`: 여전히 alarm, `true`: 정상 복귀 |

이 시나리오는 KS Test의 **범용성**을 보여준다. 분산만 변하는 Phase 2에서도 탐지하며(CUSUM/EWMA는 불가), 평균 이동도 감지하고, 복귀 시 `update_reference` 옵션의 효과를 확인할 수 있다.

### 기존 테스트 DataSource 매핑

| DataSource | KS Test로 검증하는 것 |
|---|---|
| `ds_sudden_drift` | 기본 탐지 능력. 급격한 평균+분산 변화 감지 |
| `ds_gradual_drift` | 점진적 변화에서 윈도우 크기의 영향 |
| `ds_incremental_drift` | 기준 갱신(`update_reference`) 효과 |
| `ds_multiple_drift` | 다중 검정 보정(`correction`) 효과. 복귀 구간 오탐 방지 |
| `ds_variance_change` | 평균은 동일, 분산만 변할 때 KS의 장점 (CUSUM은 못 잡음) |
| `ds_outlier_heavy` | 이상치 전처리(`remove_outliers`) 효과 |
| `ds_seasonal` | 계절성과 drift 구분. 윈도우 크기 + 기준 구간 설정 |
| `ds_stable` | False positive 측정. 보정 방법별 비교 기준선 |

---

## 탐지 로직

`detect()` 메서드의 동작 순서:

### Phase 1: 전처리

1. **이상치 제거** (`remove_outliers=true`일 때): IQR 기반으로 극단값 제거.
2. **구간 분리**: 데이터의 앞쪽 `reference_ratio` 비율을 기준 구간(reference)으로 설정.
3. **유효성 검사**: 기준 구간과 테스트 구간 모두 `window_size` 이상의 데이터가 필요.
4. **샘플 크기 경고**: `window_size < 50`이면 검정력 부족 경고 로그.

### Phase 2: 슬라이딩 윈도우 KS 검정

5. **윈도우 순회**: 기준 구간 이후부터 `window_size` 크기의 윈도우를 한 칸씩 이동.
6. **KS 검정 실행**: `scipy.stats.ks_2samp(reference, window, method=method)`를 수행.
7. **결과 기록**: 각 윈도우의 중간 지점(mid)에 D-statistic과 p-value를 기록.

### Phase 3: 다중 검정 보정

8. **보정 적용** (`correction` 설정에 따라):
   - `bonferroni`: 유의수준을 검정 횟수로 나눔.
   - `bh`: Benjamini-Hochberg 절차로 보정된 p-value 산출.
9. **알람 판정**: 보정된 p-value < alpha이면 해당 시점을 alarm으로 표시.

### Phase 4: 기준 갱신 + 이벤트 생성

10. **기준 윈도우 갱신** (`update_reference=true`일 때): drift 탐지 후 reference를 현재 윈도우로 교체. 연속 alarm이 일정 횟수 이상이면 갱신 트리거.
11. **연속 알람 그룹화**: 인접한 알람 인덱스를 gap=5 기준으로 그룹화.
12. **드리프트 유형 판별**: p-value 패턴을 분석하여 유형 분류:
    - **sudden**: 특정 시점에서 p-value 급락
    - **gradual**: 전환 구간에서 p-value 서서히 하락
    - **incremental**: 지속적으로 낮은 p-value
13. **이벤트 생성**: 각 그룹에서 p-value가 가장 작은 시점을 peak로 선택하고 score를 계산.
14. **심각도 판정**: score >= 2.0이면 critical, >= 1.0이면 warning, 그 외 normal.

---

## 프리셋 (Analysis Mode)

UI에서 원클릭으로 적용할 수 있는 사전 정의된 설정 조합.

### Quick Scan

```yaml
window_size: 30
alpha: 0.05
correction: none
update_reference: false
remove_outliers: false
method: asymptotic
```

빠른 탐색용. 높은 false positive 허용. 데이터 전체를 빠르게 훑어보는 용도.

### Standard (기본값)

```yaml
window_size: 100
alpha: 0.05
correction: bh
update_reference: true
remove_outliers: true
method: asymptotic
```

일반적인 분석용. BH 보정 + 기준 갱신 + 이상치 제거로 균형 잡힌 성능.

### High Precision

```yaml
window_size: 200
alpha: 0.01
correction: bonferroni
update_reference: true
remove_outliers: true
method: exact
```

정밀 분석용. 보수적 판정. false positive 최소화. 확인적 분석에 사용.

### Streaming

```yaml
window_size: 100
alpha: 0.05
correction: bh
update_reference: true
remove_outliers: false
method: asymptotic
```

실시간 모니터링용. 기준 윈도우 자동 갱신으로 장기 운영에 적합.

### Small Sample

```yaml
window_size: 30
alpha: 0.10
correction: none
update_reference: false
remove_outliers: false
method: bootstrap
```

소량 데이터용 ($n < 50$). Bootstrap으로 검정력 보완. 유의수준 완화.

---

## 다변량 KS 테스트

단변량 KS를 여러 변수에 각각 적용하고 Bonferroni 보정으로 결합한다.

```python
def multivariate_ks(X_ref, X_test):
    """변수별 KS 테스트 후 Bonferroni 보정."""
    n_features = X_ref.shape[1]
    p_values = []

    for i in range(n_features):
        _, p = ks_2samp(X_ref[:, i], X_test[:, i])
        p_values.append(p)

    # Bonferroni 보정: 최소 p-value × 변수 수
    min_p = min(p_values) * n_features
    return min(min_p, 1.0), p_values
```

단, 변수 간 상관관계를 고려하지 않는 한계가 있다. 상관관계가 강한 다변량 데이터는 Hotelling $T^2$를 권장한다.

---

## 다른 플러그인과의 비교

| 특성 | KS Test | CUSUM | Hotelling $T^2$ | Wasserstein |
|------|---------|-------|-----------------|-------------|
| 감지 대상 | **모든 분포 변화** | 평균 변화 | 다변량 평균 변화 | 분포 거리 |
| 분포 가정 | 비모수 | 정규 가정 | 다변량 정규 | 비모수 |
| 분산 변화 감지 | **O** | X | 부분적 | **O** |
| 형태 변화 감지 | **O** | X | X | **O** |
| 점진적 변화 | 보통 | **강함** | 보통 | 보통 |
| 다변량 지원 | 변수별 개별 | X | **네이티브** | 1D만 |
| 출력 | D-stat, p-value | 누적합 | $T^2$ 통계량 | 거리 |

### 권장 사용 상황

```
"분포가 어떻게 바뀌든 감지하고 싶다"         → KS Test
"평균이 서서히 빠지는 것을 빨리 잡고 싶다"    → CUSUM
"여러 변수의 동시 변화를 보고 싶다"           → Hotelling
"변화의 크기를 수치적으로 비교하고 싶다"       → Wasserstein
```

---

## 차트 UI 설계

### 차트 구성 (4개 패널)

#### 1. Value Chart — 시계열 + 알람

```
원본 시계열(검정 선) + drift 알람 마커(빨간 점)
- X축: 시간
- Y축: 데이터 값
- 빨간 점: alarm 시점
- 빨간 배경 영역: drift 이벤트 구간
```

#### 2. D-statistic Chart — KS 통계량

```
각 윈도우 위치의 D-statistic (보라색 선)
- X축: 시간 (Value Chart와 동기화)
- Y축: D-statistic (0~1)
- 높을수록 분포 차이가 큼
```

#### 3. p-value Chart — 유의확률

```
-log10(p-value) (청록색 선) + alpha 임계선(빨간 점선)
- X축: 시간 (동기화)
- Y축: -log10(p-value)
- 빨간 수평 점선: -log10(alpha) 임계선
- 임계선 위 = drift
```

#### 4. ECDF Comparison Chart — 분포 비교

```
Reference ECDF(파란 계단선) vs Test ECDF(주황 계단선)
- X축: 데이터 값
- Y축: 누적 확률 (0~1)
- 빨간 수직 점선: D-statistic (최대 거리 지점)
- D 값과 p-value 텍스트 표시
```

---

## 실용적 가이드라인

### 파라미터 선택 가이드

**유의수준 (alpha):**

| 값 | 사용 상황 |
|------|----------|
| 0.01 | 보수적 판단 필요 시 (오탐 최소화) |
| 0.05 | 일반적 사용 (기본값) |
| 0.10 | 탐색적 분석 (미세한 변화도 잡고 싶을 때) |

**윈도우 크기:**

| 크기 | 탐지 속도 | False Positive | 권장 상황 |
|------|----------|----------------|----------|
| 30~50 | 빠름 | 높음 | 빠른 반응 필요 시 |
| 100~200 | 보통 | 보통 | **일반적 사용** |
| 500+ | 느림 | 낮음 | 안정성 중시 시 |

### 결과 해석 체크리스트

1. **p-value 확인**: $< \alpha$이면 유의함
2. **D-statistic 확인**: 효과 크기 파악 (0.1 미만이면 미세한 차이)
3. **샘플 크기 고려**: 작으면 검정력 부족
4. **다중 검정 고려**: 보정 방법 적용 여부 확인
5. **ECDF 시각화**: 두 분포의 패턴 차이를 눈으로 확인

---

## 적합한 상황

### 효과적인 경우

- 분포의 어떤 특성(평균, 분산, 형태 등)이 변하든 범용적으로 감지하고 싶을 때
- 데이터 분포에 대한 사전 가정 없이(비모수적으로) 검정하고 싶을 때
- 기준 구간이 명확하게 정의되어 있을 때
- 분포의 형태 자체가 변하는 경우 (예: 정규분포에서 이중봉 분포로)
- A/B 테스트 결과 비교

### 한계점

- 윈도우 크기가 작으면 검정력(power)이 낮아 미세한 변화를 놓칠 수 있다
- 기준 구간(reference)이 이미 drift 상태이면 잘못된 결과를 낸다 (`update_reference`로 완화)
- 매 윈도우마다 검정을 수행하므로 다중비교 문제가 발생할 수 있다 (`correction`으로 해결)
- 슬라이딩 윈도우 방식으로 인해 변화 시점 감지에 `window_size/2`만큼의 지연이 있다
- 매우 작은 샘플 ($n < 30$)에서는 검정력이 매우 낮다

---

## 참고 문헌

- Kolmogorov, A. N. (1933). "Sulla determinazione empirica di una legge di distribuzione." *Giornale dell'Istituto Italiano degli Attuari*, 4, 83-91.
- Smirnov, N. (1948). "Table for Estimating the Goodness of Fit of Empirical Distributions." *Annals of Mathematical Statistics*, 19(2), 279-281.
- Benjamini, Y., & Hochberg, Y. (1995). "Controlling the false discovery rate: a practical and powerful approach to multiple testing." *Journal of the Royal Statistical Society B*, 57(1), 289-300.
- Rabanser, S., Gunnemann, S., & Lipton, Z. C. (2019). "Failing Loudly: An Empirical Study of Methods for Detecting Dataset Shift." *NeurIPS*.
