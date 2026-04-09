# Cache Persistence — SQLite 기반 Plugin Cache 영속화 설계

> PluginCache는 메모리 객체이다. 서버가 비정상 종료되면 cache가 사라지고,
> DataSource에서 raw를 다시 받아 처음부터 분석을 재실행해야 한다.
> 이 문서는 SQLite를 사용하여 cache를 영속화하는 설계를 정의한다.
>
> 참조: `plugin_architecture.md` 4A장(Cache 생명주기)

---

## 1. 문제

| 상황 | 현재 동작 | 영향 |
|---|---|---|
| 서버 정상 재시작 | cache + InMemoryStore 모두 소멸 | 모든 이력 손실, DataSource에서 재수집 필요 |
| 서버 비정상 종료 (crash) | 동일 | 동일 |
| 수시간 축적 후 crash | 동일 | 재수집에 수분~수십분 소요 |

**영속화 목표**: 서버 재시작 후 **즉시 차트 표시 + 이어서 분석** 가능.

---

## 2. 저장 대상 판단

| 컬렉션 | 저장 여부 | 이유 |
|---|---|---|
| **raw** (`cache.data`) | **저장** | DataSource에서 다시 받을 수 있지만, 재수집 비용 회피. 부팅 직후 차트 즉시 표시 |
| **layer** (`cache.layer_data`) | **저장 안 함** | `analyze()` 재실행으로 재계산. 저장하면 스키마 변경 시 마이그레이션 필요 |
| **drift_events** | **저장** | 과거 drift 이력은 알고리즘 재실행 없이는 복원 불가. dedup에도 필요 |
| **calculated_until** | **저장** | 어디까지 분석했는지 알아야 이어서 진행 |
| **cache_from** | **저장 안 함** | raw 첫 row의 timestamp에서 재계산 |

---

## 3. 크기 추정

| 항목 | 1년 기준 (5분 간격) | row 크기 | plugin당 | 13개 합계 |
|---|---|---|---|---|
| raw | ~105,000 rows | ~80 bytes | ~8 MB | ~104 MB |
| drift_events | 수십~수백 개 | ~500 bytes | < 1 MB | < 13 MB |
| plugin_state | 1 row | ~50 bytes | 무시 | 무시 |
| **합계** | | | **~10 MB** | **~120 MB** |

SQLite 단일 파일로 충분한 크기이다.

---

## 4. SQLite 선택 근거

| 기준 | SQLite | JSON 파일 | Redis | PostgreSQL |
|---|---|---|---|---|
| crash 안전성 | WAL 모드로 보장 | 부분 쓰기 시 파손 위험 | 보장 | 보장 |
| 설치 | Python 내장 (`sqlite3`) | 없음 | 별도 서버 | 별도 서버 |
| 동시 읽기/쓰기 | WAL 모드 OK | 직접 락 필요 | OK | OK |
| 운영 부담 | 파일 1개, 백업 = 복사 | 파일 1개 | 프로세스 관리 | 프로세스 관리 |
| 성능 (매 cycle 수십 rows) | ms 단위 | ms 단위 | ms 단위 | ms 단위 |

**결론**: Python 내장, 설치 없음, crash 안전, 파일 1개 — SQLite가 최적.

---

## 5. 스키마

```sql
-- SQLite 설정
PRAGMA journal_mode = WAL;          -- 동시 읽기/쓰기 허용
PRAGMA synchronous = NORMAL;        -- WAL 모드에서 안전하면서 빠른 설정
PRAGMA foreign_keys = ON;

-- plugin 상태 (plugin_key당 1 row)
CREATE TABLE IF NOT EXISTS plugin_state (
    plugin_key        TEXT PRIMARY KEY,
    calculated_until  TEXT,              -- ISO 8601 datetime
    updated_at        TEXT NOT NULL      -- 마지막 저장 시각
);

-- raw data (append-only, 불변)
CREATE TABLE IF NOT EXISTS raw_data (
    plugin_key  TEXT    NOT NULL,
    timestamp   TEXT    NOT NULL,
    data        TEXT    NOT NULL,         -- JSON: {"value": 3.14, "count": 1, ...}
    PRIMARY KEY (plugin_key, timestamp)
);

-- drift events (plugin_key 단위로 교체)
CREATE TABLE IF NOT EXISTS drift_events (
    plugin_key   TEXT    NOT NULL,
    detected_at  TEXT    NOT NULL,
    event_data   TEXT    NOT NULL,        -- JSON: DriftEvent.to_dict() 전체
    PRIMARY KEY (plugin_key, detected_at)
);

-- 인덱스: 복원 시 plugin_key로 조회
CREATE INDEX IF NOT EXISTS idx_raw_plugin ON raw_data(plugin_key);
CREATE INDEX IF NOT EXISTS idx_events_plugin ON drift_events(plugin_key);
```

