get_player_metrics = {
    "name": "get_player_metrics",
    "description": (
        "Look up a named MLB batter in the Baseball Savant CSV. Return Hard-Hit%, "
        "Barrel% per batted-ball event, Adjusted EV in mph, K%, LA Sweet-Spot%, "
        "Whiff%, and plate appearances. Include the player ID, season, export "
        "provenance, evidence ID, and same-season cohort benchmarks for available "
        "metrics. Use null for missing values. Report an ambiguous match with "
        "candidates. Report a plate-appearance shortfall only when verified."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "player_name": {
                "type": "string",
                "minLength": 1,
                "description": "The player's name, such as 'Shohei Ohtani' or 'Jung Hoo Lee'.",
            },
            "player_id": {
                "type": "integer",
                "minimum": 1,
                "description": "Verified MLB player ID to disambiguate the supplied name.",
            },
            "season": {
                "type": "integer",
                "minimum": 2015,
                "default": 2026,
                "description": "Statcast season to look up. Omit for the 2026 project export.",
            },
        },
        "required": ["player_name"],
        "additionalProperties": False,
    },
}

find_reference_player = {
    "name": "find_reference_player",
    "description": (
        "Rank eligible MLB batters by a batting style or a single metric using the "
        "Baseball Savant CSV. For fewer swings overall, rank Swing% ascending. "
        "For fewer swings at pitches outside the zone, rank Chase% ascending. "
        "For fewer misses per swing, rank Whiff% ascending. Use contact for frequent "
        "contact, or contact_low_swing for frequent contact with fewer swings. "
        "Clarify ambiguous goals before calling. "
        "Return rank, player ID and name, plate appearances, ranking value, "
        "supporting metrics, cohort benchmarks, export provenance, and an evidence ID. "
        "For Swing% and Chase% rankings, include Swing%, Chase%, and Zone Swing% "
        "when available. For contact rankings, include K%, Whiff%, Contact% "
        "(100 minus Whiff%), Swing%, and Hard-Hit% when available. Return "
        "metric_unavailable if the export lacks a required ranking column. For a "
        "named batter's approach or swing mechanics, call RAG_Retrieval."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "criteria": {
                "type": "object",
                "description": "Choose either a batting style or a single metric.",
                "oneOf": [
                    {
                        "properties": {
                            "style": {
                                "type": "string",
                                "enum": ["power", "contact", "contact_low_swing", "mid_range"],
                                "description": (
                                    "Power averages percentiles for barrel_batted_rate, "
                                    "hard_hit_percent, and avg_hyper_speed (Adjusted EV). "
                                    "Contact favors low k_percent and whiff_percent equally. "
                                    "Contact_low_swing orders the top ten contact hitters by "
                                    "lowest swing_percent. Mid-range ranks higher "
                                    "sweet_spot_percent first as a launch-angle proxy."
                                ),
                            },
                        },
                        "required": ["style"],
                        "additionalProperties": False,
                    },
                    {
                        "properties": {
                            "metric": {
                                "type": "string",
                                "enum": [
                                    "hard_hit_percent",
                                    "barrel_percent",
                                    "adjusted_exit_velocity_mph",
                                    "strikeout_percent",
                                    "launch_angle_sweet_spot_percent",
                                    "whiff_percent",
                                    "swing_percent",
                                    "chase_percent",
                                ],
                                "description": (
                                    "Metric to sort by across eligible batters. Swing% uses all pitches. "
                                    "Chase% uses pitches outside the strike zone. Whiff% uses swings."
                                ),
                            },
                            "direction": {
                                "type": "string",
                                "enum": ["asc", "desc"],
                                "default": "desc",
                                "description": "Use 'asc' for lowest values and 'desc' for highest.",
                            },
                        },
                        "required": ["metric"],
                        "additionalProperties": False,
                    },
                ],
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10,
                "default": 10,
                "description": "Maximum number of batters to return. Omit for up to ten.",
            },
        },
        "required": ["criteria"],
        "additionalProperties": False,
    },
}

rag_retrieval = {
    "name": "RAG_Retrieval",
    "description": (
        "Retrieve passages from the reviewed baseball hitting index for mechanics, "
        "explanations, player breakdowns, examples, or drills. Return excerpts, "
        "source titles and links, page or video timestamp where available, evidence IDs, "
        "and equipment requirements for drills. Report insufficient evidence when "
        "the index cannot support the requested coaching or player-specific claim."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "minLength": 1,
                "description": "A focused batting question or skill to search for.",
            },
            "content_types": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["mechanics", "player_breakdown", "example", "drill"],
                },
                "minItems": 1,
                "uniqueItems": True,
                "description": "Restrict to any of these content types. Omit to search all types.",
            },
            "player_name": {
                "type": "string",
                "minLength": 1,
                "description": "Require this player in the source metadata for a named-player breakdown.",
            },
            "player_level": {
                "type": "string",
                "enum": ["youth", "high_school", "adult_amateur"],
                "description": "Hitter's playing level, when known.",
            },
            "available_equipment": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "uniqueItems": True,
                "description": (
                    "Equipment available for drills, such as bat, baseballs, tee, and net. "
                    "Omit if unknown. An empty list means no equipment is available."
                ),
            },
            "top_k": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10,
                "default": 5,
                "description": "Maximum number of passages to return. Omit for up to five.",
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}

validate_response = {
    "name": "validate_response",
    "description": (
        "Check a draft batting answer against the application's answer schema and "
        "the trusted evidence retrieved for the current request. Return issue codes "
        "and affected claims for invalid structure, missing citations, unsupported "
        "claims, numerical mismatches, or drills requiring unavailable equipment."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "draft_answer": {
                "type": "object",
                "description": "Draft response payload, with evidence IDs on source-dependent claims.",
            },
            "evidence_ids": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "uniqueItems": True,
                "description": "IDs returned by retrieval and stats tools for this request. May be empty.",
            },
            "available_equipment": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "uniqueItems": True,
                "description": "Known equipment available to the hitter. Omit if unknown.",
            },
        },
        "required": ["draft_answer", "evidence_ids"],
        "additionalProperties": False,
    },
}

get_bat_tracking_metrics = {
    "name": "get_bat_tracking_metrics",
    "description": (
        "Look up measured MLB swing traits for one batter and season in Statcast "
        "Bat Tracking and Swing Path data. Return available average bat speed, swing "
        "length, attack angle, and swing path tilt with units, sample counts where "
        "available, source links, and an evidence ID. Report missing tracking coverage explicitly."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "player_name": {
                "type": "string",
                "minLength": 1,
                "description": "The MLB batter whose measured swing traits are requested.",
            },
            "player_id": {
                "type": "integer",
                "minimum": 1,
                "description": "Verified MLB player ID to disambiguate the supplied name.",
            },
            "season": {
                "type": "integer",
                "minimum": 2023,
                "default": 2026,
                "description": "Bat-tracking season to look up. Omit for the project season, 2026.",
            },
        },
        "required": ["player_name"],
        "additionalProperties": False,
    },
}
