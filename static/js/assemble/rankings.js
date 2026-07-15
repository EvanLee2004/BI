/** P0 排名双血条组装：只拼 DOM，零金额运算。输入=rankings_view_for_period JSON。 */
(function (global) {
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c];
    });
  }
  function dualRows(items) {
    if (!items || !items.length) return '<div class="ev-empty">本期无数据</div>';
    return items.map(function (it) {
      return '<div class="ev-row dual-row"><span class="rk-no">' + it.i + '</span>' +
        '<span class="ev-name" title="' + esc(it.name) + '">' + esc(it.name) + '</span>' +
        '<div class="dual-bars">' +
        '<span class="dual-bar dual-o" title="下单"><i style="width:' + it.wo.toFixed(1) + '%"></i><em>' + esc(it.order_disp) + '</em></span>' +
        '<span class="dual-bar dual-r" title="回款"><i style="width:' + it.wr.toFixed(1) + '%"></i><em>' + esc(it.receipt_disp) + '</em></span>' +
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
      body = '<div class="ev-list rk-list">' + dualRows(blk.items) + more + '</div>';
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
