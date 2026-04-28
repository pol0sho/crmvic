import xmlrpc.client
import json
import re
from datetime import datetime

# ==============================
# CLEAN TEXT
# ==============================
def clean_text(text):
    if not text:
        return ""
    text = text.replace("\r", "\n")
    text = text.replace("\u2028", "\n")
    text = text.replace("\u2029", "\n")
    text = text.replace("\x00", "")
    text = re.sub(r"[\x01-\x08\x0B-\x1F\x7F]", "", text)
    return text

# ==============================
# CONNECT TO ODOO
# ==============================
def connect_to_odoo():
    url = "https://crm.abracasabra.es"
    db = "crm.abracasabra.es"
    username = "info@abracasabra.es"
    password = "2345nicekid"

    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    uid = common.authenticate(db, username, password, {})
    if not uid:
        raise Exception("Authentication failed")

    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
    return uid, models, db, password

# ==============================
# EXTRACT PROPERTY REFERENCE
# ==============================
def extract_ref(text):
    if not text:
        return None
    match = re.search(r"ref[:\s]*([A-Z0-9]+)", text, re.IGNORECASE)
    return match.group(1) if match else None

# ==============================
# REBUILD BUYERS JSON
# ==============================
def rebuild_buyers_json():
    uid, models, db, password = connect_to_odoo()

    # Step 1: fetch all mail messages for partners
    message_ids = models.execute_kw(
        db, uid, password,
        'mail.message', 'search',
        [[
            ['model', '=', 'res.partner'],
            ['message_type', '=', 'comment'],
            ['date', '>=', '2025-01-01']
        ]]
    )

    messages = models.execute_kw(
        db, uid, password,
        'mail.message', 'read',
        [message_ids],
        {'fields': ['res_id', 'date', 'body']}
    )

    print(f"Total messages fetched: {len(messages)}")

    # Step 2: extract refs and build list
    data = []
    refs = set()
    for m in messages:
        ref = extract_ref(m.get("body", ""))
        if ref:
            refs.add(ref)
        data.append({
            "partner_id": m.get("res_id"),
            "ref": ref,
            "inquiry_date": m.get("date")
        })

    # Step 3: get property prices for refs
    if refs:
        properties = models.execute_kw(
            db, uid, password,
            'property.property', 'search_read',
            [[['reference', 'in', list(refs)]]],
            {'fields': ['reference', 'list_price']}
        )
        price_map = {p['reference']: p.get('list_price', 0) for p in properties}
    else:
        price_map = {}

    # Step 4: build final JSON
    final_data = []
    for item in data:
        ref = item.get("ref")
        max_price = price_map.get(ref, 0)
        final_data.append({
            "email": "",   # optional
            "phone": "",
            "mobile": "",
            "nationality": "Unknown",
            "max_price": max_price,
            "log_note": "",
            "inquiry_date": item.get("inquiry_date")
        })

    output = {
        "summary": {"total_buyers": len(final_data)},
        "data": final_data
    }

    filename = f"buyers_rebuilt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"✅ Buyers JSON rebuilt: {filename}")

# ==============================
# RUN
# ==============================
if __name__ == "__main__":
    rebuild_buyers_json()