from flask import Flask, request, jsonify, send_from_directory, render_template_string
import psycopg
import os
from datetime import datetime
from functools import lru_cache
from flask import request, Response
import json


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
            inquiry_data = json.load(f)
        
        with open("buyers_with_suggestions_and_notes_with_nationalities.json", "r", encoding="utf-8") as f:
            buyers_data = json.load(f)
        
        # Merge buyers_data into inquiry_data under a new key
        inquiry_data["buyers"] = buyers_data

        return app.response_class(json.dumps(inquiry_data), mimetype="application/json")
    
    except FileNotFoundError as e:
        return jsonify(error=f"{e.filename} not found"), 404

# === 📊 Dashboard HTML Page ===
@app.route("/dashboard/inquiries")
def inquiries_dashboard():
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
      <title>AbraCasaBra Real Estate</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2"></script>
<script>
  // Register the plugin with Chart.js
  Chart.register(ChartDataLabels);
</script>
      <style>
        body {
          font-family: 'Inter', sans-serif;
          background: #f8fafc;
          padding: 2rem;
        }
        h2 {
          text-align: center;
        }
table, th, td {
  border: 1px solid #ccc;
  padding: 6px 12px;
}
thead {
  background: #f1f5f9;
}

.top-properties-table {
  border-collapse: collapse;
  width: 100%;
  font-size: 14px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  background: #fff;
}

.top-properties-table th, .top-properties-table td {
  border: 1px solid #ddd;
  padding: 8px 12px;
  text-align: left;
}

.top-properties-table th {
  background-color: #f4f4f4;
  font-weight: bold;
}

.top-properties-table tr:nth-child(even) {
  background-color: #fafafa;
}



#priceNationalityChart {
  max-height: 90vh !important; /* taller */
  aspect-ratio: auto;          /* let height expand */
}

.top-properties-table a {
  color: #2563EB;
  text-decoration: none;
  font-weight: 500;
}
.top-properties-table a:hover {
  text-decoration: underline;
}

canvas {
  width: 100%;
  max-width: 1400px;
max-height: 60vh;
  height: auto;
  aspect-ratio: 3 / 1; /* Keep it wide and short */
  display: block;
  margin: 2rem auto;
}
      </style>
    </head>
    <body>
      <h2>AbraCasaBra Real Estate Statistics - {{ year }}</h2>
    <h3 style="text-align:center; margin-top:3rem;"> Auto import Inquiries & Wishlists</h3>
      <canvas id="inquiryChart"></canvas>
      <h3 style="text-align:center; margin-top:3rem;"> Monthly Inquiry Breakdown Per Portal</h3>
<canvas id="sourceBreakdownChart"></canvas>

<!-- === Buyers Budget & Nationality (New) === -->
<h3 style="text-align:center; margin-top:3rem;">Buyer Budget & Nationality (Monthly / Year-to-Date)</h3>

<!-- 🔹 Controls for Chart 1 -->
<div id="controlsBudgetOverTime" style="max-width:1400px;margin:1rem auto;display:flex;gap:.75rem;flex-wrap:wrap;align-items:center;justify-content:center">
  <label><input type="radio" name="modeBudgetOverTime" value="monthly" checked> Monthly</label>
  <label><input type="radio" name="modeBudgetOverTime" value="ytd"> Year-to-Date</label>
  <select id="monthBudgetOverTime" style="padding:.4rem .6rem;border:1px solid #ddd;border-radius:.4rem"></select>
</div>

<!-- 🔹 Controls for Chart 2 -->
<div id="controlsNationality" style="max-width:1400px;margin:1rem auto;display:flex;gap:.75rem;flex-wrap:wrap;align-items:center;justify-content:center">
  <label><input type="radio" name="modeNationality" value="monthly" checked> Monthly</label>
  <label><input type="radio" name="modeNationality" value="ytd"> Year-to-Date</label>
  <select id="monthNationality" style="padding:.4rem .6rem;border:1px solid #ddd;border-radius:.4rem"></select>
</div>

<!-- 🔹 Controls for Chart 3 -->
<div id="controlsBudgetByNationality" style="max-width:1400px;margin:1rem auto;display:flex;gap:.75rem;flex-wrap:wrap;align-items:center;justify-content:center">
  <label><input type="radio" name="modeBudgetByNationality" value="monthly" checked> Monthly</label>
  <label><input type="radio" name="modeBudgetByNationality" value="ytd"> Year-to-Date</label>
  <select id="monthBudgetByNationality" style="padding:.4rem .6rem;border:1px solid #ddd;border-radius:.4rem"></select>
