import xmlrpc.client
from collections import defaultdict
from datetime import datetime
from dateutil.relativedelta import relativedelta
import json

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


def get_top_viewed_property_links(uid, models, db, password, top_n=20):
    """
    Get the most viewed properties of all time, ensuring that only existing and active properties are included.
    """
    view_counts = defaultdict(int)
    batch_size = 5000
    offset = 0

    try:
        # Get all property.view records
        all_ids = models.execute_kw(
            db, uid, password,
            'property.view', 'search',
            [[]],
            {'order': 'date desc'}
        )

        # Count views per property
        while offset < len(all_ids):
            batch_ids = all_ids[offset:offset + batch_size]
            records = models.execute_kw(
                db, uid, password,
                'property.view', 'read',
                [batch_ids],
                {'fields': ['property_id']}
            )
            for view in records:
                prop = view.get('property_id')
                if prop and isinstance(prop, list):
                    view_counts[prop[0]] += 1
            offset += batch_size

        # Sort by views
        top_ids = sorted(view_counts.items(), key=lambda x: x[1], reverse=True)[:top_n * 2]  # extra buffer
        top_property_ids = [pid for pid, _ in top_ids]

        # Read properties – only existing ones will be returned
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
                continue  # skip missing property
            # If active field exists and is False, skip it
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
                break  # limit results to top_n

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
                {'fields': ['date']}
            )
            for view in records:
                date_str = view.get('date')
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
        # Get all property.view IDs
        all_ids = models.execute_kw(
            db, uid, password,
            'property.view', 'search',
            [[]],
            {'order': 'date desc'}
        )

        # Process in batches
        while offset < len(all_ids):
            batch_ids = all_ids[offset:offset + batch_size]
            views = models.execute_kw(
                db, uid, password,
                'property.view', 'read',
                [batch_ids],
                {'fields': ['property_id']}
            )

            # Collect property IDs in this batch
            property_ids = [v['property_id'][0] for v in views if v.get('property_id')]
            if property_ids:
                # Read location_id for these properties
                properties = models.execute_kw(
                    db, uid, password,
                    'property.property', 'read',
                    [property_ids],
                    {'fields': ['location_id']}
                )
                prop_location_map = {p['id']: p.get('location_id') for p in properties}

                # Increment counters
                for v in views:
                    prop = v.get('property_id')
                    if prop and isinstance(prop, list):
                        loc = prop_location_map.get(prop[0])
                        if loc and isinstance(loc, list):
                            view_counts_by_location[loc[0]] += 1

            offset += batch_size

        # Sort by total views
        top_locations = sorted(view_counts_by_location.items(),
                               key=lambda x: x[1], reverse=True)[:top_n]
        top_location_ids = [lid for lid, _ in top_locations]

        # Get location names
        locations = models.execute_kw(
            db, uid, password,
            'res.location', 'read',  # replace with the correct model name if different
            [top_location_ids],
            {'fields': ['name']}
        )
        loc_name_map = {loc['id']: loc['name'] for loc in locations}

        result = []
        for lid, views in top_locations:
            result.append({
                "location_id": lid,
                "name": loc_name_map.get(lid, "Unknown"),
                "views": views
            })
        return result

    except Exception as e:
        print(f"❌ Top viewed locations error: {e}")
        return []

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

    # 🔁 Add property views
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



    top_links = get_top_viewed_property_links(uid, models, db, password)
    results["top_viewed_links"] = top_links

    top_locations = get_top_viewed_locations(uid, models, db, password)

    results["top_viewed_locations"] = top_locations

    with open("inquiry_stats.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("✅ inquiry_stats.json updated!")

if __name__ == "__main__":
    generate_inquiry_stats()
