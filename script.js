let currentView = "properties";
let currentFeed = "resales";
let propertyPage = 1;
let contactPage = 1;
let nextPageCache = [];
let pageCache = {};
let inSearchMode = false;

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
  currentView = "properties";
  const perPage = getItemsPerPage();
  const cacheKey = getCacheKey(feed, page, perPage);
  if (pageCache[cacheKey]) {
    renderProperties(pageCache[cacheKey]);
    pageInfo.textContent = `Page ${page}`;
    preloadNextPage(feed, page + 1);
    return;
  }

  grid.classList.remove("fade-in");
  grid.style.opacity = 0;

  fetch(`/api/properties?feed=${feed}&page=${page}&per_page=${perPage}`)
    .then(res => res.json())
    .then(data => {
      const properties = data.properties || [];
      pageCache[cacheKey] = properties;
      renderProperties(properties);
      nextPageCache = data.next || [];
      pageInfo.textContent = `Page ${page}`;
      requestAnimationFrame(() => {
        grid.classList.add("fade-in");
        grid.style.opacity = 1;
      });
    })
    .catch(err => {
      console.error("Fetch error:", err);
      grid.innerHTML = "<p style='grid-column: span 6'>Failed to load properties.</p>";
    });
}

function fetchContacts(page = 1) {
  currentView = "contacts";
  const perPage = 100;
  const role = document.getElementById("roleSelect")?.value || "";

  grid.classList.remove("fade-in");
  grid.style.opacity = 0;

  fetch(`/api/contacts?page=${page}&per_page=${perPage}&role=${role}`)
    .then(res => res.json())
    .then(data => {
      renderContacts(data.contacts);
      pageInfo.textContent = `Contacts - Page ${page}`;
      requestAnimationFrame(() => {
        grid.classList.add("fade-in");
        grid.style.opacity = 1;
      });
    })
    .catch(err => {
      console.error("Contacts fetch failed:", err);
      grid.innerHTML = "<p style='grid-column: span 6'>Failed to load contacts.</p>";
    });
}

function renderProperties(properties) {
  grid.innerHTML = "";
  properties.forEach((prop, i) => {
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
    setTimeout(() => card.classList.add("fade-in"), i * 40);
  });
}

function renderContacts(contacts) {
  grid.innerHTML = "";
  contacts.forEach((contact, i) => {
    const card = document.createElement("div");
    card.className = "contact-card fade-in";
    card.innerHTML = `
      <div class="name">${contact.name}</div>
      <div class="email">${contact.email}</div>
      <div class="phone">📞 ${contact.phone}</div>
      <div class="mobile">📱 ${contact.mobile || ""}</div>
      <div class="roles">${(contact.roles || []).map(role => `<span>${role}</span>`).join("")}</div>
      <button class="delete-button" onclick="deleteContact(${contact.id})">Delete</button>
    `;
    grid.appendChild(card);
    setTimeout(() => card.classList.add("fade-in"), i * 40);
  });
}

function deleteContact(id) {
  if (!confirm("Are you sure you want to delete this contact?")) return;

  fetch(`/api/contacts/${id}`, { method: "DELETE" })
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        fetchContacts(contactPage);
      } else {
        alert("Delete failed.");
      }
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

document.getElementById("searchButton").addEventListener("click", () => {
  const ref = document.getElementById("searchInput").value.trim();
  if (!ref) return;

  currentView = "properties";
  inSearchMode = true;
  grid.classList.remove("fade-in");
  grid.style.opacity = 0;

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
      requestAnimationFrame(() => {
        grid.classList.add("fade-in");
        grid.style.opacity = 1;
      });
    })
    .catch(err => {
      console.error("Search failed:", err);
      grid.innerHTML = "<p style='grid-column: span 6'>Search failed. Try again.</p>";
    });
});

document.getElementById("searchInput").addEventListener("keydown", e => {
  if (e.key === "Enter") {
    document.getElementById("searchButton").click();
  }
});

document.querySelectorAll(".top-buttons button").forEach(btn => {
  btn.addEventListener("click", () => {
    const feed = btn.dataset.feed;
    if (feed) {
      currentView = "properties";
      inSearchMode = false;
      currentFeed = feed;
      propertyPage = 1;
      pageInfo.textContent = "";
      fetchProperties(currentFeed, propertyPage);
    }
  });
});

document.getElementById("viewContacts").addEventListener("click", () => {
  inSearchMode = false;
  contactPage = 1;
  fetchContacts(contactPage);
});

document.getElementById("nextPage").addEventListener("click", () => {
  if (currentView === "properties") {
    propertyPage++;
    fetchProperties(currentFeed, propertyPage);
  } else if (currentView === "contacts") {
    contactPage++;
    fetchContacts(contactPage);
  }
});

document.getElementById("prevPage").addEventListener("click", () => {
  if (currentView === "properties" && propertyPage > 1) {
    propertyPage--;
    fetchProperties(currentFeed, propertyPage);
  } else if (currentView === "contacts" && contactPage > 1) {
    contactPage--;
    fetchContacts(contactPage);
  }
});

window.addEventListener("resize", () => {
  if (currentView !== "properties") return;
  const newPerPage = getItemsPerPage();
  if (newPerPage !== lastPerPage) {
    lastPerPage = newPerPage;
    pageCache = {};
    fetchProperties(currentFeed, propertyPage);
  }
});

// Initial load
fetchProperties(currentFeed, propertyPage);
