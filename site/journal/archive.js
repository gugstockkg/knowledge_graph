"use strict";

const form = document.querySelector("#archive-filters");
const status = document.querySelector("#archive-status");
const pagination = document.querySelector("#archive-pages");
const pageNumber = document.querySelector("#archive-page-number");
const entries = [...document.querySelectorAll("[data-entry]")];
const groups = [...document.querySelectorAll("[data-group]")];
const pageSize = 12;
const normalize = (text) => text.normalize("NFKC").toLocaleLowerCase("ko").trim();

const searchable = new Map(entries.map((entry) => [entry, normalize(entry.textContent)]));

function readLocation() {
  const params = new URLSearchParams(location.search);
  const { q, category, year } = form.elements;
  q.value = params.get("q") || "";
  for (const select of [category, year]) {
    const value = params.get(select.name);
    select.value = [...select.options].some((option) => option.value === value) ? value : "";
  }
  return Math.max(1, Number.parseInt(params.get("page"), 10) || 1);
}

function render(requestedPage, writeLocation = true) {
  const { q, category, year } = form.elements;
  const terms = normalize(q.value).split(/\s+/u).filter(Boolean);
  const matches = entries.filter((entry) =>
    (!category.value || entry.dataset.category === category.value) &&
    (!year.value || entry.dataset.year === year.value) &&
    terms.every((term) => searchable.get(entry).includes(term))
  );
  const totalPages = Math.max(1, Math.ceil(matches.length / pageSize));
  const page = Math.min(totalPages, requestedPage);
  const start = (page - 1) * pageSize;
  const visible = new Set(matches.slice(start, start + pageSize));
  entries.forEach((entry) => { entry.hidden = !visible.has(entry); });
  groups.forEach((group) => { group.hidden = !group.querySelector("[data-entry]:not([hidden])"); });
  status.textContent = matches.length ? `총 ${matches.length}편 · ${start + 1}–${start + visible.size}편 표시` :
    "조건에 맞는 글이 없습니다. 검색어를 바꾸거나 필터를 초기화하세요.";
  pagination.hidden = totalPages === 1;
  pageNumber.textContent = `${page} / ${totalPages}`;
  pagination.querySelector('[data-direction="-1"]').disabled = page === 1;
  pagination.querySelector('[data-direction="1"]').disabled = page === totalPages;
  if (writeLocation) {
    const url = new URL(location.href);
    for (const field of [q, category, year]) {
      if (field.value.trim()) url.searchParams.set(field.name, field.value.trim());
      else url.searchParams.delete(field.name);
    }
    if (page > 1) url.searchParams.set("page", page);
    else url.searchParams.delete("page");
    history.replaceState(null, "", url);
  }
  return page;
}

let page = render(readLocation(), false);
form.hidden = false;
status.hidden = false;
form.addEventListener("input", () => { page = render(1); });
form.addEventListener("submit", (event) => {
  event.preventDefault();
  page = render(1);
});
form.addEventListener("reset", (event) => {
  event.preventDefault();
  for (const name of ["q", "category", "year"]) form.elements[name].value = "";
  page = render(1);
});
pagination.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-direction]");
  if (!button) return;
  page = render(page + Number(button.dataset.direction));
  status.scrollIntoView({ block: "nearest" });
});
window.addEventListener("popstate", () => { page = render(readLocation(), false); });
