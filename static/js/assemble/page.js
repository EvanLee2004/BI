/** 整页组装：碎片(display 串/HTML 段) + 模板 → 完整 HTML。零金额运算。 */
(function (global) {
  function fill(tpl, data) {
    return tpl.replace(/\{([a-zA-Z0-9_]+)\}/g, function (_, k) {
      return data[k] != null ? String(data[k]) : "";
    });
  }
  function assemblePage(frags, templates) {
    var body = fill(templates.dashboard_body, frags);
    var html = fill(templates.page_shell, {
      title: frags.title || "甲骨易智能经营罗盘",
      body: body
    });
    return html;
  }
  global.assemblePage = assemblePage;
  global._assembleFill = fill;
})(typeof window !== "undefined" ? window : globalThis);
