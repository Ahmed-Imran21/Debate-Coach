#!/usr/bin/env python3
"""
Evaluate visual_analysis/events.py against hand-labelled ground
truth (docs/video-analysis/THRESHOLD_TUNING.md).

Reads local files only: a directory of stored VisualSignalTrack
JSON documents (plain or gzipped, one per session, named
<session_id>.json[.gz]) and a single labels CSV
(session_id,type,start,end). Nothing here touches the network, the
database, or object storage.

Usage:
    .venv/bin/python scripts/evaluate_visual_events.py \
        --tracks-dir path/to/tracks \
        --labels path/to/labels.csv \
        [--iou-threshold 0.3]
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from visual_analysis.events import detect_events  # noqa: E402
from visual_analysis.schema import VisualSignalTrack  # noqa: E402
from visual_analysis.signals import prepare_signals  # noqa: E402

LABELLED_TYPES = ("gaze_away", "head_down", "gesture")


@dataclass(frozen=True)
class Interval:
    start: float
    end: float


def _load_track(path: Path) -> VisualSignalTrack:
    raw = path.read_bytes()
    if path.suffix == ".gz" or raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    data = json.loads(raw.decode("utf-8"))
    return VisualSignalTrack.model_validate(data)


def _discover_tracks(tracks_dir: Path) -> dict[str, Path]:
    tracks: dict[str, Path] = {}
    for path in sorted(tracks_dir.iterdir()):
        if path.name.endswith(".json.gz"):
            session_id = path.name[: -len(".json.gz")]
        elif path.name.endswith(".json"):
            session_id = path.name[: -len(".json")]
        else:
            continue
        tracks[session_id] = path
    return tracks


def _load_labels(labels_path: Path) -> dict[str, dict[str, list[Interval]]]:
    labels: dict[str, dict[str, list[Interval]]] = defaultdict(lambda: defaultdict(list))
    with labels_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            session_id = row["session_id"].strip()
            event_type = row["type"].strip()
            start = float(row["start"])
            end = float(row["end"])
            labels[session_id][event_type].append(Interval(start, end))
    return labels


def _iou(a: Interval, b: Interval) -> float:
    inter = max(0.0, min(a.end, b.end) - max(a.start, b.start))
    if inter <= 0:
        return 0.0
    # Safe for overlapping intervals (the only case inter > 0 can
    # happen): the combined bounding span equals the true union
    # length exactly when the two intervals overlap.
    union = max(a.end, b.end) - min(a.start, b.start)
    return inter / union if union > 0 else 0.0


def _match(
    predicted: list[Interval],
    labelled: list[Interval],
    iou_threshold: float,
) -> tuple[int, int, int, list[float]]:
    """Greedy one-to-one matching. Returns (tp, fp, fn, matched_ious)."""

    remaining_pred = list(enumerate(predicted))
    matched_ious: list[float] = []
    tp = 0

    for truth in labelled:
        best_index = None
        best_iou = 0.0
        for list_index, (_, pred) in enumerate(remaining_pred):
            score = _iou(truth, pred)
            if score > best_iou:
                best_iou = score
                best_index = list_index
        if best_index is not None and best_iou >= iou_threshold:
            tp += 1
            matched_ious.append(best_iou)
            remaining_pred.pop(best_index)

    fn = len(labelled) - tp
    fp = len(remaining_pred)
    return tp, fp, fn, matched_ious


def evaluate(tracks_dir: Path, labels_path: Path, iou_threshold: float) -> None:
    tracks = _discover_tracks(tracks_dir)
    labels = _load_labels(labels_path)

    missing = set(labels) - set(tracks)
    if missing:
        print(f"warning: no track file found for labelled session(s): {sorted(missing)}", file=sys.stderr)

    totals: dict[str, dict[str, float]] = {
        t: {"tp": 0, "fp": 0, "fn": 0, "iou_sum": 0.0, "iou_n": 0} for t in LABELLED_TYPES
    }

    for session_id, track_path in tracks.items():
        session_labels = labels.get(session_id)
        if not session_labels:
            continue

        track = _load_track(track_path)
        speech_segments = [{"start": 0.0, "end": track.clock.duration_s}]
        prepared = prepare_signals(track, speech_segments)
        events = detect_events(prepared, track.degradations)

        for event_type in LABELLED_TYPES:
            predicted = [Interval(e["start"], e["end"]) for e in events if e["type"] == event_type]
            truth = session_labels.get(event_type, [])
            if not truth and not predicted:
                continue

            tp, fp, fn, ious = _match(predicted, truth, iou_threshold)
            totals[event_type]["tp"] += tp
            totals[event_type]["fp"] += fp
            totals[event_type]["fn"] += fn
            totals[event_type]["iou_sum"] += sum(ious)
            totals[event_type]["iou_n"] += len(ious)

    print(f"{'type':<12} {'precision':>10} {'recall':>10} {'mean IoU':>10} {'tp':>5} {'fp':>5} {'fn':>5}")
    for event_type in LABELLED_TYPES:
        t = totals[event_type]
        precision = t["tp"] / (t["tp"] + t["fp"]) if (t["tp"] + t["fp"]) else float("nan")
        recall = t["tp"] / (t["tp"] + t["fn"]) if (t["tp"] + t["fn"]) else float("nan")
        mean_iou = t["iou_sum"] / t["iou_n"] if t["iou_n"] else float("nan")
        print(
            f"{event_type:<12} {precision:>10.3f} {recall:>10.3f} {mean_iou:>10.3f} "
            f"{int(t['tp']):>5} {int(t['fp']):>5} {int(t['fn']):>5}"
        )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tracks-dir", required=True, type=Path, help="Directory of <session_id>.json[.gz] track files")
    parser.add_argument("--labels", required=True, type=Path, help="CSV with columns session_id,type,start,end")
    parser.add_argument("--iou-threshold", type=float, default=0.3, help="Minimum IoU to count as a match (default 0.3)")
    args = parser.parse_args(argv)

    if not args.tracks_dir.is_dir():
        parser.error(f"not a directory: {args.tracks_dir}")
    if not args.labels.is_file():
        parser.error(f"not a file: {args.labels}")

    evaluate(args.tracks_dir, args.labels, args.iou_threshold)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
