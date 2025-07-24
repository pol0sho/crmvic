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
                {'fields': ['property_id']}
            )
            for view in records:
                prop = view.get('property_id')
                if prop and isinstance(prop, list):
                    view_counts[prop[0]] += 1
            offset += batch_size

        # Get top N property IDs
        top_ids = sorted(view_counts.items(), key=lambda x: x[1], reverse=True)[:top_n]
        top_property_ids = [pid for pid, _ in top_ids]

        # Fetch property refs
        properties = models.execute_kw(
            db, uid, password,
            'estate.property', 'read',
            [top_property_ids],
            {'fields': ['ref']}
        )

        links = []
        for prop in properties:
            ref = prop.get('ref')
            if ref:
                links.append({
                    "ref": ref,
                    "link": f"https://abracasabra-realestate.com/property/?ref_no={ref}",
                    "views": view_counts[prop['id']]
                })

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

    with open("inquiry_stats.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("✅ inquiry_stats.json updated!")

if __name__ == "__main__":
    generate_inquiry_stats()