</div>

<!-- Chart 1: Budget distribution over time -->
<h4 style="text-align:center;margin-top:1rem;">Budget Distribution (Stacked by Price Range)</h4>
<canvas id="buyersBudgetOverTimeChart"></canvas>

<!-- Chart 2: Inquiries by Nationality (count) -->
<h4 style="text-align:center;margin-top:2rem;">Inquiries by Nationality</h4>
<canvas id="buyersNationalityChart"></canvas>

<!-- Chart 3: Budget by Nationality (who has what budget) -->
<h4 style="text-align:center;margin-top:2rem;">Budget by Nationality (Stacked by Price Range)</h4>
<canvas id="buyersBudgetByNationalityChart"></canvas>

    <h3 style="text-align:center; margin-top:3rem;"> Monthly Property Views Website</h3>
    <canvas id="viewsChart"></canvas>
<h3 style="text-align:center; margin-top:3rem;">Most Viewed Locations Of All Time (Property Pages)</h3>
<canvas id="locationsChart"></canvas>

<h3 style="text-align:center; margin-top:3rem;">Top Viewer Countries</h3>
<canvas id="countriesChart"></canvas>

<h3 style="text-align:center; margin-top:3rem;">Views by Price Range</h3>
<canvas id="priceRangeChart"></canvas>

<h3 style="text-align:center; margin-top:3rem;">Views by Price Range & Nationality</h3>
<canvas id="priceNationalityChart"></canvas>

<h3 style="text-align:center; margin-top:3rem;">Most Viewed Properties Of All Time</h3>
<div id="topPropertiesContainer" style="overflow-x:auto; max-width:1400px; margin:2rem auto;"></div>



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

      // instead of building table HTML
// Collect unique sources
const sourceSet = new Set();
months.forEach(month => {
  if (data[month]) {
    Object.keys(data[month].sources || {}).forEach(src => sourceSet.add(src));
  }
});
const sources = Array.from(sourceSet);

const datasets = [];

// Add per-source stacks
sources.forEach((src, i) => {
  let color;
  const cleanLabel = src.replace("Subject: ", "").toLowerCase();

  if (cleanLabel.includes("pisos.com")) {
    color = "rgba(255, 159, 64, 0.8)"; // orange for pisos.com
  } else if (cleanLabel.includes("kyero")) {
    color = "rgba(255, 99, 132, 0.8)"; // reddish for kyero
  } else {
    // fallback to auto HSL colors for other sources
    color = `hsl(${(i * 60) % 360}, 60%, 60%)`;
  }

  datasets.push({
    label: src.replace("Subject: ", ""),
    data: months.map(m => data[m]?.sources?.[src] || 0),
    backgroundColor: color,
    stack: "sources"
  });
});

// ====== Buyers charts (Budget & Nationality) ======
const buyersBlock = data.buyers || data["buyers"] || null;
const buyersRaw = buyersBlock && Array.isArray(buyersBlock.data) ? buyersBlock.data : [];
const currentYear = new Date().getFullYear();

// Build month list for current year (YYYY-MM)
const monthKeys = [...Array(12).keys()].map(i => `${currentYear}-${String(i+1).padStart(2,"0")}`);






// Helpers
const PRICE_BUCKETS = [
  [0,150000],[150000,300000],[300000,500000],
  [500000,750000],[750000,1000000],[1000000,1500000],[1500000,Infinity]
];
const PRICE_BUCKET_LABELS = ["0–150k","150–300k","300–500k","500–750k","750k–1M","1M–1.5M","1.5M+"];

