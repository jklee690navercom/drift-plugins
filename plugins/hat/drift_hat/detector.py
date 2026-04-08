"""HAT drift detector — ADWIN 기반 적응형 윈도우 drift 탐지기 v3.0.

1.D 책임 분리(design_principles 21장)에 따라 새 analyze() 패턴을 사용한다:
- 표시(차트): framework가 plugin.get_chart_payload()로 cache 스냅샷을 직접 읽음
- 분석(drift): plugin.analyze()가 (1) raw 누적 + 스냅샷, (2) 알고리즘, (3) commit
"""

from datetime import timedelta
import math

import numpy as np

from framework.plugin.base import DriftPlugin
from framework.events.schema import DriftEvent


class HatDetector(DriftPlugin):
    """ADWIN(ADaptive WINdowing) 기반 drift 탐지기.

    값 스트림에 대해 적응형 윈도우를 유지하면서 분포 변화를 감지한다.
    윈도우를 두 부분(W_old, W_recent)으로 분할하여 평균 차이가
    통계적으로 유의미한지 검사한다.

    threshold = sqrt(1/(2*m) * ln(4*|W|/delta))
    여기서 m = 두 부분윈도우 크기의 조화평균.
    """

    DEFAULT_WINDOW_SIZE = timedelta(days=7)
    DEFAULT_SUBGROUP_SIZE = timedelta(minutes=5)
    DEFAULT_PARAMS = {
        "delta": 0.002,
        # baseline은 처음 N개의 subgroup으로 고정한다 (ratio가 아님).
        # 1.D 누적 재실행 패턴에서 baseline_ratio를 쓰면 cycle마다 baseline 위치가
        # 이동하여 ADWIN의 검출 위치가 흔들린다. 고정 포인트 수를 쓰면 같은 데이터
        # prefix에 대해 항상 같은 결정을 내려 dedup이 안정적으로 동작한다.
        "baseline_points": 30,
    }

    # ── 1.D 새 진입점 ──

    def analyze(self, new_data, data_ids, stream, params,
                calculated_until=None, previous_events=None):
        """3단계 패턴: (1) 누적+스냅샷 → (2) 알고리즘 → (3) commit.

        design_principles 21.2 원칙 145.
        """
        if new_data.empty or self.cache is None:
            return []

        # ── 1단계: 누적 + 스냅샷 (락 안, 짧음) ──
        snapshot = self.cache.append_and_snapshot(
            new_data.to_dict("records")
        )
        n = len(snapshot)

        params = {**self.DEFAULT_PARAMS, **params}
        delta = float(params["delta"])
        baseline_points = int(params["baseline_points"])
        # baseline은 고정 포인트 수. 데이터가 baseline 미달이면 모두 baseline에 들어감.
        baseline_end = min(baseline_points, n)

        # 알고리즘 실행 가능 조건 — 미달이면 raw만 cache에 남기고 종료.
        # 1.B placeholder는 더 이상 필요 없다. 차트는 raw로 그려진다.
        if baseline_end < 5 or (n - baseline_end) < 5:
            return []

        # ── 2단계: 계산 (락 밖) ──
        all_events, layer_rows = self._run_adwin(
            snapshot, stream, delta, baseline_end,
        )

        # 누적 재실행이므로 이전 cycle에서 이미 발견된 이벤트는 제외한다.
        new_events = self._dedupe_events(all_events, previous_events)

        # ── 3단계: 커밋 (락 안, 짧음) ──
        self.cache.commit_analysis(
            layer_rows=layer_rows,
            events=new_events,
        )
        return new_events

    def detect(self, data, data_ids, stream, params,
               calculated_until=None, previous_events=None):
        """Legacy 진입점 — analyze()로 이전됨.

        framework scheduler는 analyze()를 호출하므로 이 메서드는 호출되지 않는다.
        DriftPlugin 추상 메서드 계약을 만족하기 위해 남겨두며, 호출 시 명시적으로
        실패하여 잘못된 경로를 조기에 노출한다.
        """
        raise NotImplementedError(
            "HatDetector는 analyze()를 사용한다 — detect()는 호출되지 않아야 한다."
        )

    # ── 알고리즘 (락 밖에서 실행되는 순수 함수) ──

    def _run_adwin(self, snapshot, stream, delta, baseline_end):
        """누적 raw 스냅샷 전체에 ADWIN을 실행한다.

        baseline_end 는 분석 진입점에서 결정된 고정 baseline 길이이다.
        같은 데이터 prefix + 같은 baseline_end → 항상 같은 검출 결과 (dedup 안정성).

        Returns:
            (events, layer_rows):
              events — 발견된 모든 DriftEvent (dedup 전)
              layer_rows — 모든 timestamp의 running_mean / window_size
        """
        timestamps = [row["timestamp"] for row in snapshot]
        series = np.array(
            [float(row["value"]) for row in snapshot], dtype=float,
        )
        n = len(series)

        window = list(series[:baseline_end])
        window_sum = float(sum(window))

        mean_series = np.zeros(n)
        window_size_series = np.zeros(n, dtype=int)
        alarm_mask = np.zeros(n, dtype=int)
        alarm_indices = []

        # baseline 구간의 running mean / window size 기록
        for i in range(baseline_end):
            mean_series[i] = (
                float(window_sum / len(window)) if window else 0.0
            )
            window_size_series[i] = int(len(window))

        # ADWIN 순차 처리
        for i in range(baseline_end, n):
            val = float(series[i])
            window.append(val)
            window_sum += val

            drift_found, cut_point = self._adwin_check(window, delta)
            if drift_found and cut_point is not None:
                window = window[cut_point:]
                window_sum = float(sum(window))
                alarm_mask[i] = 1
                alarm_indices.append(i)

            mean_series[i] = (
                float(window_sum / len(window)) if window else 0.0
            )
            window_size_series[i] = int(len(window))

        # layer_rows — timestamp별 부가 컬럼
        layer_rows = [
            {
                "timestamp": timestamps[i],
                "running_mean": float(mean_series[i]),
                "window_size": int(window_size_series[i]),
            }
            for i in range(n)
        ]

        # events
        events = []
        for group_start, group_end in self._group_consecutive(alarm_indices):
            ids = [
                f"{stream}:{idx}" for idx in range(group_start, group_end + 1)
            ]
            peak_idx = group_start
            max_drop = 0
            for idx in range(group_start, group_end + 1):
                if alarm_mask[idx] == 1:
                    prev_ws = (
                        int(window_size_series[idx - 1]) if idx > 0 else 0
                    )
                    curr_ws = int(window_size_series[idx])
                    drop = prev_ws - curr_ws
                    if drop > max_drop:
                        max_drop = drop
                        peak_idx = idx

            prev_ws = (
                int(window_size_series[peak_idx - 1])
                if peak_idx > 0 else int(window_size_series[peak_idx])
            )
            curr_ws = int(window_size_series[peak_idx])
            score = (
                float(prev_ws - curr_ws) / float(prev_ws)
                if prev_ws > 0 else 0.0
            )
            score = max(score, 0.01)
            adj_score = score * 3.0

            events.append(DriftEvent(
                stream=stream,
                plugin="hat",
                detected_at=timestamps[peak_idx],
                data_from=timestamps[group_start],
                data_to=timestamps[group_end],
                severity=self._score_to_severity(adj_score),
                detected=True,
                score=round(float(adj_score), 4),
                message=(
                    f"ADWIN drift: window shrunk {prev_ws}->{curr_ws} "
                    f"(delta={delta})"
                ),
                data_ids=ids,
                data_count=int(len(ids)),
                detail={
                    "algorithm": "hat_adwin",
                    "delta": float(delta),
                    "baseline_points": int(baseline_end),
                    "window_before": int(prev_ws),
                    "window_after": int(curr_ws),
                    "alarm_count": int(group_end - group_start + 1),
                },
            ))

        return events, layer_rows

    @staticmethod
    def _dedupe_events(all_events, previous_events):
        """previous_events 와 detected_at 기준으로 매칭하여 새 이벤트만 반환한다.

        누적 재실행 패턴에서 같은 drift가 cycle마다 반복 보고되는 것을 막는다.

        주의: previous_events 는 cache.drift_events 에서 오는 dict 형태일 수도 있고
        DriftEvent 객체일 수도 있다. DriftEvent.to_dict() 는 detected_at 을 공백
        구분 문자열("2026-01-01 00:00:00")로 직렬화하지만, fresh DriftEvent.detected_at
        은 pandas.Timestamp 이며 isoformat() 은 "T" 구분 문자열을 반환한다.
        두 형식을 같은 키로 만들기 위해 양쪽을 datetime 으로 파싱해 정규화한다.
        """
        import pandas as pd

        def to_key(dt):
            if dt is None:
                return None
            if hasattr(dt, "isoformat") and not isinstance(dt, str):
                return pd.Timestamp(dt).isoformat()
            # 문자열 — pandas로 파싱하여 같은 형식으로 정규화
            try:
                return pd.Timestamp(dt).isoformat()
            except (ValueError, TypeError):
                return str(dt)

        existing_keys = set()
        for e in (previous_events or []):
            dt = (
                e.detected_at if hasattr(e, "detected_at")
                else e.get("detected_at")
            )
            key = to_key(dt)
            if key is not None:
                existing_keys.add(key)

        fresh = []
        for ev in all_events:
            key = to_key(ev.detected_at)
            if key not in existing_keys:
                fresh.append(ev)
        return fresh

    @staticmethod
    def _adwin_check(window, delta):
        """ADWIN 분할 검사.

        윈도우 W를 가능한 모든 지점에서 (W_old, W_recent)로 분할하여
        두 부분의 평균 차이가 임계값을 초과하는지 검사한다.

        threshold = sqrt(1/(2*m) * ln(4*|W|/delta))
        m = 조화평균(|W_old|, |W_recent|)

        Returns:
            (drift_found, cut_point): drift 감지 여부와 분할 지점
        """
        n = len(window)
        if n < 6:
            return False, None

        total_sum = sum(window)
        best_cut = None
        best_diff = 0.0

        ln_val = math.log(4.0 * n / delta)

        prefix_sum = sum(window[:3])

        for i in range(3, n - 2):
            if i > 3:
                prefix_sum += window[i - 1]
            n_old = i
            n_recent = n - i
            mean_old = prefix_sum / n_old
            mean_recent = (total_sum - prefix_sum) / n_recent
            diff = abs(mean_old - mean_recent)

            m = 2.0 * n_old * n_recent / (n_old + n_recent)
            threshold = math.sqrt(ln_val / (2.0 * m))

            if diff >= threshold and diff > best_diff:
                best_diff = diff
                best_cut = i

        if best_cut is not None:
            return True, best_cut
        return False, None

    def get_chart_config(self):
        return {
            "mainLabel": "Value",
            "yLabel": "Value",
            "layers": [
                {
                    "type": "line",
                    "field": "running_mean",
                    "label": "Running mean",
                    "color": "#ff7f0e",
                },
            ],
        }

    @staticmethod
    def _group_consecutive(indices, gap=5):
        if not indices:
            return []
        groups = []
        start = prev = indices[0]
        for idx in indices[1:]:
            if idx - prev > gap:
                groups.append((start, prev))
                start = idx
            prev = idx
        groups.append((start, prev))
        return groups

    @staticmethod
    def _score_to_severity(score):
        if score >= 2.0:
            return "critical"
        if score >= 1.0:
            return "warning"
        return "normal"
