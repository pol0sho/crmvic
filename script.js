let currentFeed = "resales";
let currentPage = 1;
let nextPageCache = [];
const pageCache = {};  // 🧠 Cache pages in memory: { "resales-1": [...], "kyero-2": [...] }

const grid = document.getElementById("properties-grid");
const pageInfo = document.getElementById("pageInfo");

function getCacheKey(feed, page, perPage) {
  return `${feed}-${page}-${perPage}`;
}

function getItemsPerPage() {
  const gridWidth = window.innerWidth;
  const gridHeight = window.innerHeight - 200; // Subtract for top/pagination

  const cardWidth = 400 + 16;   // card + horizontal gap
  const cardHeight = 291 + 80;  // image + text + padding estimate

  const columns = Math.floor(gridWidth / cardWidth);
  const rawRows = Math.floor(gridHeight / cardHeight);

  const rows = Math.max(rawRows, 5); // 👈 Enforce at least 4 rows
  const itemsPerPage = columns * rows;

  return Math.max(itemsPerPage, columns); // fallback to 1 row if necessary
}

let lastPerPage = getItemsPerPage(); // used for resize detection

function fetchProperties(feed, page) {
  const perPage = getItemsPerPage();
  const cacheKey = getCacheKey(feed, page, perPage);

  if (pageCache[cacheKey]) {
    renderProperties(pageCache[cacheKey]);
    pageInfo.textContent = `Page ${page}`;
    preloadNextPage(feed, page + 1);
    return;
  }

  fetch(`/api/properties?feed=${feed}&page=${page}&per_page=${perPage}`)
    .then(res => res.json())
    .then(data => {
      const properties = data.properties || [];
      pageCache[cacheKey] = properties;
      renderProperties(properties);
      nextPageCache = data.next || [];
      pageInfo.textContent = `Page ${page}`;
    })
    .catch(err => {
      console.error("Fetch error:", err);
      grid.innerHTML = "<p style='grid-column: span 6'>Failed to load properties.</p>";
    });
}

function preloadNextPage(feed, page) {
  const perPage = getItemsPerPage();
  const nextKey = getCacheKey(feed, page, perPage);
  if (pageCache[nextKey]) return;

  fetch(`/api/properties?feed=${feed}&page=${page}&per_page=${perPage}`)
    .then(res => res.json())
    .then(data => {
      pageCache[nextKey] = data.properties || [];
      nextPageCache = data.next || [];
    })
    .catch(() => {});
}

function renderProperties(properties) {
  grid.innerHTML = "";
  properties.forEach(prop => {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <img loading="lazy" src="${prop.cover_image || 'https://via.placeholder.com/300x200?text=No+Image'}" alt="Property Image" />
      <div class="price">€${Number(prop.price).toLocaleString()}</div>
      <div>${prop.beds} 🛏️  |  ${prop.baths} 🛁</div>
      <div>${prop.town}</div>
      <div>Ref: ${prop.ref}</div>
    `;
    grid.appendChild(card);
  });
}

document.querySelectorAll(".top-buttons button").forEach(btn => {
  btn.addEventListener("click", () => {
    currentFeed = btn.dataset.feed;
    currentPage = 1;
    nextPageCache = [];
    pageInfo.textContent = "";
    fetchProperties(currentFeed, currentPage);
  });
});

document.getElementById("nextPage").addEventListener("click", () => {
  currentPage++;
  fetchProperties(currentFeed, currentPage);
});

document.getElementById("prevPage").addEventListener("click", () => {
  if (currentPage > 1) {
    currentPage--;
    fetchProperties(currentFeed, currentPage);
  }
});

window.addEventListener('resize', () => {
  const newPerPage = getItemsPerPage();
  if (newPerPage !== lastPerPage) {
    lastPerPage = newPerPage;
    pageCache = {}; // optional: clear cache to force correct layout
    fetchProperties(currentFeed, currentPage);
  }
});

fetchProperties(currentFeed, currentPage);
