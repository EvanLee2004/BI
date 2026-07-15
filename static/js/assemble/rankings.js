/** P0 排名双血条组装：只拼 DOM，零金额运算。输入=rankings_view_for_period JSON。
 *  embed_full + full_items：预拼 .rk-full，BU 本地弹窗（cockpit-bu.js），零 API。 */
(function (global) {
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c];
    });
  }
  function dualRows(items) {
    if (!items || !items.length) return '<div class="ev-empty">本期无数据</div>';
    return items.map(function (it) {
      var wo = (it.wo != null ? Number(it.wo) : 0).toFixed(1);
      var wr = (it.wr != null ? Number(it.wr) : 0).toFixed(1);
      return '<div class="ev-row dual-row"><span class="rk-no">' + it.i + '</span>' +
        '<span class="ev-name" title="' + esc(it.name) + '">' + esc(it.name) + '</span>' +
        '<div class="dual-bars">' +
        '<span class="dual-bar dual-o" title="下单"><i style="width:' + wo + '%"></i><em>' + esc(it.order_disp) + '</em></span>' +
        '<span class="dual-bar dual-r" title="回款"><i style="width:' + wr + '%"></i><em>' + esc(it.receipt_disp) + '</em></span>' +
        '</div></div>';
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
      // 与 render rank_body：list 关后再挂 .rk-full
      var full = '';
      if (blk.embed_full && blk.full_items && blk.full_items.length) {
        full = '<div class="rk-full" hidden><div class="ev-list">' + dualRows(blk.full_items) + '</div></div>';
      }
      body = '<div class="ev-list rk-list">' + dualRows(blk.items) + more + '</div>' + full;
    }
    return '<div class="card" data-dim="' + esc(blk.dim) + '"><div class="card-h">' + esc(blk.title) +
      '</div>' + body + '</div>';
  }
  function assembleRankings(view) {
    if (!view || view.visible === false) return '';
    return '<div class="grid-2e dual-grid" data-start="' + esc(view.start) + '" data-end="' + esc(view.end) + '">\n' +
      card(view.sales) + '\n\n' + card(view.customer) + '\n\n</div>\n';
  }
  global.assembleRankings = assembleRankings;
})(typeof window !== 'undefined' ? window : globalThis);
