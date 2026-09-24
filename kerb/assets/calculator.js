/* "What's your database worth?" calculator.
   Assumptions: 0.8% of contacts book an appraisal, 1 in 5 appraisals lists,
   $400 fee per booked appraisal. Results are copied into the pilot form. */
(function () {
  var BOOK_RATE = 0.008;
  var LIST_RATE = 0.2;
  var FEE = 400;

  var $ = function (id) { return document.getElementById(id); };
  var aud = new Intl.NumberFormat("en-AU", { style: "currency", currency: "AUD", maximumFractionDigits: 0 });
  var aud2 = new Intl.NumberFormat("en-AU", { style: "currency", currency: "AUD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
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
      var v = clean(box.value);
      range.value = Math.min(Math.max(v, +range.min), +range.max);
      update();
    });
  }

  function update() {
    var contacts = Math.round(clean($("contacts").value));
    var commission = clean($("commission").value);

    // You pay per whole appraisal, so round appraisals before costing anything.
    var appraisals = Math.round(contacts * BOOK_RATE);
    var listings = appraisals * LIST_RATE;
    var grossCommission = listings * commission;
    var fee = appraisals * FEE;

    $("o-appraisals").textContent = num.format(appraisals);
    $("o-listings").textContent = num.format(listings);
    $("o-commission").textContent = aud.format(grossCommission);
    $("o-fee").textContent = aud.format(fee);
    $("o-multiple").textContent = fee > 0 ? aud2.format(grossCommission / fee) : "–";
    $("o-cpl").textContent = aud.format(FEE / LIST_RATE);

    $("f-contacts").value = contacts;
    $("f-commission").value = commission;
    $("f-estimate").value = appraisals + " appraisals / " + num.format(listings) + " listings / " + aud.format(grossCommission) + " commission / " + aud.format(fee) + " fee";
    var visible = $("f-contacts-visible");
    if (visible && !visible.dataset.touched) visible.value = contacts || "";
  }

  document.addEventListener("DOMContentLoaded", function () {
    link("contacts-range", "contacts");
    link("commission-range", "commission");
    var visible = $("f-contacts-visible");
    if (visible) visible.addEventListener("input", function () { visible.dataset.touched = "1"; });
    var yr = $("yr");
    if (yr) yr.textContent = new Date().getFullYear();
    update();
  });
})();
