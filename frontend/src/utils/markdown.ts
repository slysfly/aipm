import DOMPurify from "dompurify";

/**
 * 将轻量 Markdown 片段转换为安全 HTML，并用 DOMPurify 消毒（防 XSS）。
 * 支持 #/##/### 标题、**粗体**、`行内代码`、```代码块```、- 列表、换行。
 * 用于 Agent 运行结果的 Markdown 渲染。
 */
export function renderMarkdownToHtml(md: string): string {
  if (!md) return "";
  let html = md
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // 代码块 ```lang ... ```
  html = html.replace(/```[a-zA-Z]*\n([\s\S]*?)```/g, (_m, code) => {
    const safe = (code as string).replace(/\n$/, "");
    return `<pre style="background:#0F172A0D;border-radius:8px;padding:12px;overflow:auto;font-size:13px"><code>${safe}</code></pre>`;
  });

  // 标题
  html = html.replace(/^### (.+)$/gm, '<h4 style="font-size:15px;font-weight:600;margin:14px 0 6px;color:#0F172A">$1</h4>');
  html = html.replace(/^## (.+)$/gm, '<h3 style="font-size:17px;font-weight:700;margin:18px 0 8px;color:#0F172A">$1</h3>');
  html = html.replace(/^# (.+)$/gm, '<h2 style="font-size:21px;font-weight:700;margin:22px 0 10px;color:#0F172A">$1</h2>');

  // 粗体 / 行内代码
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/`([^`\n]+?)`/g, '<code style="background:#0F172A0D;border-radius:4px;padding:1px 5px;font-size:0.9em">$1</code>');

  // 列表块：连续的 "- " 行包进一个 <ul>
  html = html.replace(/(?:^[ \t]*- .*(?:\n|$))+/gm, (block) => {
    const items = block.trim().split("\n").map((line) => {
      const t = line.replace(/^[ \t]*- /, "");
      return `<li style="margin:4px 0;padding-left:6px;list-style-type:disc;margin-left:18px">${t}</li>`;
    }).join("");
    return `<ul style="margin:8px 0;padding:0">${items}</ul>`;
  });
  html = html.replace(/<\/li>\n<li>/g, "</li><li>");

  // 段落 / 换行
  html = html.replace(/\n{2,}/g, "</p><p style='margin:8px 0'>");
  html = html.replace(/\n/g, "<br/>");
  html = `<p style="margin:8px 0">${html}</p>`;

  return DOMPurify.sanitize(html);
}
