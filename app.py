from flask import Flask, request, jsonify, send_from_directory
import psycopg
import os

app = Flask(__name__, static_url_path='', static_folder='.')

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

@app.route("/")
def serve_index():
    return send_from_directory(".", "index.html")

@app.route("/<path:path>")
def serve_static(path):
    return send_from_directory(".", path)

@app.route('/api/properties')
def get_properties():
    feed = request.args.get('feed')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 18))  # 👈 Dynamic per_page
    offset = (page - 1) * per_page
    next_offset = page * per_page

    if feed == "resales":
        table = "resales_properties"
        image_table = "resales_property_images"
        image_column = "image_url"
        image_join_column = "p.ref"
        image_compare_column = "CAST(i.property_id AS TEXT)"
    else:
        if feed == "kyero":
            table = "kyero_properties"
            image_table = "kyero_property_images"
        else:
            table = "propmls_properties"
            image_table = "propmls_property_images"
        image_column = "url"
        image_join_column = "p.id"
        image_compare_column = "i.property_id"

    def fetch_batch(start_offset):
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT p.ref, p.price, p.beds, p.baths, p.town,
                        (SELECT {image_column} FROM {image_table} i 
                         WHERE {image_compare_column} = {image_join_column}
                         AND image_order = 1
                         LIMIT 1) AS cover_image
                    FROM {table} p
                    ORDER BY ref DESC
                    LIMIT %s OFFSET %s
                """, (per_page, start_offset))
                return cur.fetchall()

    current_page = fetch_batch(offset)
    next_page = fetch_batch(next_offset)

    return jsonify({
        "properties": current_page,
        "next": next_page
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)