let currentFeed = "resales";
let currentPage = 1;
let nextPageCache = [];
let inSearchMode = false;

const pageCache = {};  // 🧠 Cache pages in memory: { "resales-1": [...], "kyero-2": [...] }

const grid = document.getElementById("properties-grid");
const pageInfo = document.getElementById("pageInfo");

function getCacheKey(feed, page, perPage) {
  return `${feed}-${page}-${perPage}`;
}

function getItemsPerPage() {
  const gridWidth = window.innerWidth;
  const gridHeight = window.innerHeight - 200;

  const cardWidth = 400 + 16;
  const cardHeight = 291 + 80;

  const columns = Math.floor(gridWidth / cardWidth);
  const rawRows = Math.floor(gridHeight / cardHeight);

  const rows = Math.max(rawRows, 5);
  const itemsPerPage = columns * rows;

  return Math.max(itemsPerPage, columns);
}

let lastPerPage = getItemsPerPage();

function fetchProperties(feed, page) {
  if (inSearchMode) return; // 🧱 prevent flicker during search

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

document.getElementById("searchButton").addEventListener("click", () => {
  const ref = document.getElementById("searchInput").value.trim();
  if (!ref) return;

  inSearchMode = true;

  fetch(`/api/search?ref=${encodeURIComponent(ref)}`)
    .then(res => res.json())
    .then(data => {
      if (data.length > 0) {
        renderProperties(data.map(item => ({
          ...item.property,
          feed: item.feed
        })));
        pageInfo.textContent = `Found in feed: ${data[0].feed} | Ref: ${ref}`;
      } else {
        grid.innerHTML = "<p style='grid-column: span 6'>No property found with that reference.</p>";
        pageInfo.textContent = "";
      }
    })
    .catch(err => {
      console.error("Search failed:", err);
      grid.innerHTML = "<p style='grid-column: span 6'>Search failed. Try again.</p>";
    });
});

// 🔄 Allow Enter key to trigger search
document.getElementById("searchInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    document.getElementById("searchButton").click();
  }
});

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
      ${prop.feed ? `<div style="color: gray; font-size: 12px">From: ${prop.feed}</div>` : ""}
    `;
    grid.appendChild(card);
  });
}

document.querySelectorAll(".top-buttons button").forEach(btn => {
  btn.addEventListener("click", () => {
    inSearchMode = false;
    currentFeed = btn.dataset.feed;
    currentPage = 1;
    nextPageCache = [];
    pageInfo.textContent = "";
    fetchProperties(currentFeed, currentPage);
  });
});

document.getElementById("nextPage").addEventListener("click", () => {
  if (inSearchMode) return;
  currentPage++;
  fetchProperties(currentFeed, currentPage);
});

document.getElementById("prevPage").addEventListener("click", () => {
  if (inSearchMode || currentPage <= 1) return;
  currentPage--;
  fetchProperties(currentFeed, currentPage);
});

window.addEventListener('resize', () => {
  if (inSearchMode) return;

  const newPerPage = getItemsPerPage();
  if (newPerPage !== lastPerPage) {
    lastPerPage = newPerPage;
    pageCache = {};
    fetchProperties(currentFeed, currentPage);
  }
});

fetchProperties(currentFeed, currentPage);