function toMonthKey(ts){
  // input like "2025-10-20 22:37:30"
  const d = new Date(ts.replace(" ","T"));
  if (isNaN(d.getTime())) return null;
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}`;
}

function inCurrentYear(rec){
  const d = new Date(rec.inquiry_date.replace(" ","T"));
  return d.getFullYear() === currentYear;
}

function bucketIndex(price){
  const p = Number(price||0);
  for (let i=0;i<PRICE_BUCKETS.length;i++){
    const [lo,hi] = PRICE_BUCKETS[i];
    if (p>=lo && p<hi) return i;
  }
  return PRICE_BUCKETS.length-1;
}

function aggregateBuyers() {
  // Filter to current year
  const rows = buyersRaw.filter(inCurrentYear);

  // Monthly map: ym -> rows[]
  const byMonth = new Map(monthKeys.map(m => [m, []]));
  rows.forEach(r => {
    const mk = toMonthKey(r.inquiry_date);
    if (mk && byMonth.has(mk)) byMonth.get(mk).push(r);
  });

  // YTD = all rows in current year
  const ytd = rows;

  return { byMonth, ytd };
}

const buyersAgg = aggregateBuyers();

// Chart instances (for clean re-render)
let CHART_budgetOverTime = null;
let CHART_nationality = null;
let CHART_budgetByNationality = null;

function destroyIfExists(ch){
  if (ch && typeof ch.destroy === "function") ch.destroy();
}

// ===== Chart 1: Budget distribution over time =====
// - Monthly: x = price buckets, values = counts for the selected month
// - YTD:     x = months, stacked by price buckets (trend across the year)
function renderBudgetOverTime(mode, monthKey){
  const ctx = document.getElementById("buyersBudgetOverTimeChart");
  destroyIfExists(CHART_budgetOverTime);

  if (mode === "monthly") {
    const rows = buyersAgg.byMonth.get(monthKey) || [];
    const counts = Array(PRICE_BUCKETS.length).fill(0);
    rows.forEach(r => counts[bucketIndex(r.max_price)]++);

    CHART_budgetOverTime = new Chart(ctx, {
      type: "bar",
      data: {
        labels: PRICE_BUCKET_LABELS,
        datasets: [{ label: `Inquiries (${monthKey})`, data: counts, backgroundColor: "rgba(54,162,235,0.7)" }]
      },
      options: {
        responsive:true, maintainAspectRatio:false,
        plugins:{ legend:{display:false}, datalabels:{ display:false } },
        scales:{ y:{ beginAtZero:true, ticks:{ stepSize:1 } } }
      },
      plugins:[ChartDataLabels]
    });
  } else {
    // YTD stacked by buckets over months
    const datasets = PRICE_BUCKET_LABELS.map((label,i) => ({
      label,
      data: monthKeys.map(m=>{
        const rows = buyersAgg.byMonth.get(m) || [];
        return rows.reduce((acc,r)=> acc + (bucketIndex(r.max_price)===i ? 1 : 0), 0);
      }),
      backgroundColor: `hsl(${(i*45)%360},60%,60%)`,
      stack:"buckets"
    }));

    CHART_budgetOverTime = new Chart(ctx, {
      type:"bar",
      data:{ labels: monthKeys, datasets },
      options:{
        responsive:true, maintainAspectRatio:false,
        plugins:{ legend:{ position:"top" }, datalabels:{ display:false } },
        scales:{ x:{ stacked:true }, y:{ stacked:true, beginAtZero:true } }
      },
      plugins:[ChartDataLabels]
    });
  }
}

// ===== Chart 2: Inquiries by Nationality (counts) =====
// - Monthly: counts per nationality for selected month
// - YTD:     counts per nationality across current year
function renderNationality(mode, monthKey){
  const ctx = document.getElementById("buyersNationalityChart");
  destroyIfExists(CHART_nationality);

  const rows = (mode==="monthly") ? (buyersAgg.byMonth.get(monthKey) || []) : buyersAgg.ytd;
  const countsByNat = {};
  rows.forEach(r => {
    const nat = r.nationality || "Unknown";
    countsByNat[nat] = (countsByNat[nat]||0)+1;
  });

  // Top 12 nationalities + others
  const entries = Object.entries(countsByNat).sort((a,b)=>b[1]-a[1]);
  const main = entries.slice(0,12);
  const others = entries.slice(12).reduce((acc, [,v])=>acc+v, 0);
  if (others>0) main.push(["Others", others]);

  CHART_nationality = new Chart(ctx, {
    type:"bar",
    data:{
      labels: main.map(e=>e[0]),
      datasets:[{ label:"Inquiries", data: main.map(e=>e[1]), backgroundColor:"rgba(75,192,192,0.7)" }]
    },
    options:{
      responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{display:false}, datalabels:{ display:false } },
      scales:{ y:{ beginAtZero:true, ticks:{ stepSize:1 } } }
    },
    plugins:[ChartDataLabels]
  });
}

// ===== Chart 3: Budget by Nationality (stacked buckets) =====
// - Monthly: for selected month
// - YTD:     for current year
function renderBudgetByNationality(mode, monthKey){
  const ctx = document.getElementById("buyersBudgetByNationalityChart");
  destroyIfExists(CHART_budgetByNationality);

  const rows = (mode==="monthly") ? (buyersAgg.byMonth.get(monthKey) || []) : buyersAgg.ytd;

  // Totals per nationality
  const countsByNat = {};
  rows.forEach(r=>{
    const nat = r.nationality || "Unknown";
    countsByNat[nat] = (countsByNat[nat]||0)+1;
  });

  // Top 10 nationalities by total
  const topNats = Object.entries(countsByNat).sort((a,b)=>b[1]-a[1]).slice(0,10).map(e=>e[0]);

  // Build matrix [nat][bucket] -> count
  const matrix = {};
  topNats.forEach(n => matrix[n] = Array(PRICE_BUCKETS.length).fill(0));
  rows.forEach(r=>{
    const nat = topNats.includes(r.nationality||"Unknown") ? (r.nationality||"Unknown") : null;
    if (!nat) return; // skip non-top for readability
    matrix[nat][bucketIndex(r.max_price)]++;
  });

  const datasets = PRICE_BUCKET_LABELS.map((label, i)=>({
    label,
    data: topNats.map(n => matrix[n][i]),
    backgroundColor:`hsl(${(i*45)%360},60%,60%)`,
    stack:"buckets"
  }));

  CHART_budgetByNationality = new Chart(ctx, {
    type:"bar",
    data:{ labels: topNats, datasets },
    options:{
      responsive:true, maintainAspectRatio:false,
      plugins:{
        legend:{ position:"top" },
        tooltip:{
          mode:"index", intersect:false,
          callbacks:{ label: (ctx)=> `${ctx.dataset.label}: ${ctx.raw}` }
        },
        datalabels:{ display:false }
      },
      scales:{ x:{ stacked:true }, y:{ stacked:true, beginAtZero:true } }
    },
    plugins:[ChartDataLabels]
  });
}


function setupIndependentControls(chartName, renderFn) {
  const radios = document.querySelectorAll(`input[name="mode${chartName}"]`);
  const select = document.getElementById(`month${chartName}`);

  // populate month options
  select.innerHTML = monthKeys.map(m => {
    const d = new Date(`${m}-01T00:00:00`);
    return `<option value="${m}" ${d.getMonth()===new Date().getMonth() ? "selected":""}>${d.toLocaleString(undefined,{month:"long"})}</option>`;
  }).join("");

  let mode = "monthly";
  radios.forEach(r => {
    r.addEventListener("change", e => {
      mode = e.target.value;
      select.disabled = (mode !== "monthly");
      renderFn(mode, select.value);
    });
  });
  select.addEventListener("change", () => renderFn(mode, select.value));
  renderFn(mode, select.value); // initial render
}

if (buyersRaw.length) {
  setupIndependentControls("BudgetOverTime", renderBudgetOverTime);
  setupIndependentControls("Nationality", renderNationality);
  setupIndependentControls("BudgetByNationality", renderBudgetByNationality);
}


      const topLocations = data["top_viewed_locations"] || [];
      if (topLocations.length > 0) {
        const locationLabels = topLocations.map(loc => loc.name);
        const locationViews = topLocations.map(loc => loc.views);

        new Chart(document.getElementById('locationsChart'), {
          type: 'bar',
          data: {
            labels: locationLabels,
            datasets: [{
              label: 'Views per Location',
              data: locationViews,
              backgroundColor: 'rgba(153, 102, 255, 0.7)'
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { display: false },
              tooltip: {
                callbacks: {
                  label: ctx => `${ctx.raw} views`
                }
              },
              datalabels: {
                anchor: 'end',
                align: 'end',
                color: '#333',
                font: { weight: 'bold' },
                formatter: value => value > 0 ? value : ''
              }
            },
            scales: {
              y: { beginAtZero: true }
            }
          },
          plugins: [ChartDataLabels]
        });
      }


// === Price Range Views Chart ===
const priceRangeData = data["views_by_price_range"] || {};
if (Object.keys(priceRangeData).length > 0) {
  // 🟢 Step 1: merge all ranges >= 1500000 into one
  const mergedData = {};
  let over1_5MTotal = 0;

  Object.entries(priceRangeData).forEach(([range, count]) => {
    let low = 0, high = 0;

    if (range.includes("+")) {
      low = parseInt(range);
      high = Infinity;
    } else {
      [low, high] = range.split("-").map(n => parseInt(n));
    }

    if (low >= 1500000) {
      over1_5MTotal += count;
    } else {
      mergedData[range] = (mergedData[range] || 0) + count;
    }
  });

  if (over1_5MTotal > 0) {
    mergedData["1500000+"] = over1_5MTotal;
  }

  // 🟢 Step 2: sort ranges
  const labels = Object.keys(mergedData).sort((a, b) => {
    if (a.includes("+")) return 1;
    if (b.includes("+")) return -1;
    const aLow = parseInt(a.split("-")[0]) || 0;
    const bLow = parseInt(b.split("-")[0]) || 0;
    return aLow - bLow;
  });

  const values = labels.map(l => mergedData[l]);

  // 🟢 Step 3: build chart
  new Chart(document.getElementById("priceRangeChart"), {
    type: "bar",
    data: {
      labels: labels,
      datasets: [{
        label: "Total Views",
        data: values,
        backgroundColor: "rgba(255, 205, 86, 0.7)"
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.raw} views`
          }
        },
        datalabels: {
          anchor: "end",
          align: "end",
          color: "#333",
          font: { weight: "bold" },
          formatter: value => value > 0 ? value : ""
        }
      },
      scales: {
        x: {
          ticks: {
            callback: function(value, index) {
              const range = labels[index];
              if (range.includes("+")) return "1.5M+";
              const [low, high] = range.split("-").map(n => parseInt(n));
              return `${low/1000}k-${high/1000}k`;
            }
          }
        },
        y: { beginAtZero: true }
      }
    },
    plugins: [ChartDataLabels]
  });
}

