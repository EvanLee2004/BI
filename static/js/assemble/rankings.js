/** P0 排名双血条组装：只拼 DOM，零金额运算。输入=rankings_view_for_period JSON。
 *  embed_full + full_items：预拼 .rk-full，BU 本地弹窗（cockpit-bu.js），零 API。
 *  陆总#8 / 任务书34：页面级 monthly 字典 + 行 data-mkey；paint 按键查表，零金额运算。 */
(function (global) {
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c];
    });
  }
  function dualBarRow(it, extraClass, titleAttr, mkey) {
    var wo = (it.wo != null ? Number(it.wo) : 0).toFixed(1);
    var wr = (it.wr != null ? Number(it.wr) : 0).toFixed(1);
    var cls = "ev-row dual-row" + (extraClass ? " " + extraClass : "");
    var t = titleAttr ? ' title="' + esc(titleAttr) + '"' : "";
    var dm = mkey ? ' data-mkey="' + esc(mkey) + '"' : "";
    return '<div class="' + cls + '"' + t + dm + '><span class="rk-no">' + it.i + '</span>' +
      '<span class="ev-name" title="' + esc(it.name) + '">' + esc(it.name) + '</span>' +
      '<div class="dual-bars">' +
      '<span class="dual-bar dual-o" title="下单"><i style="width:' + wo + '%"></i><em>' + esc(it.order_disp) + '</em></span>' +
      '<span class="dual-bar dual-r" title="回款"><i style="width:' + wr + '%"></i><em>' + esc(it.receipt_disp) + '</em></span>' +
      '</div></div>';
  }
  function dualRows(items, asEntity) {
    if (!items || !items.length) return '<div class="ev-empty">本期无数据</div>';
    return items.map(function (it) {
      if (asEntity) {
        return dualBarRow(it, "rk-entity", "点开看 1~12 月下单/回款", it.mkey || "");
      }
      return dualBarRow(it, "", "", "");
    }).join('');
  }
  function card(blk) {
    var body;
    if (blk.empty) body = '<div class="ev-empty">本期无数据</div>';
    else {
      var more = '';
      if (blk.others) {
        more = '<div class="ev-row rk-row rk-others rk-more" title="点开看 10 名以后的完整明细">' +
          '<span class="rk-no">…</span><span class="ev-name">其余 ' + blk.others.names +
          ' 个 <span class="rk-open">点开看明细 ›</span></span><span class="ev-track"></span>' +
          '<span class="ev-amt">' + esc(blk.others.amt) + '</span>' +
          '<span class="rk-meta">' + blk.others.count + '笔</span></div>';
      }
      var full = '';
      if (blk.embed_full && blk.full_items && blk.full_items.length) {
        full = '<div class="rk-full" hidden><div class="ev-list">' + dualRows(blk.full_items, true) + '</div></div>';
      }
      body = '<div class="ev-list rk-list">' + dualRows(blk.items, true) + more + '</div>' + full;
    }
    return '<div class="card" data-dim="' + esc(blk.dim) + '"><div class="card-h">' + esc(blk.title) +
      '</div>' + body + '</div>';
  }
  /** 页面级月度 JSON 脚本（与 Python render.monthly_data_script 同形）。 */
  function monthlyDataScript(store) {
    if (!store || !Object.keys(store).length) return "";
    var payload = JSON.stringify(store).replace(/</g, "\\u003c");
    return '<script type="application/json" id="rkMonthlyData">' + payload + "</script>";
  }
  function setMonthlyStore(store) {
    if (store && typeof store === "object") {
      global.__rkMonthlyData = store;
    }
  }
  function resolveMonthlyStore(el) {
    if (global.__rkMonthlyData && typeof global.__rkMonthlyData === "object") {
      return global.__rkMonthlyData;
    }
    try {
      if (typeof document !== "undefined") {
        var node = document.getElementById("rkMonthlyData");
        if (node && node.textContent) {
          var parsed = JSON.parse(node.textContent);
          global.__rkMonthlyData = parsed;
          return parsed;
        }
      }
    } catch (e) { /* ignore */ }
    return null;
  }
  /**
   * @param {object} view rankings_view_for_period JSON
   * @param {{includeMonthlyScript?: boolean}} opts 默认 true：单周期自带 monthly_data 时输出脚本
   */
  function assembleRankings(view, opts) {
    if (!view || view.visible === false) return '';
    opts = opts || {};
    var includeScript = opts.includeMonthlyScript !== false;
    var html = '<div class="grid-2e dual-grid" data-start="' + esc(view.start) + '" data-end="' + esc(view.end) + '">\n' +
      card(view.sales) + '\n\n' + card(view.customer) + '\n\n</div>\n';
    if (includeScript && view.monthly_data) {
      setMonthlyStore(view.monthly_data);
      return monthlyDataScript(view.monthly_data) + html;
    }
    return html;
  }
  /** 点击主体行：按 data-mkey 查页面级字典，拼双血条列表（零金额运算）。 */
  function paintMonthlyFromAttr(el) {
    if (!el) return '';
    var key = el.getAttribute('data-mkey');
    if (!key) return '<div class="ev-empty">无月度数据</div>';
    var store = resolveMonthlyStore(el);
    if (!store) return '<div class="ev-empty">无月度数据</div>';
    var rows = store[key];
    if (!rows || !rows.length) return '<div class="ev-empty">无月度数据</div>';
    return '<div class="ev-list">' + rows.map(function (m) {
      return dualBarRow(m, "dual-month", "", "");
    }).join('') + '</div>';
  }
  global.assembleRankings = assembleRankings;
  global.paintRankingMonthly = paintMonthlyFromAttr;
  global.monthlyDataScript = monthlyDataScript;
  global.setRankingsMonthlyStore = setMonthlyStore;
})(typeof window !== 'undefined' ? window : globalThis);
