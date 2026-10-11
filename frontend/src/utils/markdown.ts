import DOMPurify from "dompurify";

/**
 * GFM 兼容的 Markdown → 安全 HTML 渲染器（零新依赖，纯手写）。
 *
 * 块级解析（按行扫描，替代旧版多轮全局 replace）：
 *   ```代码块 → GFM 表格(含 | 分隔行/对齐) → 标题(#~######) → 水平分割线(--- 或 *** 或 ___)
 *   → 有序列表(1. ，支持缩进嵌套) → 无序列表(- * +，支持缩进嵌套)
 *   → 引用(>) → 普通段落(空行分隔，单换行 <br/>)
 * 行内：`代码` [文本](链接) **粗体** *斜体*（先转义 & < >，再单遍正则扫描，互不干扰）
 * 安全：DOMPurify 消毒；链接仅放行 http/https（其余降级为纯文本，防 javascript: XSS）。
 *
 * 样式：表格/代码块等关键可读性样式以内联 style 兜底（脱离 CSS 也可读）；
 * 其余排版（标题字号、列表缩进、引用左边框、段落间距、表格斑马纹）
 * 交给 .aipm-md 作用域 CSS —— 见本文件导出的 MD_CSS 常量与 styles/global.css 末尾同名样式块。
 *
 * 保持 `renderMarkdownToHtml(md: string): string` 导出签名不变，调用方零改动。
 */

/* ------------------------------ 底层工具 ------------------------------ */

/** HTML 实体转义（先 & 后 < >） */
const escapeHtml = (s: string): string =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

/** 内联兜底样式（无 .aipm-md CSS 时保证可读性） */
const PRE_STYLE =
  "background:#0F172A0D;border:1px solid #E2E8F0;border-radius:8px;padding:12px;overflow:auto;font-size:13px;margin:10px 0";
const PRE_CODE_STYLE = "background:none;padding:0;font-size:inherit";
const CODE_INLINE_STYLE =
  "background:#0F172A0D;border-radius:4px;padding:1px 5px;font-size:0.9em";
const TABLE_STYLE =
  "border-collapse:collapse;margin:12px 0;width:100%;font-size:13px";
const TH_STYLE =
  "border:1px solid #E2E8F0;padding:6px 10px;background:#F1F5F9;font-weight:600;color:#0F172A;vertical-align:top";
const TD_STYLE =
  "border:1px solid #E2E8F0;padding:6px 10px;vertical-align:top";
const ZEBRA_STYLE = "background:#F8FAFC";
const HR_STYLE = "border:none;border-top:1px solid #E2E8F0;margin:16px 0";
const QUOTE_STYLE =
  "margin:10px 0;padding:8px 14px;border-left:3px solid #4F46E5;background:#F8FAFC;border-radius:0 8px 8px 0;color:#475569";
const H_STYLE: Record<number, string> = {
  1: "font-size:20px;font-weight:700;color:#0F172A;margin:18px 0 8px",
  2: "font-size:18px;font-weight:700;color:#0F172A;margin:16px 0 8px",
  3: "font-size:16px;font-weight:600;color:#0F172A;margin:14px 0 6px",
  4: "font-size:15px;font-weight:600;color:#0F172A;margin:12px 0 6px",
  5: "font-size:14px;font-weight:600;color:#0F172A;margin:10px 0 4px",
  6: "font-size:13px;font-weight:600;color:#475569;margin:10px 0 4px",
};

/** 是否为 GFM 表格分隔行（如 `| --- | :--: | --: |`；至少一个单元格为连字符） */
const isTableSeparator = (row?: string): boolean => {
  if (!row) return false;
  const t = row.trim();
  if (!t.includes("-") || !/^[\s|:-]+$/.test(t)) return false;
  const parts = t
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .replace(/\\\|/g, "\u0000")
    .split("|");
  const cells = parts.map((c) => c.replace(/\u0000/g, "").trim());
  if (cells.length === 0 || cells.every((c) => c === "")) return false;
  return cells.every((c) => /^:?-+:?$/.test(c));
};