**설계 결정**:

| 결정 | 이유 |
|---|---|
| `data` 컬럼은 JSON 문자열 | plugin마다 raw 컬럼이 다름 (value, feature_0, feature_1, ...). JSON이면 스키마 변경 불필요 |
| `plugin_key + timestamp`가 PK | 중복 INSERT 자연 방지 (`INSERT OR IGNORE`) |
| layer_data 테이블 없음 | 재계산 가능 — 저장하면 스키마 결합도 증가 |
| 단일 DB 파일 | 13개 plugin이 하나의 `drift_cache.db`를 공유. 백업/이동이 단순 |

---

## 6. 쓰기 — analyze() cycle 후

### 6.1 쓰기 시점

`commit_analysis()` 호출 직후, cache 메모리 갱신과 함께 DB에 저장한다.

```
scheduler._run_analysis()
  └─ plugin.analyze(new_data)
       ├─ 1단계: cache.append_and_snapshot()
       ├─ 2단계: _run_algorithm()
       └─ 3단계: cache.commit_analysis()
  └─ persistence.save_cycle(plugin_key, new_raw, events, calculated_until)
```

### 6.2 save_cycle 동작

```python
def save_cycle(self, plugin_key: str, new_raw: list[dict],
               events: list[dict], calculated_until: datetime):
    """한 cycle의 결과를 DB에 저장한다. 단일 트랜잭션."""
    with self._connect() as conn:
        # 1. raw 추가 (새 rows만, 기존은 IGNORE)
        conn.executemany(
            "INSERT OR IGNORE INTO raw_data (plugin_key, timestamp, data) "
            "VALUES (?, ?, ?)",
            [(plugin_key, row["timestamp"].isoformat(),
              json.dumps(row, default=str))
             for row in new_raw],
        )

        # 2. events 교체 (replace_events=True 패턴)
        conn.execute(
            "DELETE FROM drift_events WHERE plugin_key = ?",
            (plugin_key,),
        )
        conn.executemany(
            "INSERT INTO drift_events (plugin_key, detected_at, event_data) "
            "VALUES (?, ?, ?)",
            [(plugin_key, ev["detected_at"], json.dumps(ev, default=str))
             for ev in events],
        )

        # 3. plugin 상태 갱신
        conn.execute(
            "INSERT OR REPLACE INTO plugin_state "
            "(plugin_key, calculated_until, updated_at) VALUES (?, ?, ?)",
            (plugin_key, calculated_until.isoformat(),
             datetime.now().isoformat()),
        )
```

**트랜잭션 보장**: `with conn` 블록 안에서 raw + events + state가 **원자적**으로 저장된다. crash 시 중간 상태는 발생하지 않는다.

### 6.3 쓰기 성능

| 항목 | cycle당 크기 | SQLite WAL 성능 |
|---|---|---|
| raw INSERT | 1~20 rows (subgroup 크기 의존) | < 1 ms |
| events DELETE + INSERT | 수십~수백 rows | < 5 ms |
| state UPDATE | 1 row | < 1 ms |
| **합계** | | **< 10 ms** |

scheduler cycle이 보통 2~10초이므로, 10 ms 미만의 DB 쓰기는 부담이 되지 않는다.

---

## 7. 읽기 — 서버 부팅 시 복원

### 7.1 복원 흐름

```
서버 부팅
  └─ loader._setup_drift_plugin(app, info)
       ├─ cache = PluginCache()
       ├─ plugin.cache = cache
       │
       ├─ persistence.load(plugin_key)
       │    ├─ SELECT * FROM raw_data WHERE plugin_key = ? ORDER BY timestamp
       │    ├─ SELECT * FROM drift_events WHERE plugin_key = ?
       │    └─ SELECT calculated_until FROM plugin_state WHERE plugin_key = ?
       │
       └─ if data exists:
            cache.load_history(rows, events, calculated_until)
            plugin.set_calculated_until(calculated_until)
```

### 7.2 load 동작

