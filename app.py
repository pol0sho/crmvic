from flask import Flask, request, jsonify, send_from_directory
import psycopg
import os
from functools import lru_cache

app = Flask(__name__, static_url_path='', static_folder='.')

# === DB Connection ===
def get_db():
    return psycopg.connect(
        dbname="inmosuite",
        user="inmosuite_user",
        password="GlNtF89gavaJzBX3Vv3jGyzPe3vdOwGM",
        host="dpg-d1smp82li9vc73c8hsr0-a.frankfurt-postgres.render.com",
        port="5432",
        sslmode="require",
        row_factory=psycopg.rows.dict_row
    )

# === Serve Frontend Files ===
@app.route("/")
def serve_index():
    return send_from_directory(".", "index.html")

@app.route("/<path:path>")
def serve_static(path):
    return send_from_directory(".", path)

# === Cached Fetch Function ===
@lru_cache(maxsize=128)  # Cache up to 128 unique (feed, page, per_page) combinations
def get_properties_cached(feed, page, per_page):
    offset = (page - 1) * per_page

    if feed == "resales":
        table = "resales_properties"
        image_table = "resales_property_images"
        image_column = "image_url"
        image_join_column = "p.ref"
        image_compare_column = "CAST(i.property_id AS TEXT)"
    elif feed == "kyero":
        table = "kyero_properties"
        image_table = "kyero_property_images"
        image_column = "url"
        image_join_column = "p.id"
        image_compare_column = "i.property_id"
    else:
        table = "propmls_properties"
        image_table = "propmls_property_images"
        image_column = "url"
        image_join_column = "p.id"
        image_compare_column = "i.property_id"

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT p.ref, p.price, p.beds, p.baths, p.town, img.{image_column} AS cover_image
                FROM {table} p
                LEFT JOIN LATERAL (
                    SELECT {image_column}
                    FROM {image_table} i
                    WHERE {image_compare_column} = {image_join_column}
                    AND image_order = 1
                    LIMIT 1
                ) img ON true
                ORDER BY p.ref DESC
                LIMIT %s OFFSET %s
            """, (per_page + 1, offset))

            rows = cur.fetchall()
            has_next = len(rows) > per_page
            return rows[:per_page], has_next
        
@app.route("/api/search")
def search_across_feeds():
    ref = request.args.get("ref")
    if not ref:
        return jsonify([])

    feeds = {
        "resales": ("resales_properties", "resales_property_images"),
        "kyero": ("kyero_properties", "kyero_property_images"),
        "propmls": ("propmls_properties", "propmls_property_images")
    }

    results = []

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                for feed, (prop_table, img_table) in feeds.items():
                    print(f"🔍 Searching {feed} for ref {ref}...")

                    cur.execute(f"""
                        SELECT p.ref, p.price, p.beds, p.baths, p.town,
                            img.image_url AS cover_image
                        FROM {prop_table} p
                        LEFT JOIN LATERAL (
                            SELECT image_url
                            FROM {img_table} i
                            WHERE i.property_id = p.ref AND image_order = 1
                            LIMIT 1
                        ) img ON true
                        WHERE LOWER(p.ref) = LOWER(%s)
                        LIMIT 1
                    """, (ref,))

                    row = cur.fetchone()
                    print(f"➡️ Result from {feed}:", row)

                    if row:
                        results.append({
                            "feed": feed,
                            "property": {
                                "ref": row["ref"],
                                "price": row["price"],
                                "beds": row["beds"],
                                "baths": row["baths"],
                                "town": row["town"],
                                "cover_image": row["cover_image"]
                            }
                        })

    except Exception as e:
        print("❌ Search error:", str(e))
        return jsonify({"error": "Search failed", "details": str(e)}), 500

    return jsonify(results)

# === API Endpoint ===
@app.route('/api/properties')
def get_properties():
    feed = request.args.get('feed', 'resales')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 18))

    properties, has_next = get_properties_cached(feed, page, per_page)
    return jsonify({
        "properties": properties,
        "has_next": has_next
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
