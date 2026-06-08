import json
from datetime import date, timedelta

from database import query, execute, init_db
from dotenv import load_dotenv
from mcp.server import Server
from mcp.types import Tool, TextContent

load_dotenv()
init_db()

server = Server("icecream-stand")


# ── Tool definitions ──────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [

        # ── Flavor catalog ────────────────────────────────────────────────────

        Tool(
            name="get_flavors",
            description=(
                "Return the full catalog of ice cream flavors. "
                "Optionally filter by availability, category, vegan/dairy-free/nut flags, or season."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "available_only": {
                        "type": "boolean",
                        "description": "If true, only return flavors currently in stock. Default true."
                    },
                    "category": {
                        "type": "string",
                        "description": "Filter by category: 'fruit', 'chocolate', 'nutty', 'seasonal', 'classic', etc."
                    },
                    "vegan_only": {"type": "boolean"},
                    "dairy_free_only": {"type": "boolean"},
                    "nut_free_only": {"type": "boolean"},
                    "season": {
                        "type": "string",
                        "description": "Filter by season label, e.g. 'summer', 'winter', 'all'."
                    }
                }
            }
        ),

        Tool(
            name="get_flavor",
            description="Return details for a single flavor by its ID.",
            inputSchema={
                "type": "object",
                "required": ["flavor_id"],
                "properties": {
                    "flavor_id": {"type": "integer"}
                }
            }
        ),

        Tool(
            name="get_daily_features",
            description=(
                "Return the 3 featured flavors for a given date (default: today). "
                "Includes the reason each was selected."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "YYYY-MM-DD, default today."
                    }
                }
            }
        ),

        Tool(
            name="get_feature_history",
            description="Return feature history for the last N days so you can see rotation patterns.",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of recent days to return. Default 14."
                    }
                }
            }
        ),

        Tool(
            name="set_daily_features",
            description=(
                "Manually set the 3 featured flavors for a specific date. "
                "Provide an array of exactly 3 flavor IDs. "
                "Optionally include a reason string for each slot."
            ),
            inputSchema={
                "type": "object",
                "required": ["date", "flavor_ids"],
                "properties": {
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "flavor_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "minItems": 3,
                        "maxItems": 3,
                        "description": "Exactly 3 flavor IDs, in slot order 1-2-3."
                    },
                    "reasons": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional reason per slot (3 strings)."
                    }
                }
            }
        ),

        Tool(
            name="suggest_daily_features",
            description=(
                "Suggest the best 3 flavors to feature today based on the configured rules "
                "(recency, popularity, variety, seasonality). "
                "Returns ranked candidates and the suggested trio with reasoning — "
                "does NOT write to the database; call set_daily_features to confirm."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date to plan for. Default today."
                    }
                }
            }
        ),

        # ── Feature rules ─────────────────────────────────────────────────────

        Tool(
            name="get_feature_rules",
            description="Return all configured rules that govern how daily features are selected.",
            inputSchema={"type": "object", "properties": {}}
        ),

        Tool(
            name="update_feature_rule",
            description=(
                "Update a single feature rule value. "
                "Known rule_keys: min_days_since_featured, require_one_seasonal, "
                "require_variety, boost_low_popularity, popularity_weight, "
                "recency_weight, random_weight."
            ),
            inputSchema={
                "type": "object",
                "required": ["rule_key", "rule_value"],
                "properties": {
                    "rule_key": {"type": "string"},
                    "rule_value": {"type": "string"}
                }
            }
        ),

    ]


