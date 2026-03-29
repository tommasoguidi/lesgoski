# services/grouping.py
from collections import defaultdict
from lesgoski.services.airports import get_nearby_set
from lesgoski.webapp.utils import get_country_code


def group_deals_by_destination(deals):
    """
    Groups a list of deals by metro-area destination code.
    Returns a list of dicts sorted by best_deal.total_price_pp ascending:
      {
        "destination_code": str,
        "destination_name": str,
        "country_code": str,
        "country_flag": str,
        "best_deal": Deal,
        "other_deals": [Deal, ...],
      }
    Deals must have outbound and inbound flights loaded (not None).
    """
    grouped = defaultdict(list)
    dest_full_names = {}

    for deal in deals:
        out_dest = deal.outbound.destination
        in_origin = deal.inbound.origin

        area_codes = get_nearby_set(out_dest) | get_nearby_set(in_origin)
        for code in area_codes:
            grouped[code].append(deal)

        for code, full_name in [
            (out_dest, deal.outbound.destination_full or out_dest),
            (in_origin, deal.inbound.origin_full or in_origin),
        ]:
            if code not in dest_full_names:
                dest_full_names[code] = full_name

    # Only keep codes that appear as actual direct flight airports
    direct_codes = set()
    for deal in deals:
        direct_codes.add(deal.outbound.destination)
        direct_codes.add(deal.inbound.origin)

    result = []
    for dest_code, deal_list in grouped.items():
        if not deal_list or dest_code not in direct_codes:
            continue

        seen_ids = set()
        unique_deals = []
        for d in deal_list:
            if d.id not in seen_ids:
                seen_ids.add(d.id)
                unique_deals.append(d)
        unique_deals.sort(key=lambda x: x.total_price_pp)

        full_name = dest_full_names.get(dest_code, dest_code)
        country_code = get_country_code(full_name)

        result.append({
            "destination_code": dest_code,
            "destination_name": full_name.split(',')[0].strip(),
            "country_code": country_code,
            "country_flag": f"https://flagsapi.com/{country_code.upper()}/shiny/64.png",
            "best_deal": unique_deals[0],
            "other_deals": unique_deals[1:],
        })

    result.sort(key=lambda x: x["best_deal"].total_price_pp)
    return result