const topCountries = data["top_viewer_countries"] || [];
if (topCountries.length > 0) {
  const countryLabels = topCountries.map(c => c.country);
  const countryViews = topCountries.map(c => c.views);

  new Chart(document.getElementById('countriesChart'), {
    type: 'bar',
    data: {
      labels: countryLabels,
      datasets: [{
        label: 'Views by Country',
        data: countryViews,
        backgroundColor: 'rgba(75, 192, 192, 0.7)'
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        datalabels: {
          anchor: 'end',
          align: 'end',
          color: '#333',
          font: { weight: 'bold' },
          formatter: value => value > 0 ? value : ''
        }
      },
      scales: { y: { beginAtZero: true } }
    },
    plugins: [ChartDataLabels]
  });
}

// === Views by Price Range & Nationality ===
const priceNatData = data["views_by_price_and_nationality"] || {};
if (Object.keys(priceNatData).length > 0) {
  // 🟢 Step 1: normalize ranges → merge all >= 1500000 into one
  const mergedData = {};

  Object.entries(priceNatData).forEach(([country, ranges]) => {
    mergedData[country] = {};
    let over1_5MTotal = 0;

    Object.entries(ranges).forEach(([range, count]) => {
      let low = 0;
      let high = 0;

      if (range.includes("+")) {
        low = parseInt(range); // e.g. "5000000+" → 5000000
        high = Infinity;
      } else {
        [low, high] = range.split("-").map(n => parseInt(n));
      }

      if (low >= 1500000) {
        over1_5MTotal += count;
      } else {
        mergedData[country][range] = (mergedData[country][range] || 0) + count;
      }
    });

    if (over1_5MTotal > 0) {
      mergedData[country]["1500000+"] = over1_5MTotal;
    }
  });

  // 🟢 Step 2: collect all ranges again (after merge)
  const allRanges = new Set();
  Object.values(mergedData).forEach(ranges => {
    Object.keys(ranges).forEach(r => allRanges.add(r));
  });

  // Sort ranges: numeric, with "1500000+" last
  const priceRanges = Array.from(allRanges).sort((a, b) => {
    if (a.includes("+")) return 1;
    if (b.includes("+")) return -1;
    const aLow = parseInt(a.split("-")[0]) || 0;
    const bLow = parseInt(b.split("-")[0]) || 0;
    return aLow - bLow;
  });

  // 🟢 Step 3: sort countries by total views
  const countryTotals = {};
  Object.entries(mergedData).forEach(([country, ranges]) => {
    countryTotals[country] = Object.values(ranges).reduce((a, b) => a + b, 0);
  });
  const sortedCountries = Object.keys(countryTotals).sort(
    (a, b) => countryTotals[b] - countryTotals[a]
  );

  // 🟢 Step 4: build datasets
  const datasets = sortedCountries.map((country, idx) => ({
    label: country,
    data: priceRanges.map(r => mergedData[country]?.[r] || 0),
    backgroundColor: `hsl(${(idx * 50) % 360}, 60%, 60%)`
  }));

  // 🟢 Step 5: draw chart
  new Chart(document.getElementById("priceNationalityChart"), {
    type: "bar",
    data: { labels: priceRanges, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        tooltip: {
          mode: "index",
          intersect: false,
          itemSort: (a, b) => b.raw - a.raw, // high → low
          callbacks: {
            label: ctx => `${ctx.dataset.label}: ${ctx.raw} views`
          }
        },
        legend: { display: false },   // ❌ hide countries + colors
        datalabels: { display: false }
      },
      scales: {
        x: {
          stacked: true,
          ticks: {
            callback: function(value, index) {
              const range = this.getLabelForValue(value);
              if (range.includes("+")) return "1.5M+";
              const [low, high] = range.split("-").map(n => parseInt(n));
              return `${low / 1000}k-${high / 1000}k`;
            }
          }
        },
        y: { stacked: true, beginAtZero: true }
      }
    },
    plugins: [ChartDataLabels]
  });
}



