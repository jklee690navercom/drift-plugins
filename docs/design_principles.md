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