```python
def load(self, plugin_key: str) -> tuple[list[dict], list[dict], datetime | None]:
    """DB에서 plugin의 영속화 데이터를 복원한다.

    Returns:
        (raw_rows, drift_events, calculated_until)
    """
    with self._connect() as conn:
        # raw
        rows = conn.execute(
            "SELECT data FROM raw_data "
            "WHERE plugin_key = ? ORDER BY timestamp",
            (plugin_key,),
        ).fetchall()
        raw = [json.loads(r[0]) for r in rows]

        # events
        evts = conn.execute(
            "SELECT event_data FROM drift_events WHERE plugin_key = ?",
            (plugin_key,),
        ).fetchall()
        events = [json.loads(e[0]) for e in evts]

        # state
        state = conn.execute(
            "SELECT calculated_until FROM plugin_state WHERE plugin_key = ?",
            (plugin_key,),
        ).fetchone()
        cu = (
            datetime.fromisoformat(state[0])
            if state and state[0] else None
        )

    return raw, events, cu
```

### 7.3 복원 후 상태

| 컬렉션 | 복원 직후 | 첫 analyze() cycle 후 |
|---|---|---|
| raw | DB에서 복원 완료 | 새 subgroup 추가 |
| layer | **비어있음** | 전체 재계산으로 채워짐 |
| drift_events | DB에서 복원 완료 | replace_events로 교체 |
| calculated_until | DB에서 복원 완료 | 전진 |

**차트 표시**: 복원 직후 raw가 있으므로 즉시 표시 가능. layer는 없지만 raw만으로도 value 차트는 그려진다. 첫 `analyze()` cycle에서 layer가 채워지면 완전한 차트가 된다.

---

## 8. 재분석 시 DB 처리

```
reanalyzer.request_reanalysis(key, dt)
  ├─ cache.clear_after(dt)          # 메모리에서 폐기
  └─ persistence.clear_after(key, dt)  # DB에서도 폐기
       ├─ DELETE FROM raw_data WHERE plugin_key = ? AND timestamp > ?
       ├─ DELETE FROM drift_events WHERE plugin_key = ?
       └─ UPDATE plugin_state SET calculated_until = ?
```

향후 `clear_layers_after` 경로로 전환되면 raw DELETE는 불필요해진다.

---

## 9. trim 연동

`cache.trim(max_days)`이 호출되면 DB에서도 오래된 raw를 삭제한다.

```python
def trim(self, plugin_key: str, max_days: int = 365):
    cutoff = (datetime.now() - timedelta(days=max_days)).isoformat()
    with self._connect() as conn:
        conn.execute(
            "DELETE FROM raw_data "
            "WHERE plugin_key = ? AND timestamp < ?",
            (plugin_key, cutoff),
        )
```

drift_events는 trim하지 않는다 — 과거 drift 이력은 보존.

---

## 10. 파일 위치와 설정

```
drift_framework/
  └─ data/
       └─ drift_cache.db       # SQLite 파일 (13개 plugin 공유)
```

설정 (drift_config.yaml 또는 환경변수):

```yaml
cache:
  persistence: true                    # 영속화 활성화 (기본: false)
  db_path: "data/drift_cache.db"       # SQLite 파일 경로
  max_history_days: 365                # trim 보존 기간
```

---

## 11. 구현 위치

| 파일 | 역할 |
|---|---|
| `framework/plugin/persistence.py` (신규) | `CachePersistence` 클래스 — DB 연결, save_cycle, load, clear_after, trim |
| `framework/plugin/loader.py` | `_setup_drift_plugin()`에서 persistence.load() 호출 |
| `framework/scheduler.py` | `_run_analysis()` 끝에서 persistence.save_cycle() 호출 |
| `framework/reanalyzer.py` | `request_reanalysis()`에서 persistence.clear_after() 호출 |
| `framework/plugin/cache.py` | 변경 없음 — cache는 메모리 동작 그대로 유지 |

**핵심**: cache 코드 자체는 변경하지 않는다. persistence는 cache의 **외부 관찰자**로서 scheduler/reanalyzer가 적절한 시점에 호출한다. cache와 persistence의 결합도를 낮게 유지한다.

---

## 12. 향후 확장

| 단계 | 내용 | 시점 |
|---|---|---|
| Phase 1 | 이 문서의 설계대로 SQLite 영속화 구현 | 1.D.4 변환 완료 후 |
| Phase 2 | InMemoryStore → SQLite Store 전환 (raw가 store와 cache에 이중 보관되는 문제 해소) | todo 3.4.1 |
| Phase 3 | 외부 DB (PostgreSQL) 옵션 — CachePersistence 인터페이스 유지, backend만 교체 | 대규모 배포 시 |
