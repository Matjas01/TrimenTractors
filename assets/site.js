(function () {
  "use strict";
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };
  var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Header: menu toggle and a shadow once the page scrolls
  var menuBtn = document.querySelector(".menu-btn");
  var nav = document.getElementById("nav");
  if (menuBtn && nav) {
    menuBtn.addEventListener("click", function () {
      menuBtn.setAttribute("aria-expanded", String(nav.classList.toggle("open")));
    });
  }
  var header = document.querySelector("[data-header]");
  if (header) {
    var onScroll = function () { header.classList.toggle("scrolled", window.scrollY > 8); };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  $$("[data-print]").forEach(function (b) { b.addEventListener("click", function () { window.print(); }); });

  // Sections fade in as they scroll into view
  var reveal = $$("[data-reveal]");
  if (!reduced && "IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px" });
    reveal.forEach(function (el) {
      var siblings = el.parentElement ? $$(":scope > [data-reveal]", el.parentElement) : [];
      var i = siblings.indexOf(el);
      if (i > 0) el.style.setProperty("--d", Math.min(i, 6) * 0.07 + "s");
      io.observe(el);
    });
  } else {
    reveal.forEach(function (el) { el.classList.add("in"); });
  }

  // Category tabs on the home page
  $$("[data-tabs]").forEach(function (box) {
    var tabs = $$('[role="tab"]', box);
    var panels = tabs.map(function (tab) { return document.getElementById(tab.getAttribute("aria-controls")); });
    function select(i, focus) {
      tabs.forEach(function (tab, j) {
        tab.setAttribute("aria-selected", String(i === j));
        tab.tabIndex = i === j ? 0 : -1;
        panels[j].hidden = i !== j;
        if (i === j) $$("[data-reveal]", panels[j]).forEach(function (el) { el.classList.add("in"); });
      });
      if (focus) tabs[i].focus();
    }
    tabs.forEach(function (tab, i) {
      tab.addEventListener("click", function () { select(i); });
      tab.addEventListener("keydown", function (e) {
        if (e.key === "ArrowRight") select((i + 1) % tabs.length, true);
        if (e.key === "ArrowLeft") select((i - 1 + tabs.length) % tabs.length, true);
      });
    });
    select(0);
  });

  // Featured offer in the hero: rotates every few seconds, stops on hover or focus
  $$("[data-carousel]").forEach(function (box) {
    var slides = $$(".slide", box);
    var dots = $$(".dot", box);
    if (slides.length < 2) return;
    var index = 0, timer = null;
    function show(i) {
      index = (i + slides.length) % slides.length;
      slides.forEach(function (s, j) {
        s.hidden = j !== index;
        if (j === index) { s.classList.remove("enter"); void s.offsetWidth; s.classList.add("enter"); }
      });
      dots.forEach(function (d, j) { if (j === index) d.setAttribute("aria-current", "true"); else d.removeAttribute("aria-current"); });
      var next = slides[(index + 1) % slides.length].querySelector("img");
      if (next) next.loading = "eager";
    }
    function start() { if (!reduced && !timer) timer = setInterval(function () { show(index + 1); }, 6000); }
    function stop() { clearInterval(timer); timer = null; }
    box.querySelector("[data-prev]").addEventListener("click", function () { stop(); show(index - 1); });
    box.querySelector("[data-next]").addEventListener("click", function () { stop(); show(index + 1); });
    dots.forEach(function (d, i) { d.addEventListener("click", function () { stop(); show(i); }); });
    box.addEventListener("mouseenter", stop);
    box.addEventListener("mouseleave", start);
    box.addEventListener("focusin", stop);
    document.addEventListener("visibilitychange", function () { if (document.hidden) stop(); else start(); });
    start();
  });

  // Offer row arrows
  $$("[data-scroll]").forEach(function (btn) {
    var section = btn.closest("section");
    var scroller = section && section.querySelector("[data-scroller]");
    if (!scroller) return;
    btn.addEventListener("click", function () {
      var card = scroller.querySelector("li");
      var step = card ? card.getBoundingClientRect().width + 16 : 300;
      scroller.scrollBy({ left: step * Number(btn.getAttribute("data-scroll")), behavior: reduced ? "auto" : "smooth" });
    });
  });

  // Request form: writes an email to the salesperson for the chosen topic
  var dialog = document.querySelector("[data-request-dialog]");
  if (dialog && dialog.showModal) {
    var config = JSON.parse(dialog.getAttribute("data-config"));
    var form = dialog.querySelector("form");
    $$("[data-request]").forEach(function (link) {
      link.addEventListener("click", function (e) {
        e.preventDefault();
        dialog.showModal();
        form.elements.what.focus();
      });
    });
    dialog.addEventListener("click", function (e) { if (e.target === dialog) dialog.close(); });
    form.addEventListener("submit", function (e) {
      if (!e.submitter || e.submitter.value !== "send") return;
      var f = form.elements;
      var to = config[f.topic.value] || config.m;
      var body = f.what.value.trim() + "\n\n" + [f.name.value.trim(), f.contact.value.trim()].filter(Boolean).join("\n") +
        "\n\n" + location.href;
      window.location.href = "mailto:" + to + "?subject=" + encodeURIComponent(config.subject) + "&body=" + encodeURIComponent(body);
    });
  }

  // Plural forms: (one, other) or, for Russian, (one, few, many)
  function plural(lang, forms, n) {
    var i;
    if (lang === "ru") i = n % 10 === 1 && n % 100 !== 11 ? 0 : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? 1 : 2;
    else if (lang === "lv") i = n % 10 === 1 && n % 100 !== 11 ? 0 : 1;
    else i = n === 1 ? 0 : 1;
    return forms[Math.min(i, forms.length - 1)].replace("{n}", n);
  }

  // Listing filters
  var FIELDS = ["q", "c", "make", "hinge", "wmin", "wmax", "sort"];
  var SORTS = {
    new: function (a, b) { return a.rank - b.rank; },
    price_asc: function (a, b) { return (a.price || Infinity) - (b.price || Infinity) || a.rank - b.rank; },
    price_desc: function (a, b) { return b.price - a.price || a.rank - b.rank; },
    year: function (a, b) { return (b.year || 0) - (a.year || 0) || a.rank - b.rank; },
    width: function (a, b) { return (a.width || Infinity) - (b.width || Infinity) || a.rank - b.rank; }
  };

  $$("[data-listing]").forEach(function (root) {
    var form = root.querySelector(".filters");
    var list = root.querySelector(".cards");
    var count = root.querySelector(".result-count");
    var empty = root.querySelector(".no-results");
    var i18n = JSON.parse(root.getAttribute("data-i18n"));
    var cards = $$(".card", list).map(function (li) {
      var d = li.dataset;
      return { el: li, id: d.id, cat: d.cat, make: d.make, hinge: d.hinge, text: d.text,
        rank: +d.rank, price: +d.price, year: +d.year || 0, width: d.width ? +d.width : null };
    });
    var params = new URLSearchParams(location.search);
    FIELDS.forEach(function (name) {
      var el = form.elements[name];
      if (!el || !params.has(name)) return;
      el.value = params.get(name);
      if (el.tagName === "SELECT" && el.value !== params.get(name)) el.value = "";
    });

    function val(name) { var el = form.elements[name]; return el ? el.value.trim() : ""; }

    function apply() {
      var words = val("q").toLowerCase().split(/\s+/).filter(Boolean);
      var c = val("c"), make = val("make"), hinge = val("hinge");
      var wmin = parseFloat(val("wmin")), wmax = parseFloat(val("wmax"));
      var shown = cards.filter(function (it) {
        if (c && it.cat !== c) return false;
        if (make && it.make !== make) return false;
        if (hinge && it.hinge !== hinge) return false;
        if (!isNaN(wmin) && !(it.width >= wmin)) return false;
        if (!isNaN(wmax) && !(it.width !== null && it.width <= wmax)) return false;
        return words.every(function (w) { return it.text.indexOf(w) > -1; });
      });
      shown.sort(SORTS[val("sort")] || SORTS.new);
      cards.forEach(function (it) { it.el.hidden = true; });
      shown.forEach(function (it) { it.el.hidden = false; list.appendChild(it.el); });
      count.textContent = plural(i18n.lang, i18n.results, shown.length);
      empty.hidden = shown.length > 0;
      var p = new URLSearchParams();
      FIELDS.forEach(function (name) {
        var v = val(name);
        if (v && !(name === "sort" && v === "new")) p.set(name, v);
      });
      var qs = p.toString();
      history.replaceState(null, "", location.pathname + (qs ? "?" + qs : "") + location.hash);
    }

    form.addEventListener("input", apply);
    form.addEventListener("change", apply);
    form.addEventListener("submit", function (e) { e.preventDefault(); apply(); });
    form.addEventListener("reset", function () { setTimeout(apply, 0); });
    apply();
  });

  // Links from the old site pointed at item pop-ups: /en/for_sale/1/all#id=3065
  var legacy = location.hash.match(/^#id=(\d+)$/);
  if (legacy) {
    var hit = document.querySelector('.card[data-id="' + legacy[1] + '"] a');
    if (hit) location.replace(hit.href);
  }

  // Lightbox
  var box, boxImg, boxCount, urls = [], index = 0, touchX = null;

  function show(i) {
    index = (i + urls.length) % urls.length;
    boxImg.src = urls[index];
    boxCount.textContent = urls.length > 1 ? index + 1 + " / " + urls.length : "";
  }

  function openBox(list, start, labels) {
    if (!box) {
      box = document.createElement("dialog");
      box.className = "lightbox";
      box.innerHTML = '<img alt=""><span class="lb-count"></span>' +
        '<button type="button" class="lb-prev">&#8249;</button><button type="button" class="lb-next">&#8250;</button>' +
        '<button type="button" class="lb-close">&#215;</button>';
      document.body.appendChild(box);
      boxImg = box.querySelector("img");
      boxCount = box.querySelector(".lb-count");
      box.querySelector(".lb-prev").addEventListener("click", function () { show(index - 1); });
      box.querySelector(".lb-next").addEventListener("click", function () { show(index + 1); });
      box.querySelector(".lb-close").addEventListener("click", function () { box.close(); });
      box.addEventListener("click", function (e) { if (e.target === box) box.close(); });
      box.addEventListener("keydown", function (e) {
        if (e.key === "ArrowLeft") show(index - 1);
        if (e.key === "ArrowRight") show(index + 1);
      });
      box.addEventListener("touchstart", function (e) { touchX = e.touches[0].clientX; }, { passive: true });
      box.addEventListener("touchend", function (e) {
        if (touchX === null) return;
        var dx = e.changedTouches[0].clientX - touchX;
        if (Math.abs(dx) > 40) show(index + (dx < 0 ? 1 : -1));
        touchX = null;
      });
    }
    var names = ["prev", "next", "close"];
    (labels || []).forEach(function (label, i) { box.querySelector(".lb-" + names[i]).setAttribute("aria-label", label); });
    box.querySelector(".lb-prev").hidden = box.querySelector(".lb-next").hidden = list.length < 2;
    urls = list;
    show(start);
    box.showModal();
  }

  // Product gallery: thumbnails swap the main photo, the main photo opens the lightbox
  $$("[data-gallery]").forEach(function (g) {
    var labels = JSON.parse(g.getAttribute("data-labels") || "[]");
    var main = g.querySelector(".g-main");
    var mainImg = main.querySelector("img");
    var thumbs = $$(".g-thumbs a", g);
    var list = thumbs.length ? thumbs.map(function (a) { return a.href; }) : [main.href];
    thumbs.forEach(function (a) {
      a.addEventListener("click", function (e) {
        e.preventDefault();
        mainImg.src = a.href;
        mainImg.alt = a.querySelector("img").alt;
        main.href = a.href;
        main.setAttribute("data-i", a.getAttribute("data-i"));
        thumbs.forEach(function (t) { t.removeAttribute("aria-current"); });
        a.setAttribute("aria-current", "true");
      });
    });
    main.addEventListener("click", function (e) {
      e.preventDefault();
      openBox(list, +main.getAttribute("data-i") || 0, labels);
    });
  });

  // About page photos
  $$("[data-photos]").forEach(function (ul) {
    var labels = JSON.parse(ul.getAttribute("data-labels") || "[]");
    var links = $$("a", ul);
    var list = links.map(function (a) { return a.href; });
    links.forEach(function (a, i) {
      a.addEventListener("click", function (e) { e.preventDefault(); openBox(list, i, labels); });
    });
  });
})();
