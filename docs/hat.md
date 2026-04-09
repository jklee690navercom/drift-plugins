# HAT (Hoeffding Adaptive Tree / ADWIN-like)

## 개요

Hoeffding bound를 이용하여 두 슬라이딩 윈도우(W0, W1)의 평균 차이가 통계적으로 유의한지를 판단하는 ADWIN 유사 drift 탐지 알고리즘이다. **분포 가정 없이 이론적 보장**을 제공하며, 온라인 학습 환경에서 실시간으로 concept drift를 감지하고 적응형 재학습을 트리거하는 데 적합하다.

---

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

### Hoeffding Adaptive Tree와의 관계

Hoeffding Adaptive Tree(HAT)는 Bifet & Gavalda(2009)가 제안한 적응형 결정 트리로, ADWIN drift 탐지기를 내장하여 concept drift에 자동 대응한다:

1. **Hoeffding Tree**: 데이터 스트림에서 점진적으로 학습하는 결정 트리. Hoeffding bound로 노드 분할 결정.
2. **ADWIN 탐지기**: 각 노드에 부착되어 해당 서브트리의 정확도 변화를 모니터링.
3. **적응형 재학습**: ADWIN이 drift를 감지하면 해당 서브트리를 대체 트리로 교체.

```
[Root Node]
   ├── [Node A] ← ADWIN 모니터 (정확도 추적)
   │      ├── [Leaf 1]
   │      └── [Leaf 2]
   └── [Node B] ← ADWIN 모니터
          ├── [Leaf 3]  ← drift 감지! → 대체 트리로 교체
          └── [Leaf 4]
```

### 온라인 학습과 적응형 재학습

HAT의 온라인 학습 사이클:

1. **관측**: 새 데이터 포인트 도착
2. **예측**: 현재 모델로 예측
3. **평가**: 실제 값과 비교하여 에러 계산
4. **drift 검사**: ADWIN으로 에러율 변화 모니터링
5. **갱신/재학습**: drift 감지 시 서브트리 교체, 미감지 시 점진적 갱신

---

## 파라미터

| 파라미터 | 기본값 | 설명 | 효과 |
|---|---|---|---|
| `min_window` | 30 | 각 윈도우(W0, W1)의 최소 크기 | 크면 안정적, 작으면 빠른 반응 |
| `delta` | 0.01 | Hoeffding bound의 오류 확률 | 작을수록 보수적. 0.001: 매우 보수적, 0.05: 민감 |
| `reference_ratio` | 0.5 | 기준 구간 비율 | 슬라이딩 시작 위치 결정 |

---

## 데이터 시나리오

### 3단계 환경 변화

| 구간 | 시점 | 패턴 | HAT 반응 |
|------|------|------|----------|
| 안정 환경 | 0~199 | 에러율 ~ 5% ($\mu=0.05$) | $\|\Delta\bar{x}\| < \epsilon$, 정상 |
| 환경 변화 1 | 200~349 | 에러율 ~ 15% (갑작스런 증가) | $\|\Delta\bar{x}\| > \epsilon$, alarm → 재학습 트리거 |
| 환경 변화 2 | 350~499 | 에러율 ~ 25% (추가 악화) | 재학습 후에도 $\|\Delta\bar{x}\| > \epsilon$ → 추가 적응 필요 |

이 시나리오는 HAT의 **적응형 재학습** 능력을 검증한다. 환경이 바뀔 때마다 ADWIN이 drift를 감지하고, 모델이 새 환경에 적응하는 과정을 보여준다.

---

## 다른 알고리즘과의 비교

| 특성 | HAT (ADWIN) | CUSUM | EWMA | KS Test |
|------|------------|-------|------|---------|
| 분포 가정 | **없음** (분포 무관) | 정규 가정 | 정규 가정 | 비모수 |
| 이론적 보장 | **Hoeffding bound** | 순차 검정 이론 | 근사적 | 점근적 |
| 온라인 학습 연동 | **네이티브** | 별도 구현 필요 | 별도 구현 필요 | 배치 위주 |
| 점진적 변화 | 보통 | **강함** | 강함 | 보통 |
| 급격한 변화 | **강함** | 강함 | 보통 | 강함 |
| 보수성 | **매우 보수적** | 조절 가능 | 조절 가능 | 조절 가능 |
| 이상치 민감도 | **높음** (R에 영향) | 중간 | 낮음 | 중간 |

### 언제 HAT를 선택하나?

- **온라인/스트리밍 환경에서 실시간 drift 감지가 필요하다** → HAT
- **분포 가정 없이 이론적 보장이 필요하다** → HAT
- **모델 재학습을 자동으로 트리거하고 싶다** → HAT
- **노이즈가 많고 평활화가 필요하다** → EWMA
- **미세한 변화를 빠르게 잡고 싶다** → CUSUM

---

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

---

## 차트 시각화

- **기본 차트**: Value 시계열 + drift 알람 마커
- **전문가 차트**:
  - Y축(좌): 원본 Value
  - Y2축(우): Error Rate (score)
    - `Error Rate` (빨간색 선): score 추이 ($|\text{mean\_diff}| / \epsilon$)
    - `Threshold` (주황색 수평선): 1.0 (score = 1.0 이상이면 drift)

---

## 참고 문헌

- Hoeffding, W. (1963). "Probability Inequalities for Sums of Bounded Random Variables." *Journal of the American Statistical Association*, 58(301), 13-30.
- Bifet, A., & Gavalda, R. (2007). "Learning from Time-Changing Data with Adaptive Windowing." *SIAM International Conference on Data Mining*.
- Bifet, A., & Gavalda, R. (2009). "Adaptive Learning from Evolving Data Streams." *IDA*.
- Domingos, P., & Hulten, G. (2000). "Mining High-Speed Data Streams." *KDD*.
