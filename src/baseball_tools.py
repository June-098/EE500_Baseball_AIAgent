import csv
import hashlib
import io
import json
from bisect import bisect_left, bisect_right
from math import isfinite
from pathlib import Path
from statistics import mean, median


METRIC_COLUMNS = {
    "hard_hit_percent": "hard_hit_percent",
    "barrel_percent": "barrel_batted_rate",
    "adjusted_exit_velocity_mph": "avg_hyper_speed",
    "strikeout_percent": "k_percent",
    "launch_angle_sweet_spot_percent": "sweet_spot_percent",
    "whiff_percent": "whiff_percent",
    "swing_percent": "swing_percent",
    "chase_percent": "oz_swing_percent",
}
METRIC_NAMES_BY_COLUMN = {column: metric for metric, column in METRIC_COLUMNS.items()}
CONTACT_COLUMNS = ("k_percent", "whiff_percent")
STYLE_COLUMNS = {
    "power": ("barrel_batted_rate", "hard_hit_percent", "avg_hyper_speed"),
    "contact": CONTACT_COLUMNS,
    "contact_low_swing": CONTACT_COLUMNS,
    "mid_range": ("sweet_spot_percent",),
}


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _read_players(reader, columns):
    players = {}
    for row in reader:
        player_id = int(row["player_id"])
        plate_appearances = int(row["pa"])
        raw_name = row["last_name, first_name"].strip()
        if player_id in players or player_id < 1 or plate_appearances < 0 or not raw_name:
            raise ValueError("Invalid or duplicate player record")

        last, separator, first = raw_name.partition(",")
        name = f"{first.strip()} {last.strip()}" if separator else raw_name
        metrics = {metric: _number(row[column]) for metric, column in columns.items()}
        whiff = metrics.get("whiff_percent")
        if whiff is not None:
            metrics["contact_percent"] = round(100 - whiff, 2)
        players[player_id] = {
            "player_id": player_id,
            "player_name": name,
            "plate_appearances": plate_appearances,
            "metrics": metrics,
        }
    return list(players.values())


def _average_ranks(players, metrics, direction):
    values = {
        metric: sorted(direction * player["metrics"][metric] for player in players)
        for metric in metrics
    }
    ranks = {}
    for player in players:
        metric_ranks = []
        for metric, ordered in values.items():
            value = direction * player["metrics"][metric]
            # Tied values share the average of their one-based ranks.
            metric_ranks.append((bisect_left(ordered, value) + bisect_right(ordered, value) + 1) / 2)
        ranks[player["player_id"]] = mean(metric_ranks)
    return ranks


def _cohort(players):
    medians = {}
    for metric in METRIC_COLUMNS.keys() | {"zone_swing_percent", "contact_percent"}:
        values = [
            value for player in players
            if (value := player["metrics"].get(metric)) is not None
        ]
        if values:
            medians[metric] = median(values)
    appearances = [player["plate_appearances"] for player in players]
    return {
        "player_count": len(players),
        "observed_pa_range": [min(appearances), max(appearances)],
        "medians": medians,
    }


def find_reference_player(criteria, limit=10, *, stats_path):
    """Rank MLB batters using a Savant CSV path configured by the agent host."""
    if type(limit) is not int or not 1 <= limit <= 10:
        return {"status": "invalid_input", "message": "Use a limit of 1 to 10."}
    if not isinstance(criteria, dict):
        return {"status": "invalid_input", "message": "Supply a style or metric."}

    style = criteria.get("style")
    metric = criteria.get("metric")
    direction = criteria.get("direction", "desc")
    if set(criteria) == {"style"} and isinstance(style, str) and style in STYLE_COLUMNS:
        required_columns = STYLE_COLUMNS[style]
        required_metrics = tuple(METRIC_NAMES_BY_COLUMN[column] for column in required_columns)
    elif (
        "metric" in criteria
        and set(criteria) <= {"metric", "direction"}
        and isinstance(metric, str)
        and metric in METRIC_COLUMNS
        and direction in ("asc", "desc")
    ):
        required_metrics = (metric,)
        required_columns = (METRIC_COLUMNS[metric],)
    else:
        return {"status": "invalid_input", "message": "Choose one supported style or metric and sort direction."}

    source_path = Path(stats_path)
    try:
        contents = source_path.read_bytes()
        reader = csv.DictReader(io.StringIO(contents.decode("utf-8-sig"), newline=""), strict=True)
        headers = set(reader.fieldnames or ())
        if not {"last_name, first_name", "player_id", "pa"} <= headers:
            return {"status": "invalid_dataset", "message": "The CSV is missing required player columns."}
        needed = required_columns + (("swing_percent",) if style == "contact_low_swing" else ())
        missing = [column for column in needed if column not in headers]
        if missing:
            return {"status": "metric_unavailable", "missing_columns": missing}
        columns = {
            key: column for key, column in (METRIC_COLUMNS | {"zone_swing_percent": "z_swing_percent"}).items()
            if column in headers
        }
        players = _read_players(reader, columns)
    except OSError:
        return {"status": "dataset_unavailable", "message": "The configured CSV could not be read."}
    except (csv.Error, ValueError, TypeError, AttributeError):
        return {"status": "invalid_dataset", "message": "The CSV contains an invalid player record."}

    eligible = [
        player for player in players
        if player["plate_appearances"] > 0
        and all(player["metrics"][key] is not None for key in required_metrics)
    ]
    if not eligible:
        return {"status": "no_eligible_players"}

    if style in ("power", "contact", "contact_low_swing"):
        ranks = _average_ranks(eligible, required_metrics, -1 if style == "power" else 1)
        ordered = sorted(eligible, key=lambda player: (ranks[player["player_id"]], player["player_id"]))
        denominator = len(ordered) - 1
        for position, player in enumerate(ordered, 1):
            rank = ranks[player["player_id"]]
            player["ranking_value"] = round(100 * (len(ordered) - rank) / denominator, 2) if denominator else 100.0
            if style != "power":
                player["contact_rank"] = position
        ranking_metric = "power_score" if style == "power" else "contact_score"
        if style == "contact_low_swing":
            ordered = [player for player in ordered[:10] if player["metrics"]["swing_percent"] is not None]
            ordered.sort(key=lambda player: (player["metrics"]["swing_percent"], player["contact_rank"]))
            ranking_metric = "swing_percent"
            for player in ordered:
                player["contact_score"] = player["ranking_value"]
                player["ranking_value"] = player["metrics"][ranking_metric]
    else:
        ranking_metric = required_metrics[0]
        sign = 1 if direction == "asc" else -1
        ordered = sorted(
            eligible, key=lambda player: (sign * player["metrics"][ranking_metric], player["player_id"])
        )
        for player in ordered:
            player["ranking_value"] = player["metrics"][ranking_metric]

    if not ordered:
        return {"status": "no_eligible_players"}
    results = ordered[:limit]
    for rank, player in enumerate(results, 1):
        player["rank"] = rank

    checksum = hashlib.sha256(contents).hexdigest()
    evidence_key = json.dumps([checksum, criteria, limit], sort_keys=True)
    return {
        "status": "ok",
        "criteria": criteria,
        "ranking_metric": ranking_metric,
        "cohort": _cohort(eligible),
        "source": {"file": source_path.name, "sha256": checksum},
        "evidence_id": f"savant-{hashlib.sha256(evidence_key.encode()).hexdigest()[:16]}",
        "players": results,
    }
