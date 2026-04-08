# Drift Plugin Developer Tool 설계 원칙

> 이 문서는 전체 시스템 설계 원칙 중 Plugin Developer Tool과 플러그인 개발에 해당하는 부분을 발췌한 것이다.

## 1. 플러그인 패키지 구조

1. 알고리즘과 UI는 하나의 완결된 패키지(플러그인)로 만들어 함께 배포한다.
2. 모든 플러그인은 하나의 GitHub Monorepo(drift-plugins/plugins)에서 관리하며, 각 플러그인은 plugins/{key}/ 디렉토리로 구분한다.
3. 플러그인별 독립 버전은 접두어 태그(cusum/v1.0.0, hotelling/v2.1.0)로 관리하며, pip의 subdirectory 지정으로 개별 설치한다.
4. 플러그인 간 충돌은 프레임워크가 방지한다: key 중복 검사(URL/템플릿/static 충돌 방지), 패키지 네이밍 규칙(drift_{key}).

## 2. Plugin Developer Tool

5. 플러그인 개발을 지원하는 PyQt6 기반 데스크톱 도구(Plugin Developer Tool)를 제공하며, 프로젝트 생성 마법사(빈칸 채우기 템플릿), 코드 편집, 구조 검증, 로컬 테스트, 미리보기, Registry를 통한 등록·버전 관리를 원스톱으로 수행한다.
6. 플러그인의 등록·수정·삭제는 Registry Server를 통해서만 이루어지며, 개발자가 GitHub 저장소를 직접 조작하지 않는다.
7. 원격 저장소에서 플러그인 소스를 가져와 로컬에서 개발하고 Registry Server를 통해 등록·배포한다.

## 3. 플러그인이 구현해야 하는 것

8. 플러그인의 detect()는 순수하게 "숫자 시계열에서 이상을 찾는 알고리즘"만 구현하며, 데이터가 무엇을 의미하는지(confidence score인지, 온도인지)는 알지 못한다.
9. 각 플러그인은 Flask Blueprint로 등록되어 자신의 라우트, API 엔드포인트를 독립적으로 소유한다.
10. 플러그인은 프레임워크의 base.html을 상속하여 네비게이션 일관성만 유지하고, block content 안에서는 완전히 자유롭다.
11. 플러그인은 대시보드용 카드 템플릿(card.html)과 상세 페이지 템플릿(page.html)을 제공한다.
12. 알고리즘 고유 파라미터(k, h, alpha 등)는 플러그인이 DEFAULT_PARAMS로 정의하고, 사용자가 config 또는 UI에서 값을 변경할 수 있다.

## 4. 플러그인 유형

13. 수치 drift 플러그인은 NumericStore에서 DriftDataset을 받아 통계적 탐지를 수행한다 (CUSUM, Hotelling, KS, Wasserstein, MEWMA 등).
14. LLM drift 플러그인은 DocumentStore와 NumericStore를 모두 사용하며, 추가로 프레임워크가 제공하는 LLM 서비스를 주입받는다.
15. LLM drift는 6가지 유형(지식, 언어, 분포, 추론, 관점, 운영) 단위로 플러그인을 구성하며, 각 플러그인이 해당 유형의 세부 지표들을 포함한다.

## 5. 프로젝트 분리

16. 전체 시스템은 세 개의 독립 프로젝트로 분리하여 개발·배포한다: drift-framework, drift-registry, drift-plugin-dev-tool.
17. 세 프로젝트 간에는 코드 import 의존이 없으며, 모든 통신은 HTTP API로만 이루어진다.
18. 각 프로젝트는 독립된 Git 저장소, pyproject.toml, 가상환경을 가지며, 릴리스 주기가 서로 독립적이다.

---

## 6. Plugin 구조 — 표시와 분석의 분리

플러그인은 명확히 구분되는 두 가지 책임을 진다. 이 둘은 서로 독립적으로 동작해야 하며, 한쪽이 막히더라도 다른 쪽이 영향을 받아서는 안 된다.

| 책임 | 트리거 | 입력 | 출력 |
|---|---|---|---|
| **표시 (display)** | 차트가 데이터를 요청할 때 | (없음 — cache에서 읽음) | raw 시계열 + drift event + (있으면) layer 컬럼 |
| **분석 (analyze)** | scheduler가 새 데이터를 넘길 때 | 새로 들어온 raw 슬라이스 | 새로 발견된 drift event 목록 |

### 6.1 두 책임은 서로 다른 함수로 구현한다

