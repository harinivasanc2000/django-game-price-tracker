from django import template

from apps.games.fx import to_gbp_or_zero
from apps.games.prediction import predict_deal

register = template.Library()


@register.inclusion_tag("games/_prediction.html", takes_context=True)
def deal_prediction_panel(context):
    d = context.get("d") or {}
    live = context.get("live_offers") or []
    launch = context.get("launch")
    catalog = context.get("catalog_game") or context.get("already_tracked")

    steam_gbp = None
    if d.get("price_status") == "paid" and d.get("price") is not None:
        steam_gbp = float(to_gbp_or_zero(d["price"], d.get("currency") or "GBP"))

    best_gbp = float(live[0]["price_gbp"]) if live else steam_gbp
    best_kind = live[0].get("kind") if live else "official"

    pred = predict_deal(
        title=d.get("name") or "",
        steam_price_gbp=steam_gbp,
        steam_discount=d.get("discount") or 0,
        launch_gbp=float(launch) if launch else None,
        best_offer_gbp=best_gbp,
        best_offer_kind=best_kind,
        game=catalog,
    )
    return {"pred": pred}
