# 从你实际使用的系统导出一次运行

打分器只需要每张认领单一行 JSON，里面是排好序的结果：

```json
{"ticket": "t07", "hits": [{"path": "notes/workshop.md", "lines": [14, 17], "page": null, "text": "...", "score": 4.2}]}
```

让运行保持诚实的规则：

- 调用智能体使用的**同一条**搜索路径，用**同样的**设置和过滤条件。专门为这次测试另建一个索引，测到的是那个索引，而不是智能体。
- 按原样发送认领单的 `ask`。不要改写，除非查询改写本身就是系统的一部分；那就按系统的方式改写，并把改写后的文本以 `"query"` 记在结果里。
- 请求的结果条数要多于 k（比如 20 条），打分器才能区分**埋没**和**丢失**。
- `path` 要相对于和认领单相同的根目录。把反斜杠统一成正斜杠。
- 每种配置一个文件，放在 `runs/` 下，以改动命名（`c0-baseline.jsonl`、`c3-hybrid.jsonl`）。永不覆盖。

## 方式 1：由智能体驱动的 MCP 搜索工具

当通往索引的唯一入口是一个 MCP 工具时，让智能体来跑循环，但要让它机械地执行：

1. 读取 `tickets.practice.jsonl`。
2. 对每张认领单，用 `ask` 作为查询调用一次搜索工具，结果条数取工具允许的最大值（最多 20）。
3. 每张认领单往 `runs/<名称>.jsonl` 写一行，把工具返回的结果映射成 `path`、`lines` 或 `page`、`text` 和 `score`。照抄数值；导出时不要评判相关性。
4. 不要因为结果"看起来不对"就重试某张单。重试就等于换了一个系统。

## 方式 2：HTTP 搜索 API（Elasticsearch 风格或类似）

```python
import json, urllib.request

def search(q, size=20):
    body = json.dumps({"size": size, "query": {"match": {"content": q}}}).encode()
    req = urllib.request.Request("http://localhost:9200/notes/_search", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)["hits"]["hits"]

with open("tickets.practice.jsonl") as fh, open("runs/c0.jsonl", "w") as out:
    for line in fh:
        t = json.loads(line)
        hits = [{"path": h["_source"]["path"],
                 "lines": h["_source"].get("lines"),
                 "text": h["_source"].get("content", "")[:2000],
                 "score": h["_score"]} for h in search(t["ask"])]
        out.write(json.dumps({"ticket": t["id"], "hits": hits}, ensure_ascii=False) + "\n")
```

把查询体换成智能体实际发送的内容（混合检索、过滤条件、重排块）。不同索引的字段名不同；做映射，不要去改索引名。

## 方式 3：SQLite FTS5

```python
import json, sqlite3
db = sqlite3.connect("notes.db")
q = "\"E-217\""  # 查询词，按智能体的方式加引号
rows = db.execute("SELECT path, start_line, end_line, body, bm25(chunks) AS s "
                  "FROM chunks WHERE chunks MATCH ? ORDER BY s LIMIT 20", (q,)).fetchall()
hits = [{"path": p, "lines": [a, b], "text": body, "score": -s} for p, a, b, body, s in rows]
```

FTS5 的查询语法会把某些标点当作运算符。如果智能体会转义或加引号，这里也要照做，并记录下来：没转义的 `E-217` 这类编码是**编码被拆坏**的典型原因。

## 方式 4：向量库客户端

用智能体使用的**同一个**模型、同样的前缀或指令串来嵌入 `ask`（很多嵌入模型要求加 "query:" 之类的前缀，漏掉前缀会悄无声息地拉低分数）。建索引时把切块的源路径和行号范围存为元数据；没有这些，你就只能用引文来钉认领单。

## 方式 5：智能体记忆召回

把每条记忆条目当作一条结果，`path` 设为稳定的条目 id 或 `memory/<命名空间>/<id>`，`text` 设为条目正文。`newest-wins` 单钉在当前条目上；旧条目排在它前面时，解剖结论就是**旧副本**。

## 方式 6：完全接触不到代码

在产品自带的搜索框里提问，每道题把前 10 条结果（文件名和章节）记到表格里，一张认领单一行。之后把表格转成 JSONL，或者手工打分：hit@k 就是"前 k 行里有没有钉住的位置"，RR 就是"1 / 第一个钉住位置所在的行号"。
