import xmlrpc.client
from collections import defaultdict
from datetime import datetime
from dateutil.relativedelta import relativedelta
import json
import geoip2.database

# ====================
# HELPER FUNCTIONS
# ====================

def connect_to_odoo():
    url = "https://crm.abracasabra.es"
    db = "crm.abracasabra.es"
    username = "info@abracasabra.es"
    password = "2345nicekid"

    try:
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
        uid = common.authenticate(db, username, password, {})
        if not uid:
            raise Exception("Authentication failed")
        models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
        return uid, models, db, password
    except Exception as e:
        print(f"❌ Odoo Connection Error: {e}")
        return None, None, None, None


def get_all_months_this_year():
    now = datetime.now()
    return [f"{now.year}-{month:02d}" for month in range(1, 13)]


def is_bot(view):
    """Return True if user_agent indicates a bot."""
    ua = (view.get('user_agent') or '').lower()
    return any(bot in ua for bot in ['gptbot', 'claudebot', 'spider'])


# ====================
# STATS FUNCTIONS
# ====================

def get_top_viewed_property_links(uid, models, db, password, top_n=20):
    """
    Get the most viewed properties of all time, ensuring that only existing and active properties are included.
    """
    view_counts = defaultdict(int)
    batch_size = 5000
    offset = 0

    try:
        all_ids = models.execute_kw(
            db, uid, password,
            'property.view', 'search',
            [[]],
            {'order': 'date desc'}
        )

        while offset < len(all_ids):
            batch_ids = all_ids[offset:offset + batch_size]
            records = models.execute_kw(
                db, uid, password,
                'property.view', 'read',
                [batch_ids],
                {'fields': ['property_id', 'user_agent']}
            )
            for v in records:
                if is_bot(v):
                    continue
                prop = v.get('property_id')
                if prop and isinstance(prop, list):
                    view_counts[prop[0]] += 1
            offset += batch_size

        # sort by views
        top_ids = sorted(view_counts.items(), key=lambda x: x[1], reverse=True)[:top_n * 2]
        top_property_ids = [pid for pid, _ in top_ids]

        # read properties
        properties = models.execute_kw(
            db, uid, password,
            'property.property', 'read',
            [top_property_ids],
            {'fields': ['reference', 'active']}
        )

        existing_ids = {p['id']: p for p in properties}

        links = []
        for prop_id, count in top_ids:
            prop = existing_ids.get(prop_id)
            if not prop:
                continue
            if 'active' in prop and not prop['active']:
                continue
            ref = prop.get('reference')
            if ref:
                links.append({
                    "ref": ref,
                    "link": f"https://abracasabra-realestate.com/property/?ref_no={ref}",
                    "views": count
                })
            if len(links) >= top_n:
                break

        return links

    except Exception as e:
        print(f"❌ Top viewed properties error: {e}")
        return []


def get_views_grouped_by_month(uid, models, db, password):
    domain = []
    batch_size = 5000
    offset = 0
    month_counts = defaultdict(int)

    try:
        all_ids = models.execute_kw(
            db, uid, password,
            'property.view', 'search',
            [domain],
            {'order': 'date asc'}
        )

        while offset < len(all_ids):
            batch_ids = all_ids[offset:offset + batch_size]
            records = models.execute_kw(
                db, uid, password,
                'property.view', 'read',
                [batch_ids],
                {'fields': ['date', 'user_agent']}
            )
            for v in records:
                if is_bot(v):
                    continue
                date_str = v.get('date')
                if date_str:
                    try:
                        dt = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                        month_key = f"{dt.year}-{dt.month:02d}"
                        month_counts[month_key] += 1
                    except:
                        pass
            offset += batch_size
    except Exception as e:
        print(f"❌ View count error: {e}")

    return month_counts


def get_top_viewed_locations(uid, models, db, password, top_n=25):
    """Aggregate property.view records by location_id and return the top N locations."""
    view_counts_by_location = defaultdict(int)
    batch_size = 5000
    offset = 0

    try:
        all_ids = models.execute_kw(
            db, uid, password,
            'property.view', 'search',
            [[]],
            {'order': 'date desc'}
        )

        while offset < len(all_ids):
            batch_ids = all_ids[offset:offset + batch_size]
            views = models.execute_kw(
                db, uid, password,
                'property.view', 'read',
                [batch_ids],
                {'fields': ['property_id', 'user_agent']}
            )

            property_ids = [v['property_id'][0] for v in views if v.get('property_id')]
            if property_ids:
                properties = models.execute_kw(
                    db, uid, password,
                    'property.property', 'read',
                    [property_ids],
                    {'fields': ['location_id']}
                )
                prop_location_map = {p['id']: p.get('location_id') for p in properties}

                for v in views:
                    if is_bot(v):
                        continue
                    prop = v.get('property_id')
                    if prop and isinstance(prop, list):
                        loc = prop_location_map.get(prop[0])
                        if loc and isinstance(loc, list):
                            view_counts_by_location[loc[0]] += 1

            offset += batch_size

        top_locations = sorted(view_counts_by_location.items(),
                               key=lambda x: x[1], reverse=True)[:top_n]
        top_location_ids = [lid for lid, _ in top_locations]

        locations = models.execute_kw(
            db, uid, password,
            'res.location', 'read',
            [top_location_ids],
            {'fields': ['name']}
        )
        loc_name_map = {loc['id']: loc['name'] for loc in locations}

        result = []
        for lid, views_count in top_locations:
            result.append({
                "location_id": lid,
                "name": loc_name_map.get(lid, "Unknown"),
                "views": views_count
            })
        return result

    except Exception as e:
        print(f"❌ Top viewed locations error: {e}")
        return []


