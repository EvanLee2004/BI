/** P0 排名双血条组装：只拼 DOM，零金额运算。输入=rankings_view_for_period JSON。
 *  embed_full + full_items：预拼 .rk-full，BU 本地弹窗（cockpit-bu.js），零 API。
 *  陆总#8：主体行 data-monthly=1~12 月显示串 JSON；点击时拼双血条，零金额运算。 */
(function (global) {
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c];
    });
  }
  function dualBarRow(it, extraClass, titleAttr, monthlyJson) {
    var wo = (it.wo != null ? Number(it.wo) : 0).toFixed(1);
    var wr = (it.wr != null ? Number(it.wr) : 0).toFixed(1);
    var cls = "ev-row dual-row" + (extraClass ? " " + extraClass : "");
    var t = titleAttr ? ' title="' + esc(titleAttr) + '"' : "";
    var dm = monthlyJson ? ' data-monthly="' + esc(monthlyJson) + '"' : "";
    return '<div class="' + cls + '"' + t + dm + '><span class="rk-no">' + it.i + '</span>' +
      '<span class="ev-name" title="' + esc(it.name) + '">' + esc(it.name) + '</span>' +
      '<div class="dual-bars">' +
      '<span class="dual-bar dual-o" title="下单"><i style="width:' + wo + '%"></i><em>' + esc(it.order_disp) + '</em></span>' +
      '<span class="dual-bar dual-r" title="回款"><i style="width:' + wr + '%"></i><em>' + esc(it.receipt_disp) + '</em></span>' +
      '</div></div>';
  }
  function jsonNum(v) {
    var f = Number(v == null ? 0 : v);
    if (!isFinite(f)) f = 0;
    // 与 Python _json_num：整值出 int，避免 100.0 vs 100 导致 golden 不等
    return f === Math.floor(f) ? Math.floor(f) : Math.round(f * 10) / 10;
  }
  function monthlyJsonOf(it) {
    var mon = it.monthly;
    if (!mon || !mon.length) return "";
    // 只保留显示串/宽度（与 Python _monthly_json_attr 同形）
    var rows = mon.map(function (m) {
      return {
        i: jsonNum(m.i),
        name: m.name,
        wo: jsonNum(m.wo),
        wr: jsonNum(m.wr),
        order_disp: m.order_disp,
        receipt_disp: m.receipt_disp
      };
    });
    return JSON.stringify(rows);
  }
  function dualRows(items, asEntity) {
    if (!items || !items.length) return '<div class="ev-empty">本期无数据</div>';
    return items.map(function (it) {
      if (asEntity) {
        return dualBarRow(it, "rk-entity", "点开看 1~12 月下单/回款", monthlyJsonOf(it));
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
  function assembleRankings(view) {
    if (!view || view.visible === false) return '';
    return '<div class="grid-2e dual-grid" data-start="' + esc(view.start) + '" data-end="' + esc(view.end) + '">\n' +
      card(view.sales) + '\n\n' + card(view.customer) + '\n\n</div>\n';
  }
  /** 点击主体行：把 data-monthly 显示串拼成双血条列表（零金额运算）。 */
  function paintMonthlyFromAttr(el) {
    if (!el) return '';
    var raw = el.getAttribute('data-monthly');
    if (!raw) return '<div class="ev-empty">无月度数据</div>';
    var rows;
    try { rows = JSON.parse(raw); } catch (e) { return '<div class="ev-empty">月度数据损坏</div>'; }
    if (!rows || !rows.length) return '<div class="ev-empty">无月度数据</div>';
    return '<div class="ev-list">' + rows.map(function (m) {
      return dualBarRow(m, "dual-month", "", "");
    }).join('') + '</div>';
  }
  global.assembleRankings = assembleRankings;
  global.paintRankingMonthly = paintMonthlyFromAttr;
})(typeof window !== 'undefined' ? window : globalThis);
