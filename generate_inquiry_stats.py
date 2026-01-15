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


def get_months_from_jan_2025():
    start = datetime(2025, 1, 1)
    now = datetime.now()

    months = []
    cur = start
    while cur <= now:
        months.append(f"{cur.year}-{cur.month:02d}")
        cur += relativedelta(months=1)

    return months


def is_bot(view):
    """Return True if user_agent indicates a bot."""
    ua = (view.get('user_agent') or '').lower()
    return any(bot in ua for bot in ['gptbot', 'claudebot', 'spider'])

def paged_search(models, db, uid, password, model, domain, order="date desc", batch_size=5000):
    """
    Safe generator for large Odoo tables.
    Prevents XML-RPC IncompleteRead by paginating search().
    """
    offset = 0
    while True:
        ids = models.execute_kw(
            db, uid, password,
            model, 'search',
            [domain],
            {'limit': batch_size, 'offset': offset, 'order': order}
        )
        if not ids:
            break
        yield ids
        offset += batch_size


# ====================
# STATS FUNCTIONS
# ====================

def get_top_viewed_property_links(uid, models, db, password, top_n=20):
    view_counts = defaultdict(int)
    batch_size = 5000

    try:
        for batch_ids in paged_search(
            models, db, uid, password,
            'property.view',
            [['date', '>=', '2025-01-01']]
        ):
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

        top_ids = sorted(view_counts.items(), key=lambda x: x[1], reverse=True)[:top_n * 2]
        top_property_ids = [pid for pid, _ in top_ids]

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
            if not prop or not prop.get('active', True):
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
    month_counts = defaultdict(int)

    try:
        for batch_ids in paged_search(
            models, db, uid, password,
            'property.view',
            [['date', '>=', '2025-01-01']],
            order="date asc"
        ):
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
                        month_counts[f"{dt.year}-{dt.month:02d}"] += 1
                    except:
                        pass

    except Exception as e:
        print(f"❌ View count error: {e}")

    return month_counts


def get_top_viewed_locations(uid, models, db, password, top_n=25):
    view_counts_by_location = defaultdict(int)

    try:
        for batch_ids in paged_search(
            models, db, uid, password,
            'property.view',
            [['date', '>=', '2025-01-01']]
        ):
            views = models.execute_kw(
                db, uid, password,
                'property.view', 'read',
                [batch_ids],
                {'fields': ['property_id', 'user_agent']}
            )

            property_ids = [v['property_id'][0] for v in views if v.get('property_id')]
            if not property_ids:
                continue

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

        top_locations = sorted(view_counts_by_location.items(), key=lambda x: x[1], reverse=True)[:top_n]
        location_ids = [lid for lid, _ in top_locations]

        locations = models.execute_kw(
            db, uid, password,
            'res.location', 'read',
            [location_ids],
            {'fields': ['name']}
        )
        name_map = {l['id']: l['name'] for l in locations}

        return [{
            "location_id": lid,
            "name": name_map.get(lid, "Unknown"),
            "views": views
        } for lid, views in top_locations]

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
    country_counts = defaultdict(int)
    seen_ips = {}

    for batch_ids in paged_search(
        models, db, uid, password,
        'property.view',
        [['date', '>=', '2025-01-01']]
    ):
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

            if ip not in seen_ips:
                seen_ips[ip] = geolocate_ip(ip)

            if seen_ips[ip]:
                country_counts[seen_ips[ip]] += 1

    return sorted(
        [{"country": c, "views": v} for c, v in country_counts.items()],
        key=lambda x: x["views"],
        reverse=True
    )[:top_n]


def get_views_by_price_range(uid, models, db, password):
    view_counts = defaultdict(int)

    for batch_ids in paged_search(
        models, db, uid, password,
        'property.view',
        [['date', '>=', '2025-01-01']]
    ):
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

    if not view_counts:
        return {}

    properties = models.execute_kw(
        db, uid, password,
        'property.property', 'read',
        [list(view_counts.keys())],
        {'fields': ['list_price']}
    )

    bins = [(i * 100000, (i + 1) * 100000) for i in range(50)]
    price_ranges = defaultdict(int)

    for p in properties:
        price = p.get('list_price') or 0
        for low, high in bins:
            if low <= price < high:
                price_ranges[f"{low}-{high}"] += view_counts[p['id']]
                break

    return dict(price_ranges)

def get_views_by_price_and_nationality(uid, models, db, password):
    view_data = []

    for batch_ids in paged_search(
        models, db, uid, password,
        'property.view',
        [['date', '>=', '2025-01-01']]
    ):
        views = models.execute_kw(
            db, uid, password,
            'property.view', 'read',
            [batch_ids],
            {'fields': ['property_id', 'ip', 'user_agent']}
        )

        for v in views:
            if is_bot(v):
                continue
            prop = v.get('property_id')
            ip = v.get('ip')
            if prop and isinstance(prop, list) and ip:
                view_data.append((prop[0], ip))

    if not view_data:
        return {}

    properties = models.execute_kw(
        db, uid, password,
        'property.property', 'read',
        [list({pid for pid, _ in view_data})],
        {'fields': ['list_price']}
    )
    price_map = {p['id']: p.get('list_price') or 0 for p in properties}

    bins = [(i * 100000, (i + 1) * 100000) for i in range(50)]

    def price_bucket(price):
        for low, high in bins:
            if low <= price < high:
                return f"{low}-{high}"
        return "5000000+"

    ip_cache = {}
    results = defaultdict(lambda: defaultdict(int))

    for pid, ip in view_data:
        if ip not in ip_cache:
            ip_cache[ip] = geolocate_ip(ip) or "Unknown"
        results[ip_cache[ip]][price_bucket(price_map.get(pid, 0))] += 1

    return {k: dict(v) for k, v in results.items()}



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

    months = get_months_from_jan_2025()
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
    results["views_by_price_and_nationality"] = get_views_by_price_and_nationality(uid, models, db, password)


    with open("inquiry_stats.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("✅ inquiry_stats.json updated!")


if __name__ == "__main__":
    generate_inquiry_stats()
