"""Pure checks shared by the external browser capture and local tests."""

FOOD_TYPES = ("restaurant",)


def validate_moves(moves, errors, taste_requests):
    if errors:
        raise ValueError("Browser errors: " + "; ".join(errors))
    if taste_requests != 1 or len(moves) != 5:
        raise ValueError(f"Judge path failed: requests={taste_requests}, moves={len(moves)}")
    food = next((row for row in moves if str(row.get("role") or "").strip().casefold() == "hospitality"), None)
    if not food:
        raise ValueError("Hospitality move is missing.")
    entity_type = str(food.get("entity_type") or "").strip().casefold().replace(" ", "_")
    if not any(token in entity_type for token in FOOD_TYPES):
        raise ValueError(f"Hospitality is not restaurant-typed: {food}")
    return food


def validate_layout(nav_box, inner_width, scroll_width):
    if not nav_box or nav_box["x"] < 0 or nav_box["x"] + nav_box["width"] > inner_width:
        raise ValueError(f"Brand Planner nav is clipped: {nav_box}")
    if scroll_width != inner_width:
        raise ValueError(f"Phone page overflows: innerWidth={inner_width}, scrollWidth={scroll_width}")


def validate_capture(moves, nav_box, inner_width, scroll_width, errors, taste_requests):
    food = validate_moves(moves, errors, taste_requests)
    validate_layout(nav_box, inner_width, scroll_width)
    return food
