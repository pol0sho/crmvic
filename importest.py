import json
import psycopg2
from psycopg2.extras import RealDictCursor

# ==============================
# CONFIG
# ==============================
DB_URL = (
    "postgresql://inmosuite_user:GlNtF89gavaJzBX3Vv3jGyzPe3vdOwGM"
    "@dpg-d1smp82li9vc73c8hsr0-a.frankfurt-postgres.render.com:5432/inmosuite"
    "?sslmode=require"
)

JSON_FILE = "contacts_export_20260103_190709.json"
CLIENT_ID = 2

# ==============================
# AUTHOR NAME → USER ID MAP
# ==============================
AUTHOR_ID_MAP = {
    "Victor Kok": 16,
    "Ana Moreno": 48,
    "Stijn Vleminckx": 47,
    "Nathalie De Vos": 49,
    "An Wilssens": 52,
    "Sarah Van Haelst": 46,
    "Nathalie Stigter": 45,
    "Wendy Loockx": 44,
    "Christian De Schrijver - AbraCasaBra Real Estate": 28,
    "Olivier Dykmans": 29,
    "Marco Vlaskamp - AbraCasaBra Real Estate": 40,
    "Milan Van Den Branden": 39,
    "Philippe Van Den Branden": 38,
    "Frank Verhaeghe": 42,
}


def get_db():
    return psycopg2.connect(DB_URL)


# ==============================
# WIPE EXISTING CLIENT DATA
# ==============================
def wipe_client_contacts(cur):
    print("🧹 Deleting existing contacts for client_id = 2...")

    cur.execute(
        """
        DELETE FROM contact_internal_notes
        WHERE contact_id IN (
            SELECT id FROM contacts WHERE client_id = %s
        )
        """,
        (CLIENT_ID,),
    )

    cur.execute(
        """
        DELETE FROM imported_leads
        WHERE contact_id IN (
            SELECT id FROM contacts WHERE client_id = %s
        )
        """,
        (CLIENT_ID,),
    )

    cur.execute(
        """
        DELETE FROM contacts
        WHERE client_id = %s
        """,
        (CLIENT_ID,),
    )

    print("✅ Old contacts, leads, and notes removed")


# ==============================
# INSERT CONTACT
# ==============================
def insert_contact(cur, contact, phone_value):
    cur.execute(
        """
        INSERT INTO contacts (
            name,
            email,
            phone,
            role,
            client_id,
            subscribed,
            created_at
        )
        VALUES (%s, %s, %s, %s, %s, true, NOW())
        RETURNING id
        """,
        (
            contact.get("name"),
            contact.get("email"),
            phone_value,
            contact.get("type", "").lower(),
            CLIENT_ID,
        ),
    )
    return cur.fetchone()["id"]


# ==============================
# INSERT INTERNAL NOTE (WITH AUTHOR MAPPING)
# ==============================
def insert_internal_note(cur, contact_id, note):
    author_name = note.get("author")
    author_id = None

    if author_name:
        author_name = author_name.strip()
        author_id = AUTHOR_ID_MAP.get(author_name)

        if author_id is None:
            print(f"⚠️  Unmapped author: {author_name}")

    cur.execute(
        """
        INSERT INTO contact_internal_notes (
            contact_id,
            title,
            content,
            category,
            priority,
            author_id,
            author_name,
            tags,
            created_at,
            updated_at,
            author_avatar
        )
        VALUES (
            %s,
            '',
            %s,
            'general',
            'medium',
            %s,
            %s,
            NULL,
            %s,
            %s,
            NULL
        )
        """,
        (
            contact_id,
            note.get("body"),
            author_id,        # mapped author_id
            author_name,      # always store name
            note.get("date"),
            note.get("date"),
        ),
    )


# ==============================
# MAIN IMPORT
# ==============================
def import_contacts():
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        contacts = json.load(f)

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    seen_phones = set()
    nulled_phones = 0

    try:
        wipe_client_contacts(cur)

        inserted_contacts = 0
        inserted_notes = 0

        for contact in contacts:
            if not contact.get("email"):
                continue

            phone = contact.get("phone")
            phone_to_insert = phone

            if phone:
                if phone in seen_phones:
                    phone_to_insert = None
                    nulled_phones += 1
                else:
                    seen_phones.add(phone)

            contact_id = insert_contact(cur, contact, phone_to_insert)
            inserted_contacts += 1

            for note in contact.get("log_notes", []):
                insert_internal_note(cur, contact_id, note)
                inserted_notes += 1

        conn.commit()

        print("🎉 Import completed successfully")
        print(f"   Contacts imported: {inserted_contacts}")
        print(f"   Notes imported:    {inserted_notes}")
        print(f"   Phones nulled (duplicates): {nulled_phones}")

    except Exception as e:
        conn.rollback()
        print("❌ Import failed, rolled back")
        raise e

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    import_contacts()
