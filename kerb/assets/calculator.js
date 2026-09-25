/* Calculator + Calendly buttons.
   Calculator assumptions: 0.8% of contacts book an appraisal, 1 in 5 appraisals
   lists, $400 fee per booked appraisal. */
(function () {
  var BOOK_RATE = 0.008;
  var LIST_RATE = 0.2;
  var FEE = 400;
  var CALENDLY = "https://calendly.com/kerbautomation/30min?hide_gdpr_banner=1&primary_color=1f6feb";

  var $ = function (id) { return document.getElementById(id); };
  var aud = new Intl.NumberFormat("en-AU", { style: "currency", currency: "AUD", maximumFractionDigits: 0 });
  var num = new Intl.NumberFormat("en-AU", { maximumFractionDigits: 1 });

  function clean(v) {
    var n = parseFloat(String(v).replace(/[^\d.]/g, ""));
    return isFinite(n) && n > 0 ? n : 0;
  }

  // Keep a slider and its number box in step; the number box can go past the slider's range.
  function link(rangeId, boxId) {
    var range = $(rangeId), box = $(boxId);
    range.addEventListener("input", function () { box.value = range.value; update(); });
    box.addEventListener("input", function () {
      range.value = Math.min(Math.max(clean(box.value), +range.min), +range.max);
      update();
    });
  }

  function update() {
    var contacts = Math.round(clean($("contacts").value));
    var commission = clean($("commission").value);

    // You pay per whole appraisal, so round appraisals before costing anything.
    var appraisals = Math.round(contacts * BOOK_RATE);
    var listings = appraisals * LIST_RATE;

    $("o-appraisals").textContent = num.format(appraisals);
    $("o-listings").textContent = num.format(listings);
    $("o-commission").textContent = aud.format(listings * commission);
    $("o-fee").textContent = aud.format(appraisals * FEE);
    $("o-cpl").textContent = aud.format(FEE / LIST_RATE);
  }

  // "Book a call" buttons open Calendly as a popup; if the widget didn't load
  // (blocked script, offline), the link just opens Calendly in a new tab.
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest(".js-calendly");
    if (!a || !window.Calendly || e.metaKey || e.ctrlKey) return;
    e.preventDefault();
    window.Calendly.initPopupWidget({ url: CALENDLY });
  });

  document.addEventListener("DOMContentLoaded", function () {
    if ($("contacts")) {
      link("contacts-range", "contacts");
      link("commission-range", "commission");
      update();
    }
    var yr = $("yr");
    if (yr) yr.textContent = new Date().getFullYear();
  });
})();
