import psycopg2

DB_URL = (
    "postgresql://inmosuite_user:GlNtF89gavaJzBX3Vv3jGyzPe3vdOwGM"
    "@dpg-d1smp82li9vc73c8hsr0-a.frankfurt-postgres.render.com:5432/inmosuite"
    "?sslmode=require"
)

CLIENT_ID = 2


def test_cascade_delete():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    try:
        print("🧪 Deleting contacts for client_id = 2 (contacts ONLY)...")

        cur.execute(
            """
            DELETE FROM contacts
            WHERE client_id = %s
            """,
            (CLIENT_ID,)
        )

        deleted = cur.rowcount
        conn.commit()

        print(f"✅ Deleted {deleted} contacts")
        print("➡️  Now check contact_internal_notes table to confirm cascade")

    except Exception as e:
        conn.rollback()
        print("❌ Delete failed (likely FK without CASCADE)")
        raise e

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    test_cascade_delete()