from flask import Flask, request, jsonify, send_from_directory, render_template_string
import psycopg
import os
from datetime import datetime
from functools import lru_cache
from flask import request, Response


app = Flask(__name__, static_folder='.', static_url_path='')


def check_auth(username, password):
    return username == "pol0sho" and password == "pol0sho"

def authenticate():
    return Response(
        'Access Denied', 401,
        {'WWW-Authenticate': 'Basic realm="Restricted Area"'}
    )

def require_auth():
    auth = request.authorization
    if not auth or not check_auth(auth.username, auth.password):
        return authenticate()

@app.route('/')
@app.route('/dashboard')
@app.route('/properties')
@app.route('/contacts')
def index():
    auth_result = require_auth()
    if auth_result:
        return auth_result
    return send_from_directory('.', 'index.html')

# ✅ Catch-all route for unknown paths (optional but helpful)
@app.errorhandler(404)
def not_found(e):
    return send_from_directory('.', 'index.html')

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
        
@app.route("/api/contacts")
def get_contacts():
    try:
        role_filter = request.args.get("role")
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 100))
        offset = (page - 1) * per_page

        query = "SELECT id, name, email, phone, mobile, role FROM contacts"
        params = []

        if role_filter:
            query += " WHERE role = %s"
            params.append(role_filter)

        query += " ORDER BY id DESC LIMIT %s OFFSET %s"
        params += [per_page, offset]

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(params))
                rows = cur.fetchall()

        contacts = [{
            "id": r["id"],
            "name": r["name"],
            "email": r["email"],
            "phone": r["phone"],
            "mobile": r["mobile"],
            "roles": [r["role"]] if r["role"] else []
        } for r in rows]

        return jsonify(contacts=contacts)

    except Exception as e:
        return jsonify(error=str(e)), 500

        
@app.route("/api/contacts/<int:contact_id>", methods=["DELETE"])
def delete_contact(contact_id):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM contacts WHERE id = %s", (contact_id,))
                conn.commit()
        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500
        