19. 플러그인은 `analyze(new_data, ...)`와 `get_chart_payload()` 두 메서드로 책임을 분리한다. 단일 `detect()`에서 두 책임을 모두 처리하지 않는다.
20. `analyze()`는 새 데이터를 받아 cache에 누적하고, 누적분이 분석 가능한 크기에 도달했을 때만 알고리즘을 실행한다.
21. `get_chart_payload()`는 cache에 있는 raw 데이터와 drift event, layer 컬럼을 차트가 요구하는 형태로 묶어 반환한다. 알고리즘을 실행하지 않는다.
22. 표시와 분석을 분리했기 때문에, framework가 어떤 크기로 데이터를 던지든(1 row씩이든 1000 row씩이든) 차트는 첫 데이터부터 즉시 그려진다. 분석 가능 크기에 도달하지 못한 경우에도 표시는 정상 동작한다.

### 6.2 cache 책임 — raw와 layer를 분리 보관한다

23. PluginCache는 두 종류의 데이터를 별도로 보관한다.
    - **raw data**: 입력 시계열 (timestamp + value 등). `analyze()`가 항상 누적하며, 한 번 들어온 row는 불변이다.
    - **layer data**: 알고리즘이 계산한 부가 컬럼 (T² 점수, EWMA 값, control limit 등). timestamp를 키로 갖는다.
24. raw 데이터가 불변인 이유: 재분석(reanalyzer)이 알고리즘만 다시 돌려도 되도록 하기 위함이다. 재분석 시 cache는 layer만 폐기하고 raw는 보존한다.
25. raw row에 layer 컬럼을 직접 섞지 않는다. 그래야 cache 코드가 plugin마다 달라지는 layer 스키마를 알지 않아도 되며, 동시성과 clear_after 처리가 단순해진다.
26. `get_chart_payload()`는 표시 시점에 raw와 layer를 timestamp 기준으로 합쳐서 반환한다.

### 6.3 analyze()의 표준 구현 패턴

27. analyze()는 다음 패턴을 따른다.

    ```python
    def analyze(self, new_data, ...):
        # ── 1단계: 표시 (항상 실행) ──
        self.cache.append_data(new_data)

        # ── 2단계: 분석 (조건부) ──
        if self.cache.size < self.MIN_REQUIRED:
            return []  # 표시는 이미 1단계에서 끝남

        events, layer_rows = self._run_algorithm(self.cache.data)
        self.cache.set_layers(layer_rows)
        self.cache.append_events(events)
        return events
    ```

28. 1단계는 framework가 던진 새 슬라이스를 무조건 cache에 누적한다. 누적은 부작용이 없으며, 차트가 즉시 보이기 위한 필수 조건이다.
29. 2단계는 cache 누적분이 알고리즘이 요구하는 최소 크기에 도달했을 때만 실행한다. 도달하지 못하면 빈 리스트를 반환하고 종료한다.
30. 알고리즘은 `new_data`가 아니라 `self.cache.data`(누적분)를 입력으로 사용한다. windowed 알고리즘은 최근 window 크기만 슬라이싱한다.

### 6.4 plugin은 stateless를 유지한다

31. plugin instance는 `self._buffer`, `self._last_event` 같은 상태를 직접 보유하지 않는다. 모든 상태는 cache에 보관한다.
32. plugin instance가 stateless여야 같은 plugin이 여러 binding에 묶일 때 instance를 공유해도 안전하다. (단, cache 자체는 binding 단위로 분리되어야 한다 — framework 측 책임.)
33. 알고리즘 파라미터(k, h, alpha 등)는 `self._params`에 보관하지만, 이는 stateless의 예외가 아니다. params는 binding 시점에 framework가 주입하며, 한 번 주입되면 분석 결과에 종속되지 않는다.

### 6.5 framework와의 계약

34. framework는 매 cycle마다 "지난번 호출 이후 새로 도착한 raw 슬라이스"를 plugin에 넘긴다. 이미 본 데이터는 다시 넘기지 않는다.
35. framework는 plugin의 cache를 직접 수정하지 않는다. cache는 plugin이 단독으로 쓰기 권한을 가진다. framework는 chart 요청 시 `get_chart_payload()`만 호출한다.
36. framework는 재분석 요청 시 `cache.clear_after(dt)`를 호출하여 layer와 drift event를 폐기한다. raw는 보존된다. plugin은 다음 `analyze()` 호출에서 raw 누적분으로 알고리즘을 다시 실행한다.
37. framework가 어떤 크기로 데이터를 던지든 plugin은 정상 동작해야 한다. plugin은 입력 슬라이스 크기에 의존하는 가드를 두지 않는다 (대신 cache 누적분 크기로 판단한다).