const topProperties = data["top_viewed_links"] || [];
if (topProperties.length > 0) {
  let html = "<table class='top-properties-table'>";
  html += "<thead><tr><th>Rank</th><th>Reference</th><th>Views</th><th>Link</th></tr></thead><tbody>";
  topProperties.forEach((p, idx) => {
    html += `<tr>
      <td>${idx + 1}</td>
      <td>${p.ref}</td>
      <td>${p.views}</td>
      <td><a href="${p.link}" target="_blank">View</a></td>
    </tr>`;
  });
  html += "</tbody></table>";
  document.getElementById("topPropertiesContainer").innerHTML = html;
}

new Chart(document.getElementById("sourceBreakdownChart"), {
  type: "bar",
  data: { labels: months, datasets },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      tooltip: { mode: "index", intersect: false },
      legend: { position: "top" },
      datalabels: {
        color: "#333",
        font: { weight: "bold" },
        formatter: v => v > 0 ? v : ""
      }
    },
    scales: {
      x: { stacked: true },
      y: { stacked: true, beginAtZero: true }
    }
  },
  plugins: [ChartDataLabels]
});


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

            // === 📈 Line Chart: Property Views ===
      let lastDataIndex = months.findLastIndex(month => data[month]?.property_views > 0);

// If no data, show nothing
if (lastDataIndex === -1) lastDataIndex = 0;