/** 拆分表格行为单元格（支持 `|` 转义，首尾竖线可省略） */
const splitRow = (row: string): string[] => {
  const t = row.trim().replace(/^\|/, "").replace(/\|$/, "");
  return t
    .replace(/\\\|/g, "\u0000")
    .split("|")
    .map((c) => c.replace(/\u0000/g, "|").trim());
};

/** 行内解析（输入需为原文；内部先转义，再按 代码→链接→粗体→斜体 单遍匹配，互不干扰） */
const INLINE_RE = /(`[^`\n]+`)|(\*\*[^*]+\*\*)|(\[[^\]\n]+\]\([^)\s]+\))|(\*[^*\n]+\*)/g;

const inline = (raw: string): string => {
  const s = escapeHtml(raw);
  let out = "";
  let last = 0;
  let m: RegExpExecArray | null;
  INLINE_RE.lastIndex = 0;
  while ((m = INLINE_RE.exec(s)) !== null) {
    out += s.slice(last, m.index);
    const t = m[0];
    if (m[1]) {
      // 行内代码（内容已转义）
      out += `<code style="${CODE_INLINE_STYLE}">${t.slice(1, -1)}</code>`;
    } else if (m[2]) {
      // 粗体
      out += `<strong>${t.slice(2, -2)}</strong>`;
    } else if (m[3]) {
      // 链接 [text](url)：仅放行 http/https，其余（javascript: 等）降级为纯文本防 XSS
      const open = t.indexOf("](") + 2;
      const text = t.slice(1, open - 1);
      const urlEnc = t.slice(open, t.lastIndexOf(")"));
      const url = urlEnc.replace(/&amp;/g, "&").trim();
      if (/^https?:\/\//i.test(url)) {
        out += `<a href="${url.replace(/"/g, "%22")}" target="_blank" rel="noopener noreferrer">${text}</a>`;
      } else {
        out += `${text} (${urlEnc})`;
      }
    } else {
      // 斜体
      out += `<em>${t.slice(1, -1)}</em>`;
    }
    last = m.index + t.length;
  }
  out += s.slice(last);
  return out;
};

/* ------------------------------ 表格 ------------------------------ */

/** 生成 GFM 表格 HTML（表头 thead + 斑马纹 tbody + 列对齐，内联样式兜底） */
const buildTable = (header: string[], aligns: string[], body: string[][]): string => {
  const alignCss = (idx: number): string =>
    aligns[idx] === "center"
      ? "text-align:center;"
      : aligns[idx] === "right"
        ? "text-align:right;"
        : "text-align:left;";
  const thead = `<thead><tr>${header
    .map((c, idx) => `<th style="${TH_STYLE};${alignCss(idx)}">${inline(c)}</th>`)
    .join("")}</tr></thead>`;
  const rows = body
    .map((row, rIdx) => {
      const zebra = rIdx % 2 === 1 ? `${ZEBRA_STYLE};` : "";
      const cells = row
        .map((c, idx) => `<td style="${TD_STYLE};${alignCss(idx)}${zebra}">${inline(c)}</td>`)
        .join("");
      return `<tr>${cells}</tr>`;
    })
    .join("");
  return `<table style="${TABLE_STYLE}">${thead}<tbody>${rows}</tbody></table>`;
};

/* ------------------------------ 列表（支持缩进嵌套） ------------------------------ */

interface ListItem {
  indent: number;
  ordered: boolean;
  text: string;
  children: ListItem[];
}

/** 由扁平列表项按缩进构建嵌套树，再递归生成嵌套 <ul>/<ol>（嵌套列表位于父 <li> 内，HTML 合法） */
const parseList = (items: ListItem[]): string => {
  // 1. 构建树：stack 维护当前打开路径；弹出缩进不小于当前的节点
  const root: ListItem = { indent: -1, ordered: false, text: "", children: [] };
  const stack: ListItem[] = [root];
  for (const item of items) {
    while (stack.length > 1 && stack[stack.length - 1].indent >= item.indent) {
      stack.pop();
    }
    stack[stack.length - 1].children.push(item);
    stack.push(item);
  }

  // 2. 递归发射（嵌套列表放在父 <li> 内部）
  const emit = (node: ListItem, ordered: boolean): string => {
    const open = ordered ? "<ol>" : "<ul>";
    const close = ordered ? "</ol>" : "</ul>";
    let body = "";
    for (const child of node.children) {
      body += `<li>${inline(child.text)}`;
      if (child.children.length > 0) {
        // 子列表标签由「第一个子项」的类型决定（emit 遍历的是 child.children）
        body += emit(child, child.children[0]?.ordered ?? false);
      }
      body += `</li>`;
    }
    return `${open}${body}${close}`;
  };

  return emit(root, root.children[0]?.ordered ?? false);
};