#### Framework가 plugin에 데이터를 주는 방식

plugin 입장에서 framework가 어떻게 데이터를 만들어 주는지 알아야, "왜 raw가 아니라 subgroup이 오는가", "왜 같은 timestamp가 두 번 오지 않는가"를 이해할 수 있다.

37a. framework는 raw 데이터를 그대로 던지지 않는다. 항상 plugin이 선언한 `subgroup_size`로 평균 집계한 row만 전달한다. plugin은 원본 데이터의 빈도·도착 패턴을 알지 못하며 알 필요도 없다.
37b. framework는 **닫힌(완성된) subgroup만** plugin에 emit한다. "닫힘"의 판정은 watermark 기반이다 — `bucket_end ≤ max(observed_timestamp) - lateness_tolerance` 일 때 그 subgroup은 더 이상 변하지 않는다고 간주한다.
37c. 같은 timestamp의 subgroup은 plugin에 두 번 전달되지 않는다. plugin은 받은 subgroup을 항상 처음 보는 데이터로 가정해도 된다.
37d. plugin은 데이터 도착 패턴(burst / gap / late arrival)을 알지 못한다. framework가 intake 단과 subgroup 계산 단을 분리해 이 불확실성을 모두 흡수한다. plugin은 받은 subgroup을 받은 순서대로 cache에 누적하면 된다.
37e. 이미 닫힌 bucket에 row가 늦게 도착해 drop되는 경우, 그 처리는 framework 책임이며 plugin에는 노출되지 않는다. plugin은 "받은 데이터가 곧 사실"이라고 믿어도 된다.

> framework 측 상세 원칙은 `drift_framework/docs/design_principles.md` 20장 "데이터 파이프라인 — Intake와 Subgroup 분리" (원칙 124~136) 참조.

### 6.6 동시성 — UI 읽기와 분석 쓰기의 분리

plugin 입장에서 두 가지 호출이 모두 주기적이며 서로 다른 스레드에서 들어온다.

| 호출자 | 스레드 | cache 접근 |
|---|---|---|
| `analyze()` | scheduler 단일 스레드 | 쓰기 (raw / layer / event) |
| `get_chart_payload()` | Flask 워커 스레드들 (다중) | 읽기 |

두 호출이 겹치면 reader가 일관되지 않은 중간 상태를 볼 수 있고, 알고리즘이 락을 길게 쥐면 UI polling이 멈춘다. 다음 원칙으로 두 위험을 모두 막는다.

38. cache의 모든 mutation은 짧은 임계구역 안에서만 일어난다. 알고리즘의 CPU 작업은 락 밖에서 실행한다.
39. `analyze()`는 다음 3단계로 구성된다.
    1. **누적 + 스냅샷** (락 안, 짧음): 새 raw를 cache에 append하고 분석에 쓸 데이터의 스냅샷을 꺼낸다.
    2. **계산** (락 밖, 길 수 있음): 스냅샷으로 알고리즘을 실행하여 (events, layer rows)를 만든다.
    3. **커밋** (락 안, 짧음): layer와 event를 cache에 원자적으로 반영한다.
40. `get_chart_payload()`는 raw / layer / drift event를 한 번의 락 획득 안에서 동시에 스냅샷한다. 세 컬렉션이 서로 다른 시점의 상태를 가리키지 않도록 한다.
41. 차트의 꼬리에서 raw row만 있고 layer / event가 아직 따라오지 않는 일시 상태는 정상이다. 다음 `analyze()` cycle에서 layer가 추가되며, plugin은 이 지연을 숨기려 하지 않는다.
42. 같은 binding에 대한 `analyze()` 호출은 동시에 진행되지 않는다. 정기 분석과 재분석은 plugin 상태(`running` / `reanalyzing`)로 framework가 직렬화한다. plugin은 이 직렬화를 신뢰하고, `analyze()` 내부에 자체 동기화를 두지 않는다.
43. cache의 락은 재진입 가능(`RLock`)으로 둔다. plugin이 cache 메서드 안에서 다른 cache 메서드를 호출해도 데드락이 발생하지 않게 한다.
44. 알고리즘 단계(원칙 39의 2단계)에서는 cache를 직접 읽지 않는다. 1단계에서 받은 스냅샷만 사용한다. 그래야 계산 도중 cache가 다른 스레드에 의해 변해도 결과가 흔들리지 않는다.
