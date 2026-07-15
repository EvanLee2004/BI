/** 整页组装：碎片 + views(排名等) + 模板 → 完整 HTML。零金额运算。 */
(function (global) {
  function fill(tpl, data) {
    return tpl.replace(/\{([a-zA-Z0-9_]+)\}/g, function (_, k) {
      return data[k] != null ? String(data[k]) : "";
    });
  }
  function escAttr(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/"/g, "&quot;")
      .replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  /**
   * 用 rankings.js 的 assembleRankings 按周期拼 rank_views（与 render._pv 结构对齐）。
   * 金额字段仅使用后端给的 order_disp/receipt_disp/wo/wr，不做金额运算。
   */
  function buildRankViewsHtml(views) {
    if (!views || !views.rankings_view) return "";
    if (typeof global.assembleRankings !== "function") return "";
    var rv = views.rankings_view;
    var yk = views.year_key || "";
    var keys = views.period_keys && views.period_keys.length
      ? views.period_keys
      : Object.keys(rv);
    var out = "";
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i];
      if (!rv[k]) continue;
      var style = k === yk ? "" : "display:none";
      var inner = global.assembleRankings(rv[k]);
      out += '<div class="pv" data-blk="' + escAttr(k) + '" style="' + style + '">' +
        inner + "</div>";
    }
    return out;
  }
  /**
   * @param {object} frags  fragments 字典
   * @param {object} templates  {dashboard_body, page_shell}
   * @param {object} [views]  {rankings_view, year_key, period_keys} — 有则用 JS 组装 rank_views
   */
  function assemblePage(frags, templates, views) {
    var data = {};
    var k;
    for (k in frags) {
      if (Object.prototype.hasOwnProperty.call(frags, k)) data[k] = frags[k];
    }
    if (views && views.rankings_view) {
      data.rank_views = buildRankViewsHtml(views);
    }
    var body = fill(templates.dashboard_body, data);
    var html = fill(templates.page_shell, {
      title: data.title || "甲骨易智能经营罗盘",
      body: body
    });
    return html;
  }
  global.assemblePage = assemblePage;
  global._assembleFill = fill;
  global.buildRankViewsHtml = buildRankViewsHtml;
})(typeof window !== "undefined" ? window : globalThis);
