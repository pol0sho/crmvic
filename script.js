let currentFeed = "resales";
let currentPage = 1;

const grid = document.getElementById("properties-grid");
const pageInfo = document.getElementById("pageInfo");

function fetchProperties(feed, page) {
  fetch(`/api/properties?feed=${feed}&page=${page}`)
    .then(res => res.json())
    .then(data => {
      renderProperties(data.properties || []);
      pageInfo.textContent = `Page ${page}`;
    })
    .catch(err => {
      console.error("Fetch error:", err);
      grid.innerHTML = "<p style='grid-column: span 6'>Failed to load properties.</p>";
    });
}

function renderProperties(properties) {
  grid.innerHTML = "";
  properties.forEach(prop => {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <img src="${prop.cover_image || 'https://via.placeholder.com/300x200?text=No+Image'}" alt="Property Image" />
      <div class="price">€${prop.price.toLocaleString()}</div>
      <div>${prop.beds} 🛏️  |  ${prop.baths} 🛁</div>
      <div>${prop.town}</div>
      <div>Ref: ${prop.ref}</div>
    `;
    grid.appendChild(card);
  });
}

// Feed button logic
document.querySelectorAll(".top-buttons button").forEach(btn => {
  btn.addEventListener("click", () => {
    currentFeed = btn.dataset.feed;
    currentPage = 1;
    fetchProperties(currentFeed, currentPage);
  });
});

// Pagination
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

// Initial load
fetchProperties(currentFeed, currentPage);