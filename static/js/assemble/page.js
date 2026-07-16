/** 整页组装：fragments 壳 + views 显示串 → 完整 HTML。零金额运算。 */
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
  /** 与 render._pv 对齐：周期显隐壳 */
  function wrapPvBodies(bodyByKey, yearKey, periodKeys) {
    if (!bodyByKey) return "";
    var keys = periodKeys && periodKeys.length ? periodKeys : Object.keys(bodyByKey);
    var out = "";
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i];
      if (bodyByKey[k] == null) continue;
      var style = k === yearKey ? "" : "display:none";
      out += '<div class="pv" data-blk="' + escAttr(k) + '" style="' + style + '">' +
        bodyByKey[k] + "</div>";
    }
    return out;
  }
  /** 排名：叶子显示串 → rankings.js；月度字典只注入一次（任务书34）。 */
  function buildRankViewsHtml(views) {
    if (!views || !views.rankings_view) return "";
    if (typeof global.assembleRankings !== "function") return "";
    var rv = views.rankings_view;
    var yk = views.year_key || "";
    var keys = views.period_keys && views.period_keys.length
      ? views.period_keys
      : Object.keys(rv);
    var store = views.rankings_monthly_data || {};
    if (typeof global.setRankingsMonthlyStore === "function") {
      global.setRankingsMonthlyStore(store);
    } else {
      global.__rkMonthlyData = store;
    }
    var out = "";
    if (typeof global.monthlyDataScript === "function") {
      out += global.monthlyDataScript(store);
    } else if (store && Object.keys(store).length) {
      out += '<script type="application/json" id="rkMonthlyData">' +
        JSON.stringify(store).replace(/</g, "\\u003c") + "</script>";
    }
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i];
      if (!rv[k]) continue;
      var style = k === yk ? "" : "display:none";
      // 多周期共享页面级字典，勿再每周期 embed monthly_data 脚本
      out += '<div class="pv" data-blk="' + escAttr(k) + '" style="' + style + '">' +
        global.assembleRankings(rv[k], { includeMonthlyScript: false }) + "</div>";
    }
    return out;
  }
  /**
   * 用 views 填入须客户端组装的字段（覆盖 fragments 中的空串）。
   */
  function applyViews(data, views) {
    if (!views) return data;
    var yk = views.year_key || "";
    var keys = views.period_keys || [];
    if (views.kpi_body) data.kpi_views = wrapPvBodies(views.kpi_body, yk, keys);
    if (views.pl_body) data.pl_views = wrapPvBodies(views.pl_body, yk, keys);
    if (views.donut_body) data.donut_views = wrapPvBodies(views.donut_body, yk, keys);
    if (views.profit_rank_body) {
      data.profit_rank_views = wrapPvBodies(views.profit_rank_body, yk, keys);
    }
    if (views.rankings_view) data.rank_views = buildRankViewsHtml(views);
    if (views.trend_html != null) data.trend_html = views.trend_html;
    if (views.receipts_budget != null) data.receipts_budget = views.receipts_budget;
    // BU 专属：fragments strip 后由 views 还原（非周期 .pv 卡，显示成品串）
    if (views.receipts_html != null) data.receipts_html = views.receipts_html;
    if (views.pl_tag != null) data.pl_tag = views.pl_tag;
    if (views.period_bar != null) data.period_bar = views.period_bar;
    if (views.daily_html != null) data.daily_html = views.daily_html;
    return data;
  }
  function assemblePage(frags, templates, views) {
    var data = {};
    var k;
    for (k in frags) {
      if (Object.prototype.hasOwnProperty.call(frags, k)) data[k] = frags[k];
    }
    applyViews(data, views);
    var body = fill(templates.dashboard_body, data);
    return fill(templates.page_shell, {
      title: data.title || "甲骨易智能经营罗盘",
      body: body
    });
  }
  global.assemblePage = assemblePage;
  global._assembleFill = fill;
  global.wrapPvBodies = wrapPvBodies;
  global.buildRankViewsHtml = buildRankViewsHtml;
  global.applyViews = applyViews;
})(typeof window !== "undefined" ? window : globalThis);
