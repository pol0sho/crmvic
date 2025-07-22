from flask import Flask, request, jsonify, send_from_directory
import psycopg2
import os

app = Flask(__name__, static_url_path='', static_folder='.')

def get_db():
    return psycopg2.connect(
        dbname="inmosuite",
        user="inmosuite_user",
        password="GlNtF89gavaJzBX3Vv3jGyzPe3vdOwGM",  # Use env var in prod!
        host="dpg-d1smp82li9vc73c8hsr0-a.frankfurt-postgres.render.com",
        port="5432",
        sslmode="require"
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
    per_page = 18
    offset = (page - 1) * per_page

    if feed == "resales":
        table = "resales_properties"
        image_table = "resales_property_images"
    elif feed == "kyero":
        table = "kyero_properties"
        image_table = "kyero_property_images"
    else:
        table = "propmls_properties"
        image_table = "propmls_property_images"

    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT p.ref, p.price, p.beds, p.baths, p.town,
               (SELECT image_url FROM {image_table} i 
                WHERE i.property_id = p.ref AND image_order = 1
                LIMIT 1) AS cover_image
        FROM {table} p
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    """, (per_page, offset))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify({
        "properties": [
            {
                "ref": r[0],
                "price": r[1],
                "beds": r[2],
                "baths": r[3],
                "town": r[4],
                "cover_image": r[5]
            }
            for r in rows
        ]
    })

if __name__ == "__main__":
    app.run(debug=True)