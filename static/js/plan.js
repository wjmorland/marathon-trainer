(function () {
  document.addEventListener("DOMContentLoaded", function () {
    var current = document.querySelector('.week[data-current="true"]');
    if (!current) return;
    current.scrollIntoView({ block: "start" });
  });
})();