# GeoIP setup
reader = geoip2.database.Reader('GeoLite2-Country.mmdb')

def geolocate_ip(ip):
    try:
        response = reader.country(ip)
        return response.country.name
    except Exception:
        return None


def get_top_countries(uid, models, db, password, top_n=20):
    batch_size = 5000
    offset = 0
    country_counts = defaultdict(int)
    seen_ips = {}

    all_ids = models.execute_kw(
        db, uid, password,
        'property.view', 'search',
        [[]],
        {'order': 'date desc'}
    )

    while offset < len(all_ids):
        batch_ids = all_ids[offset:offset + batch_size]
        views = models.execute_kw(
            db, uid, password,
            'property.view', 'read',
            [batch_ids],
            {'fields': ['ip', 'user_agent']}
        )

        for v in views:
            if is_bot(v):
                continue
            ip = v.get('ip')
            if not ip:
                continue
            if ip in seen_ips:
                country = seen_ips[ip]
            else:
                country = geolocate_ip(ip)
                seen_ips[ip] = country

            if country:
                country_counts[country] += 1

        offset += batch_size

    top_countries = sorted(country_counts.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return [{"country": c, "views": v} for c, v in top_countries]


def get_views_by_price_range(uid, models, db, password):
    """
    Calculate total views for properties grouped by price ranges.
    """
    view_counts = defaultdict(int)
    batch_size = 5000
    offset = 0

    all_ids = models.execute_kw(
        db, uid, password,
        'property.view', 'search',
        [[]],
        {'order': 'date desc'}
    )

    while offset < len(all_ids):
        batch_ids = all_ids[offset:offset + batch_size]
        views = models.execute_kw(
            db, uid, password,
            'property.view', 'read',
            [batch_ids],
            {'fields': ['property_id', 'user_agent']}
        )

        for v in views:
            if is_bot(v):
                continue
            prop = v.get('property_id')
            if prop and isinstance(prop, list):
                view_counts[prop[0]] += 1

        offset += batch_size

    if not view_counts:
        return {}

    property_ids = list(view_counts.keys())
    properties = models.execute_kw(
        db, uid, password,
        'property.property', 'read',
        [property_ids],
        {'fields': ['list_price']}
    )

    bins = [(i * 100000, (i + 1) * 100000) for i in range(0, 50)]  # up to 5M
    price_ranges = {f"{low}-{high}": 0 for (low, high) in bins}

    for prop in properties:
        price = prop.get('list_price') or 0
        views_count = view_counts.get(prop['id'], 0)

        for low, high in bins:
            if low <= price < high:
                key = f"{low}-{high}"
                price_ranges[key] += views_count
                break

    price_ranges = {k: v for k, v in price_ranges.items() if v > 0}

    return price_ranges


def generate_inquiry_stats():
    uid, models, db, password = connect_to_odoo()
    if not uid:
        return

    sources = [
        "Subject: Kyero.com",
        "Subject: Idealista",
        "Subject: Indomio",
        "Subject: AbraCasaBra Form",
        "Subject: thinkSPAIN",
        "Subject: Aplaceinthesun",
        "Subject: Pisos.com"
    ]

    months = get_all_months_this_year()
    results = {}

    # Property views per month
    views_per_month = get_views_grouped_by_month(uid, models, db, password)

    for month in months:
        start_date = datetime.strptime(month, "%Y-%m")
        end_date = (start_date + relativedelta(months=1))
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        source_counts = defaultdict(int)
        matching_partner_ids = set()

        for source in sources:
            message_ids = models.execute_kw(
                db, uid, password,
                'mail.message', 'search',
                [[
                    ['body', 'ilike', source],
                    ['date', '>=', start_str],
                    ['date', '<', end_str],
                    ['model', '=', 'res.partner']
                ]]
            )
            if message_ids:
                messages = models.execute_kw(
                    db, uid, password,
                    'mail.message', 'read',
                    [message_ids],
                    {'fields': ['res_id']}
                )
                for msg in messages:
                    matching_partner_ids.add(msg['res_id'])
                    source_counts[source] += 1

        wishlist_contact_ids = models.execute_kw(
            db, uid, password,
            'res.partner', 'search',
            [[
                ['property_type_ids', '!=', False],
                ['create_date', '>=', start_str],
                ['create_date', '<', end_str]
            ]]
        )

        wishlist_only_ids = set(wishlist_contact_ids) - matching_partner_ids
        referral_source_counts = defaultdict(int)

        if wishlist_only_ids:
            wishlist_contacts = models.execute_kw(
                db, uid, password,
                'res.partner', 'read',
                [list(wishlist_only_ids)],
                {'fields': ['referral_source_id']}
            )
            for contact in wishlist_contacts:
                referral = contact.get('referral_source_id')
                if referral and isinstance(referral, list):
                    source_name = referral[1]
                    referral_source_counts[source_name] += 1
                else:
                    referral_source_counts['(None)'] += 1

        results[month] = {
            "autoimport_total": len(matching_partner_ids),
            "wishlist_total": len(wishlist_only_ids),
            "property_views": views_per_month.get(month, 0),
            "sources": dict(source_counts),
            "referrals": dict(referral_source_counts)
        }

    results["top_viewed_links"] = get_top_viewed_property_links(uid, models, db, password)
    results["top_viewed_locations"] = get_top_viewed_locations(uid, models, db, password)
    results["top_viewer_countries"] = get_top_countries(uid, models, db, password)
    results["views_by_price_range"] = get_views_by_price_range(uid, models, db, password)

    with open("inquiry_stats.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("✅ inquiry_stats.json updated!")


if __name__ == "__main__":
    generate_inquiry_stats()