@app.route("/api/search")
def search_across_feeds():
    ref = request.args.get("ref")
    if not ref:
        return jsonify([])

    # feed: (property_table, image_table, image_column, image_join_column, image_compare_column)
    feeds = {
        "resales": ("resales_properties", "resales_property_images", "image_url", "p.ref", "CAST(i.property_id AS TEXT)"),
        "kyero": ("kyero_properties", "kyero_property_images", "url", "p.id", "i.property_id"),
        "propmls": ("propmls_properties", "propmls_property_images", "url", "p.id", "i.property_id")
    }

    results = []

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                for feed, (prop_table, img_table, img_col, join_left, join_right) in feeds.items():
                    print(f"🔍 Searching {feed} for ref {ref}...")

                    cur.execute(f"""
                        SELECT p.ref, p.price, p.beds, p.baths, p.town,
                               img.{img_col} AS cover_image
                        FROM {prop_table} p
                        LEFT JOIN LATERAL (
                            SELECT {img_col}
                            FROM {img_table} i
                            WHERE {join_right} = {join_left}
                              AND image_order = 1
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

# === 📈 API for Inquiry Stats ===
@app.route("/api/inquiries")
def get_inquiries():
    try:
        with open("inquiry_stats.json", "r", encoding="utf-8") as f:
            data = f.read()
            return app.response_class(data, mimetype="application/json")
    except FileNotFoundError:
        return jsonify(error="inquiry_stats.json not found"), 404

# === 📊 Dashboard HTML Page ===
@app.route("/dashboard/inquiries")
def inquiries_dashboard():
    html = """
    <!DOCTYPE html>
    <html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>AI Inquiry Statistics</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=JetBrains+Mono&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2"></script>
  <script>Chart.register(ChartDataLabels);</script>
  <style>
    :root {
      --bg-dark: #0e0e12;
      --card-dark: #1c1c22;
      --text-main: #f1f1f1;
      --text-secondary: #7f8c8d;
      --highlight: #00f0ff;
      --accent: #f72585;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      padding: 2rem;
      font-family: 'Inter', sans-serif;
      background-color: var(--bg-dark);
      color: var(--text-main);
    }

    html, body {
  max-height: 100vh;
  overflow-y: auto;
  overflow-x: hidden;
}
    h2, h3 {
      text-align: center;
      font-weight: 600;
      letter-spacing: 0.05em;
    }

    h2 {
      font-size: 2rem;
      color: var(--highlight);
      text-shadow: 0 0 8px var(--highlight);
    }

    h3 {
      margin-top: 3rem;
      color: var(--accent);
    }

canvas {
  width: 100%;
  max-width: 1400px;
  height: auto;
  max-height: 60vh; /* ✅ constrain vertical growth */
  aspect-ratio: 3 / 1;
  display: block;
  margin: 2rem auto;
  background-color: var(--card-dark);
  border-radius: 12px;
  padding: 1rem;
  box-shadow: 0 0 30px rgba(0, 240, 255, 0.08);
}

    table {
      border-collapse: collapse;
      width: 100%;
      max-width: 1400px;
      margin: 2rem auto;
      font-family: 'JetBrains Mono', monospace;
      background-color: var(--card-dark);
      color: var(--text-main);
      border-radius: 8px;
      overflow: hidden;
    }

    th, td {
      padding: 10px 16px;
      text-align: center;
      border-bottom: 1px solid rgba(255,255,255,0.05);
    }

    th {
      background-color: #222;
      color: var(--highlight);
      text-transform: uppercase;
      font-size: 0.9rem;
    }

    tr:nth-child(even) {
      background-color: rgba(255,255,255,0.03);
    }

    tr:hover {
      background-color: rgba(255,255,255,0.05);
    }

    @media (max-width: 768px) {
      body {
        padding: 1rem;
      }

      canvas {
        aspect-ratio: 2 / 1;
      }

      table, thead, tbody, th, td, tr {
        font-size: 0.85rem;
      }
    }
  </style>
</head>
    <body>
      <h2>Inquiry Statistics - {{ year }}</h2>
    <h3 style="text-align:center; margin-top:3rem;"> Auto import leads</h3>
      <canvas id="inquiryChart"></canvas>
      <h3 style="text-align:center; margin-top:3rem;"> Monthly Breakdown</h3>
<div id="sourceTable" style="overflow-x:auto; max-width: 1400px; margin: 2rem auto; font-family: monospace;"></div>
    <h3 style="text-align:center; margin-top:3rem;"> Average property views Abracasabra.es</h3>


<script>
  fetch('/api/inquiries')
    .then(res => {
      if (!res.ok) throw new Error("API call failed");
      return res.json();
    })
    .then(data => {
      const year = new Date().getFullYear();
      const months = [...Array(12).keys()].map(i => `${year}-${String(i + 1).padStart(2, '0')}`);

      const autoimport = [];
      const wishlist = [];
      const bgAuto = [];
      const bgWish = [];

      let tableHtml = "<table style='border-collapse:collapse; width:100%;'>";
tableHtml += "<thead><tr><th style='text-align:left;'>Month</th><th>Autoimport</th><th>Wishlist</th>";

const sourceSet = new Set();

// First pass: collect all sources
for (const month of months) {
  if (data[month]) {
    Object.keys(data[month].sources || {}).forEach(source => sourceSet.add(source));
  }
}
const sources = Array.from(sourceSet);
sources.forEach(source => {
  tableHtml += `<th>${source.replace("Subject: ", "")}</th>`;
});
tableHtml += "</tr></thead><tbody>";

// Second pass: build rows
months.forEach(month => {
  const entry = data[month];
  tableHtml += `<tr><td>${month}</td>`;
  if (entry) {
    tableHtml += `<td style='text-align:center;'>${entry.autoimport_total}</td>`;
    tableHtml += `<td style='text-align:center;'>${entry.wishlist_total}</td>`;
    sources.forEach(source => {
      const val = entry.sources?.[source] || 0;
      tableHtml += `<td style='text-align:center;'>${val}</td>`;
    });
  } else {
    tableHtml += `<td colspan="${2 + sources.length}" style='text-align:center; color:#aaa;'>No data</td>`;
  }
  tableHtml += "</tr>";
});

tableHtml += "</tbody></table>";
document.getElementById("sourceTable").innerHTML = tableHtml;

      months.forEach(month => {
        if (data[month]) {
          autoimport.push(data[month].autoimport_total);
          wishlist.push(data[month].wishlist_total);
          bgAuto.push('rgba(54, 162, 235, 0.6)');
          bgWish.push('rgba(255, 99, 132, 0.6)');
        } else {
          autoimport.push(0);
          wishlist.push(0);
          bgAuto.push('rgba(200, 200, 200, 0.3)');
          bgWish.push('rgba(180, 180, 180, 0.3)');
        }
      });

      new Chart(document.getElementById('inquiryChart'), {
        type: 'bar',
        data: {
          labels: months,
          datasets: [
            {
              label: 'Autoimport Contacts',
              data: autoimport,
              backgroundColor: bgAuto
            },
            {
              label: 'Wishlist Only',
              data: wishlist,
              backgroundColor: bgWish
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: { duration: 1000 },
          plugins: {
            legend: { position: 'top' },
            tooltip: {
              callbacks: {
                label: ctx => `${ctx.dataset.label}: ${ctx.raw}`
              }
            },
            // 🔢 Add values on top of bars
            datalabels: {
              anchor: 'end',
              align: 'end',
              color: '#333',
              font: { weight: 'bold' },
              formatter: value => value > 0 ? value : ''
            }
          },
          scales: {
            y: {
              beginAtZero: true,
              ticks: { stepSize: 1 }
            }
          }
        },
        plugins: [ChartDataLabels] // 👈 Activate plugin for labels
      });
    })
    .catch(err => {
      alert("Failed to load data: " + err.message);
    });
</script>
    </body>
    </html>
    """
    current_year = datetime.now().year
    return render_template_string(html, year=current_year)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
