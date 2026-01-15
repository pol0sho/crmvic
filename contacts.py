import xmlrpc.client
import json
import re
from datetime import datetime


# ==============================
# TEXT CLEANING
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
# ODOO CONNECTION
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
# PARTNER TYPE FROM individual_type
# ==============================
def map_individual_type(individual_type):
    if individual_type == "is_buyer":
        return "Buyer"
    if individual_type == "is_seller":
        return "Seller"
    if individual_type == "is_professional":
        return "Professional"
    return None


# ==============================
# EXPORT CONTACTS
# ==============================
def export_contacts_to_json():
    uid, models, db, password = connect_to_odoo()

    # Only contacts that actually have a role
    contact_ids = models.execute_kw(
        db, uid, password,
        'res.partner', 'search',
        [[
            ['email', 'not ilike', 'autofilled%'],
            ['individual_type', 'in', ['is_buyer', 'is_seller', 'is_professional']]
        ]]
    )

    print(f"Total contacts before dedupe: {len(contact_ids)}")

    filename = f"contacts_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    batch_size = 1000
    offset = 0
    selected_contacts = {}

    # Stats counter
    type_counts = {
        "Buyer": 0,
        "Seller": 0,
        "Professional": 0
    }

    # ==============================
    # STEP 1 — LOAD + DEDUPE
    # ==============================
    while offset < len(contact_ids):
        batch_ids = contact_ids[offset:offset + batch_size]

        contacts = models.execute_kw(
            db, uid, password,
            'res.partner', 'read',
            [batch_ids],
            {
                'fields': [
                    'name',
                    'email',
                    'phone',
                    'individual_type'
                ]
            }
        )

        for c in contacts:
            name = (c.get("name") or "").strip()
            email = (c.get("email") or "").strip()
            phone = (c.get("phone") or "").strip()

            if not name or not email:
                continue

            partner_type = map_individual_type(c.get("individual_type"))
            if not partner_type:
                continue

            email_key = email.lower()

            record = {
                "id": c["id"],
                "name": name,
                "email": email,
                "phone": phone,
                "type": partner_type
            }

            if email_key not in selected_contacts:
                selected_contacts[email_key] = record
                type_counts[partner_type] += 1
            else:
                # Prefer record with phone
                current = selected_contacts[email_key]
                if phone and not current.get("phone"):
                    selected_contacts[email_key] = record

        offset += batch_size

    final_list = list(selected_contacts.values())

    print("Deduplicated contacts by type:")
    for k, v in type_counts.items():
        print(f"  {k}: {v}")

    print(f"Total exported contacts: {len(final_list)}")

    # ==============================
    # STEP 2 — FETCH LOG NOTES
    # ==============================
    print("Fetching log notes for all contacts...")

    for contact in final_list:
        partner_id = contact["id"]

        message_ids = models.execute_kw(
            db, uid, password,
            'mail.message', 'search',
            [[
                ['model', '=', 'res.partner'],
                ['res_id', '=', partner_id],
                ['message_type', '=', 'comment']
            ]]
        )

        if not message_ids:
            contact["log_notes"] = []
            continue

        messages = models.execute_kw(
            db, uid, password,
            'mail.message', 'read',
            [message_ids],
            {'fields': ['date', 'body', 'author_id']}
        )

        logs = []
        for m in messages:
            author_name = ""
            author = m.get("author_id")
            if author and isinstance(author, list):
                author_name = author[1]

            logs.append({
                "date": m.get("date"),
                "author": author_name,
                "body": clean_text(m.get("body") or "")
            })

        contact["log_notes"] = logs

    # ==============================
    # REMOVE INTERNAL IDS
    # ==============================
    for c in final_list:
        c.pop("id", None)

    # ==============================
    # SAVE FILE
    # ==============================
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(final_list, f, indent=2, ensure_ascii=False)

    print("✅ Export completed")
    print(f"✅ JSON file created: {filename}")


# ==============================
# RUN
# ==============================
if __name__ == "__main__":
    export_contacts_to_json()