// Trim months and viewsData to only that range
const trimmedMonths = months.slice(0, lastDataIndex + 1);
const viewsData = trimmedMonths.map(month => data[month]?.property_views || 0);
      const viewColors = viewsData.map(val => val > 0 ? 'rgba(34,197,94,0.5)' : 'rgba(180,180,180,0.3)');

      new Chart(document.getElementById('viewsChart'), {
  type: 'line',
  data: {
    labels: trimmedMonths,
    datasets: [{
      label: 'Property Views',
      data: viewsData,
      fill: false,
      tension: 0.3,
      borderColor: 'rgba(34,197,94,1)',
      backgroundColor: 'rgba(34,197,94,0.5)',
      pointRadius: 5,
      pointHoverRadius: 7
    }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: { duration: 1000 },
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: ctx => `Views: ${ctx.raw}`
              }
            },
            datalabels: {
              align: 'top',
              anchor: 'end',
              color: '#10b981',
              font: { weight: 'bold' },
              formatter: (value) => value > 0 ? value : ''
            }
          },
scales: {
  y: {
    beginAtZero: true,
    suggestedMax: Math.max(...viewsData) + 5000,
    ticks: {
      callback: (value) => value.toLocaleString()
    }
  }
}
        },
        plugins: [ChartDataLabels]
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
