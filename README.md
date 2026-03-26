# Drift Plugins Monorepo

Drift Framework용 플러그인 모음. 각 플러그인은 `plugins/{key}/` 디렉토리에 위치한다.

## 플러그인 목록

| Key | 이름 | 알고리즘 |
|---|---|---|
| cusum | CUSUM | 누적합 기반 변화점 탐지 |
| ks-test | KS Test | Kolmogorov-Smirnov 분포 검정 |
| hotelling | Hotelling T² | 다변량 T² 통계량 |
| wasserstein | Wasserstein | Wasserstein 거리 기반 |
| mewma | MEWMA | 다변량 지수가중이동평균 |
| c-chart | C-Chart | 결점수 관리도 |
| p-chart | P-Chart | 불량률 관리도 |
| xbar-r-chart | X̄-R Chart | 평균-범위 관리도 |
| imr-chart | IMR Chart | 개별값-이동범위 관리도 |
| hat | HAT | Histogram Adaptive Threshold |
| shap | SHAP | Feature Importance 기반 |
| ocdd | OCDD | Online Class Distribution Drift |

## 설치

```bash
pip install "git+https://github.com/jklee690navercom/drift-plugins.git#subdirectory=plugins/cusum"
```

## 플러그인 구조

모든 플러그인은 `DriftPlugin`을 상속하며, `detect()`와 `get_chart_config()`만 구현한다.
BaseChart, 표준 API, 캐시 관리, 폴링은 Framework가 자동 제공한다.