# ── Tool handlers ─────────────────────────────────────────────────────────────

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    def respond(data) -> list[TextContent]:
        return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]

    today = date.today().isoformat()

    # ── Flavor catalog ────────────────────────────────────────────────────────

    if name == "get_flavors":
        conditions = []
        params = []

        available_only = arguments.get("available_only", True)
        if available_only:
            conditions.append("is_available = TRUE")

        if "category" in arguments:
            conditions.append("category = %s")
            params.append(arguments["category"])

        if arguments.get("vegan_only"):
            conditions.append("is_vegan = TRUE")

        if arguments.get("dairy_free_only"):
            conditions.append("is_dairy_free = TRUE")

        if arguments.get("nut_free_only"):
            conditions.append("contains_nuts = FALSE")

        if "season" in arguments:
            conditions.append("(season = %s OR season = 'all')")
            params.append(arguments["season"])

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"SELECT * FROM flavors {where} ORDER BY popularity_score DESC"
        rows = query(sql, params or None)
        return respond(rows)

    elif name == "get_flavor":
        rows = query("SELECT * FROM flavors WHERE id = %s", (arguments["flavor_id"],))
        return respond(rows[0] if rows else {"error": "Flavor not found"})

    # ── Daily features ────────────────────────────────────────────────────────

    elif name == "get_daily_features":
        d = arguments.get("date", today)
        rows = query("""
            SELECT df.slot, df.reason, df.date,
                   f.id AS flavor_id, f.name, f.category, f.description,
                   f.is_vegan, f.is_dairy_free, f.contains_nuts, f.popularity_score
            FROM daily_features df
            JOIN flavors f ON f.id = df.flavor_id
            WHERE df.date = %s
            ORDER BY df.slot ASC
        """, (d,))
        return respond(rows if rows else {"message": f"No features set for {d}."})

    elif name == "get_feature_history":
        days = arguments.get("days", 14)
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        rows = query("""
            SELECT df.date, df.slot, df.reason,
                   f.id AS flavor_id, f.name, f.category
            FROM daily_features df
            JOIN flavors f ON f.id = df.flavor_id
            WHERE df.date >= %s
            ORDER BY df.date DESC, df.slot ASC
        """, (cutoff,))
        return respond(rows)

    elif name == "set_daily_features":
        d = arguments["date"]
        flavor_ids = arguments["flavor_ids"]
        reasons = arguments.get("reasons", ["", "", ""])

        # Clear existing for the day first
        execute("DELETE FROM daily_features WHERE date = %s", (d,))

        for slot, (fid, reason) in enumerate(zip(flavor_ids, reasons), start=1):
            execute("""
                INSERT INTO daily_features (date, flavor_id, slot, reason)
                VALUES (%s, %s, %s, %s)
            """, (d, fid, slot, reason))

        # Update days_since_last_featured for all flavors
        execute("""
            UPDATE flavors
            SET days_since_last_featured = (
                SELECT COALESCE(
                    (SELECT EXTRACT(DAY FROM NOW() - MAX(df.date::DATE))
                     FROM daily_features df WHERE df.flavor_id = flavors.id),
                    999
                )
            )
        """)

        rows = query("""
            SELECT df.slot, df.reason, f.id, f.name
            FROM daily_features df JOIN flavors f ON f.id = df.flavor_id
            WHERE df.date = %s ORDER BY df.slot
        """, (d,))
        return respond({"status": "set", "date": d, "features": rows})

    elif name == "suggest_daily_features":
        d = arguments.get("date", today)

        # Load rules
        rule_rows = query("SELECT rule_key, rule_value FROM feature_rules")
        rules = {r["rule_key"]: r["rule_value"] for r in rule_rows}

        min_days = int(rules.get("min_days_since_featured", 3))
        require_seasonal = rules.get("require_one_seasonal", "true").lower() == "true"
        require_variety = rules.get("require_variety", "true").lower() == "true"
        popularity_weight = float(rules.get("popularity_weight", 0.4))
        recency_weight = float(rules.get("recency_weight", 0.4))
        random_weight = float(rules.get("random_weight", 0.2))

        # Get all available flavors
        candidates = query("""
            SELECT f.*,
                   COALESCE(
                       (SELECT EXTRACT(DAY FROM %s::DATE - MAX(df.date::DATE))
                        FROM daily_features df WHERE df.flavor_id = f.id),
                       999
                   ) AS days_out
            FROM flavors f
            WHERE f.is_available = TRUE
        """, (d,))

        # Filter out recently featured
        eligible = [c for c in candidates if (c.get("days_out") or 999) >= min_days]

        if len(eligible) < 3:
            return respond({
                "error": (
                    f"Only {len(eligible)} eligible flavor(s) after applying "
                    f"min_days_since_featured={min_days}. "
                    "Consider lowering that rule or making more flavors available."
                )
            })

        import random

        max_pop = max(c["popularity_score"] for c in eligible) or 1
        max_days = max(c.get("days_out") or 0 for c in eligible) or 1

        for c in eligible:
            pop_norm = (c["popularity_score"] or 5) / max_pop
            rec_norm = min((c.get("days_out") or 999), max_days) / max_days
            rand_component = random.random()
            c["_score"] = (
                popularity_weight * pop_norm
                + recency_weight * rec_norm
                + random_weight * rand_component
            )

        eligible.sort(key=lambda x: x["_score"], reverse=True)

        selected = []
        reasons = []

        if require_seasonal:
            seasonal = [c for c in eligible if c.get("season") not in (None, "all")]
            if seasonal:
                pick = seasonal[0]
                selected.append(pick)
                reasons.append(f"Seasonal feature ({pick['season']}), score {pick['_score']:.2f}")
                eligible = [c for c in eligible if c["id"] != pick["id"]]

        for c in eligible:
            if len(selected) >= 3:
                break
            if require_variety and len(selected) == 2:
                categories_so_far = {s["category"] for s in selected}
                if c["category"] in categories_so_far and len(categories_so_far) < 2:
                    continue  # skip to find a different category
            selected.append(c)
            reasons.append(
                f"Score {c['_score']:.2f} "
                f"(pop={c['popularity_score']}, days_out={c.get('days_out')})"
            )

        if len(selected) < 3:
            remaining = [c for c in eligible if c["id"] not in {s["id"] for s in selected}]
            for c in remaining:
                if len(selected) >= 3:
                    break
                selected.append(c)
                reasons.append(f"Backfill — score {c['_score']:.2f}")

        suggestion = [
            {
                "slot": i + 1,
                "flavor_id": s["id"],
                "name": s["name"],
                "category": s["category"],
                "season": s.get("season"),
                "popularity_score": s["popularity_score"],
                "days_since_featured": s.get("days_out"),
                "reason": reasons[i],
            }
            for i, s in enumerate(selected[:3])
        ]

        return respond({
            "suggested_date": d,
            "suggestion": suggestion,
            "note": "Call set_daily_features with the flavor_ids to confirm this selection."
        })

    # ── Feature rules ─────────────────────────────────────────────────────────

    elif name == "get_feature_rules":
        rows = query("SELECT * FROM feature_rules ORDER BY id")
        return respond(rows)

    elif name == "update_feature_rule":
        execute("""
            INSERT INTO feature_rules (rule_key, rule_value)
            VALUES (%s, %s)
            ON CONFLICT (rule_key) DO UPDATE SET rule_value = EXCLUDED.rule_value
        """, (arguments["rule_key"], arguments["rule_value"]))
        return respond({"status": "updated", "rule_key": arguments["rule_key"],
                        "new_value": arguments["rule_value"]})

    return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]