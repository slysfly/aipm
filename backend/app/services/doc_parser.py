"""
PMI中国AI项目管理社区 - 多格式文档文本提取
支持：txt/md/csv/json/html/xml/代码类（纯文本）、docx、pptx、xlsx、pdf
尽量仅依赖标准库 + openpyxl（环境已具备），pdf 优先尝试 pypdf/PyPDF2。
任何解析失败都降级为"尽力解码"，保证批量上传不中断。
"""

import io
import zipfile
import re
from xml.etree import ElementTree as ET
from html.parser import HTMLParser

# 纯文本类扩展名（直接按 utf-8 解码即可）
_TEXT_EXT = {
    "txt", "text", "md", "markdown", "csv", "tsv", "json", "log", "xml",
    "html", "htm", "yaml", "yml", "py", "js", "jsx", "ts", "tsx", "java",
    "c", "cpp", "h", "hpp", "go", "rs", "sql", "toml", "ini", "cfg",
    "sh", "bash", "bat", "ps1", "r", "php", "rb", "swift", "kt", "scala",
    "tex", "rst", "gitignore", "env",
}


class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        if data and data.strip():
            self.parts.append(data.strip())

    def handle_starttag(self, tag, attrs):
        # 块级标签之间加换行，保持段落结构
        if tag in ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section"):
            self.parts.append("\n")


def _extract_html(raw: bytes) -> str:
    try:
        s = _HTMLStripper()
        s.feed(raw.decode("utf-8", errors="ignore"))
        text = "\n".join(s.parts)
        return re.sub(r"\n{3,}", "\n\n", text).strip()
    except Exception:
        return raw.decode("utf-8", errors="ignore")


def _extract_docx(raw: bytes) -> str:
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        xml = z.read("word/document.xml")
    root = ET.fromstring(xml)
    texts = []
    for t in root.iter(ns + "t"):
        if t.text:
            texts.append(t.text)
        # 处理换行符 <w:br/> 与段落 <w:p/>
        if t.tail and t.tail.strip() == "":
            pass
    # 段落分隔
    parts = []
    for p in root.iter(ns + "p"):
        line = "".join(node.text or "" for node in p.iter(ns + "t"))
        parts.append(line)
    return "\n".join(p for p in parts if p.strip())


def _extract_pptx(raw: bytes) -> str:
    ns = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    texts = []
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = sorted(
            n for n in z.namelist()
            if re.match(r"ppt/slides/slide\d+\.xml$", n)
        )
        for name in names:
            try:
                root = ET.fromstring(z.read(name))
            except Exception:
                continue
            slide_texts = [t.text for t in root.iter(ns + "t") if t.text]
            if slide_texts:
                texts.append("\n".join(slide_texts))
    return "\n\n".join(texts)


def _extract_xlsx(raw: bytes) -> str:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    parts = []
    for ws in wb.worksheets:
        rows = []
        for row in ws.iter_rows(values_only=True):
            cells = [str(c) for c in row if c is not None and str(c).strip() != ""]
            if cells:
                rows.append("\t".join(cells))
        if rows:
            parts.append(f"【{ws.title}】\n" + "\n".join(rows))
    return "\n\n".join(parts)


def _extract_pdf(raw: bytes) -> str:
    # 优先 PyMuPDF（fitz）：抽取最稳，支持扫描件/复杂排版；其次 pypdf / PyPDF2
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=raw, filetype="pdf")
        pages = [(p.get_text() or "").strip() for p in doc]
        text = "\n\n".join(p for p in pages if p)
        if text.strip():
            return text
    except Exception:
        pass
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            # 无 PDF 库：尽力抽取可读字符串
            return _fallback_raw(raw)
    try:
        reader = PdfReader(io.BytesIO(raw))
        pages = []
        for p in reader.pages:
            txt = p.extract_text() or ""
            if txt.strip():
                pages.append(txt.strip())
        return "\n\n".join(pages)
    except Exception:
        return _fallback_raw(raw)


def _fallback_raw(raw: bytes) -> str:
    """对二进制做尽力文本抽取（去掉不可打印噪声）。"""
    try:
        text = raw.decode("utf-8", errors="ignore")
    except Exception:
        text = raw.decode("latin-1", errors="ignore")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", " ", text)
    return re.sub(r"\s{3,}", "\n\n", text).strip()


def extract_text(filename: str, raw: bytes) -> str:
    """根据文件扩展名提取纯文本；任何异常都降级为尽力解码。"""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    try:
        if ext in ("docx",):
            return _extract_docx(raw)
        if ext in ("pptx",):
            return _extract_pptx(raw)
        if ext in ("xlsx",):
            return _extract_xlsx(raw)
        if ext in ("pdf",):
            return _extract_pdf(raw)
        if ext in ("html", "htm", "xml"):
            return _extract_html(raw)
        if ext in _TEXT_EXT:
            return raw.decode("utf-8", errors="ignore")
    except Exception:
        pass
    return _fallback_raw(raw)


def is_supported(filename: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in _TEXT_EXT or ext in ("docx", "pptx", "xlsx", "pdf")