/* ------------------------------ 块级解析主循环 ------------------------------ */

/** 是否为块级起始行（段落收集时用于判断段落终止） */
const isBlockStart = (line: string, lines: string[], idx: number): boolean => {
  if (/^\s*(```|~~~)/.test(line)) return true;
  if (/^ {0,3}#{1,6}\s/.test(line)) return true;
  if (/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line)) return true;
  if (/^\s*>/.test(line)) return true;
  if (/^\s*([-*+])\s+/.test(line)) return true;
  if (/^\s*\d+[.)]\s+/.test(line)) return true;
  if (line.trimStart().startsWith("|")) return isTableSeparator(lines[idx + 1]);
  return false;
};

/** 将 Markdown 文本解析为块级 HTML（未消毒；引用内部递归处理嵌套块） */
const renderBlocks = (text: string): string => {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const n = lines.length;
  let html = "";
  let i = 0;

  while (i < n) {
    const line = lines[i];

    if (line.trim() === "") {
      i++;
      continue;
    }

    // 1. 代码块 ``` / ~~~
    if (/^\s*(```|~~~)/.test(line)) {
      const fence = line.trimStart().startsWith("```") ? "```" : "~~~";
      const buf: string[] = [];
      i++;
      while (i < n && !new RegExp(`^\\s*${fence}`).test(lines[i])) {
        buf.push(lines[i]);
        i++;
      }
      i++; // 跳过闭合 fence（未闭合时越过尾部，循环自然终止）
      html += `<pre style="${PRE_STYLE}"><code style="${PRE_CODE_STYLE}">${escapeHtml(
        buf.join("\n")
      )}</code></pre>`;
      continue;
    }

    // 2. GFM 表格（| 表头 + |---| 分隔行）
    if (line.trimStart().startsWith("|") && isTableSeparator(lines[i + 1])) {
      const headerCells = splitRow(line);
      const sepCells = splitRow(lines[i + 1]);
      const aligns = sepCells.map((c) => {
        const t = c.trim();
        if (t.startsWith(":") && t.endsWith(":") && t.length > 1) return "center";
        if (t.endsWith(":")) return "right";
        return "left";
      });
      i += 2;
      const bodyRows: string[][] = [];
      while (i < n && lines[i].trim() !== "" && lines[i].trimStart().startsWith("|")) {
        bodyRows.push(splitRow(lines[i]));
        i++;
      }
      html += buildTable(headerCells, aligns, bodyRows);
      continue;
    }

    // 3. 标题 # ~ ######
    const h = line.match(/^ {0,3}(#{1,6})\s+(.*)$/);
    if (h) {
      const level = h[1].length;
      html += `<h${level} style="${H_STYLE[level] || H_STYLE[6]}">${inline(h[2])}</h${level}>`;
      i++;
      continue;
    }

    // 4. 水平分割线 --- / *** / ___
    if (/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      html += `<hr style="${HR_STYLE}">`;
      i++;
      continue;
    }

    // 5. 引用 >（内部递归支持嵌套块）
    if (/^\s*>/.test(line)) {
      const buf: string[] = [];
      while (i < n && /^\s*>/.test(lines[i])) {
        buf.push(lines[i].replace(/^\s*>\s?/, ""));
        i++;
      }
      html += `<blockquote style="${QUOTE_STYLE}">${renderBlocks(
        buf.join("\n")
      )}</blockquote>`;
      continue;
    }

    // 6. 列表（有序 / 无序，支持缩进嵌套）
    const ul = line.match(/^(\s*)([-*+])\s+(.*)$/);
    const ol = line.match(/^(\s*)(\d+)[.)]\s+(.*)$/);
    if (ul || ol) {
      const items: ListItem[] = [];
      while (i < n) {
        const q = lines[i];
        const su = q.match(/^(\s*)([-*+])\s+(.*)$/);
        const so = q.match(/^(\s*)(\d+)[.)]\s+(.*)$/);
        if (!su && !so) break;
        const m = su || so;
        items.push({
          indent: m[1].replace(/\t/g, "  ").length,
          ordered: !!so,
          text: m[3],
          children: [],
        });
        i++;
      }
      html += parseList(items);
      continue;
    }

    // 7. 普通段落（空行或下一块级行终止，单换行 <br/>）
    const buf: string[] = [line];
    i++;
    while (i < n && lines[i].trim() !== "" && !isBlockStart(lines[i], lines, i)) {
      buf.push(lines[i]);
      i++;
    }
    html += `<p>${buf.map((l) => inline(l.trim())).join("<br/>")}</p>`;
  }

  return html;
};

/* ------------------------------ 导出 ------------------------------ */

/**
 * 将 Markdown 片段转换为安全 HTML，并用 DOMPurify 消毒（防 XSS）。
 * 输出无外层包裹标签（由调用容器提供 class="aipm-md" 命中作用域 CSS）。
 * 用于 Agent 运行结果、文档、知识库预览等 Markdown 渲染。
 */
export function renderMarkdownToHtml(md: string): string {
  if (!md) return "";
  const html = renderBlocks(md);
  // 链接已限 http/https；DOMPurify 默认 URI 净化进一步拦截 javascript: 等危险协议
  return DOMPurify.sanitize(html, { ADD_ATTR: ["target", "rel"] });
}

/**
 * .aipm-md 作用域样式（与上方内联兜底样式视觉一致）。
 * 与 styles/global.css 末尾的同名样式块内容保持一致，
 * 供需要以 <style> 注入的场景（如独立弹窗/微前端）使用。
 */
export const MD_CSS: string = `
/* .aipm-md — Markdown 渲染样式（Agent 输出 / 文档 / 知识库预览共用） */
.aipm-md { font-size: 14px; color: #334155; }
.aipm-md > :first-child { margin-top: 0; }
.aipm-md h1 { font-size: 20px; font-weight: 700; color: #0F172A; margin: 18px 0 8px; }
.aipm-md h2 { font-size: 18px; font-weight: 700; color: #0F172A; margin: 16px 0 8px; }
.aipm-md h3 { font-size: 16px; font-weight: 600; color: #0F172A; margin: 14px 0 6px; }
.aipm-md h4 { font-size: 15px; font-weight: 600; color: #0F172A; margin: 12px 0 6px; }
.aipm-md h5 { font-size: 14px; font-weight: 600; color: #0F172A; margin: 10px 0 4px; }
.aipm-md h6 { font-size: 13px; font-weight: 600; color: #475569; margin: 10px 0 4px; }
.aipm-md p { margin: 8px 0; }
.aipm-md ul, .aipm-md ol { margin: 8px 0; padding-left: 22px; }
.aipm-md ul { list-style: disc; }
.aipm-md ol { list-style: decimal; }
.aipm-md li { margin: 4px 0; }
.aipm-md li > ul, .aipm-md li > ol { margin: 4px 0; }
.aipm-md blockquote { margin: 10px 0; }
.aipm-md blockquote blockquote { margin: 6px 0; }
.aipm-md hr { margin: 16px 0; }
.aipm-md table { width: 100%; }
.aipm-md th, .aipm-md td { text-align: left; }
.aipm-md tbody tr:nth-child(even) td { background: #F8FAFC; }
.aipm-md code { font-family: Consolas, 'SFMono-Regular', Menlo, monospace; }
.aipm-md pre { margin: 10px 0; }
.aipm-md a { color: #4F46E5; text-decoration: none; }
.aipm-md a:hover { text-decoration: underline; }
`;
