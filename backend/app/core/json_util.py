"""JSON 操作块抽取工具。

修复旧式贪婪正则 ``re.search(r'\\{.*\\}', ...)`` 会"吞掉"围栏块前后正文的缺陷：
- ``extract_json_blocks``：fence 优先，按 ```json ... ``` / ``` ... ``` 围栏逐块解析；
  若单个围栏块都没解析成功，再对全文做一次贪婪的 ``{..}`` / ``[..]`` 抽取兜底。
- ``strip_json_blocks``：移除文本中的围栏块，返回干净正文（避免 JSON 块裸露在聊天气泡里）。
解析失败的块一律跳过，绝不抛异常。
"""
import json
import re

_FENCE = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL)
_GREEDY = re.compile(r"\{.*\}|\[.*\]", re.DOTALL)


def extract_json_blocks(text: str):
    """从文本中抽取所有合法 JSON 块（list，保留出现顺序）。

    ① fence 优先：先按 ```json ... ``` / ``` ... ``` 围栏逐个抽取并 ``json.loads``；
    ② 若一个围栏块都没成功，再对全文做一次贪婪的 ``{..}`` / ``[..]`` 抽取兜底。
    解析失败的块跳过不报错。
    """
    if not text:
        return []
    blocks = []
    for raw in _FENCE.findall(text):
        piece = raw.strip()
        if not piece:
            continue
        try:
            blocks.append(json.loads(piece))
        except (json.JSONDecodeError, ValueError):
            continue
    if blocks:
        return blocks
    # 兜底：贪婪抽取大括号 / 中括号块
    for raw in _GREEDY.findall(text):
        piece = raw.strip()
        if not piece:
            continue
        try:
            blocks.append(json.loads(piece))
        except (json.JSONDecodeError, ValueError):
            continue
    return blocks


def strip_json_blocks(text: str) -> str:
    """移除文本中的 ```json ... ``` / ``` ... ``` 围栏块，返回干净正文。

    无围栏则原样返回。移除后用空行归一化残留的连续换行。
    """
    if not text:
        return ""
    cleaned, _ = _FENCE.subn("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
