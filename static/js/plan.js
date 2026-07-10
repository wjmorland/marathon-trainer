(function () {
  document.addEventListener("DOMContentLoaded", function () {
    // The "today" highlight is baked into the HTML at build time (in UTC,
    // on whatever schedule the site rebuilds), so it drifts from the
    // visitor's actual local date. Recompute it here from the browser's
    // local clock so the highlight is always correct regardless of when
    // the site was last built or what timezone the visitor is in.
    var now = new Date();
    var todayStr = now.getFullYear()
      + "-" + String(now.getMonth() + 1).padStart(2, "0")
      + "-" + String(now.getDate()).padStart(2, "0");

    document.querySelectorAll(".day-row").forEach(function (row) {
      row.classList.toggle("today", row.dataset.date === todayStr);
    });

    var todayRow = document.querySelector('.day-row[data-date="' + todayStr + '"]');
    var current = todayRow ? todayRow.closest(".week") : null;

    document.querySelectorAll(".week").forEach(function (week) {
      if (week === current) {
        week.setAttribute("data-current", "true");
      } else {
        week.removeAttribute("data-current");
      }
    });

    if (!current) return;
    current.scrollIntoView({ block: "start" });
  });
})();
