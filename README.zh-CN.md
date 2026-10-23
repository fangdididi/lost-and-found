[English](README.md) | **简体中文**

# Lost and Found（失物招领）

**你的智能体在你自己的文件里搜索时，真的能找到正确的那一段吗？这个智能体技能用"钉在真实位置上的真实问题"来测量它，解释每一次未命中，一次只改一处，最后留下一份智能体可以遵守的信任说明。**

你的编程智能体在改代码前会先搜本地索引；你的客服机器人在帮助中心上跑 RAG；你的助手记着过往的决定。答案出错时，常见的反应是怪模型、换嵌入模型，或者调大 `top_k` 碰运气。这些都没有回答最先该问的问题：*对于我们真正会问的事，正确的那一段有没有送到智能体手里？*

Lost and Found 让智能体在**你的**语料上分七步回答这个问题：

- **范围说明。** 被测的是哪条搜索路径、它的设置，以及智能体实际使用的读取深度 `k`。智能体只读 3 条却按 10 条打分，是在美化系统。
- **认领单。** 真实问题，每个都用路径加行号、页码或一小段引文钉在能回答它的位置上，绝不钉切块 id，这样重新切块后认领单依然有效。按"难在哪"打标签：同义词、精确编码、两处答案、PDF 和日志、以新为准的记忆、其他语言，以及语料里根本没有答案的问题。
- **货架清点。** 实际存在的和被索引的对比：被跳过的类型、没有文字层的扫描版 PDF、忽略规则、大小上限、过期索引、重复或互相矛盾的记忆条目。
- **基线运行。** 导出真实系统排好序的结果，加一把朴素的关键词标尺，按真实的 `k` 计算 hit@k、recall@k、MRR 和 nDCG，分标签统计，并给每张单标出找到 / 埋没 / 丢失。
- **未命中解剖。** 每次未命中都放进九类原因表中的一行（没上架、旧副本、撕裂、淹没、词语鸿沟、编码被拆坏、走错房间、被挤出、标注错误），每类都配一分钟探测和常见修法。
- **一次只改一处。** 先写假设，在练习半集上运行，逐题评判（修好 / 弄坏 / 上升 / 下降，外加精确符号检验），只有每张被弄坏的单都解释清楚才保留，最后在封存半集上确认一次。
- **信任说明。** 一段可以直接贴进智能体指令的文字：能稳定找到什么、找不太稳的是什么以及变通办法、哪些没上架、哪些事绝不能依赖搜索、什么时候应该说"没找到"。

## 功能特性

| | |
|---|---|
| 适用对象 | 本地代码/文档搜索、RAG 管线、向量库、混合检索、MCP 搜索工具、智能体记忆命名空间 |
| 认领单钉法 | `path` + `lines`、`page` 或 `quote`；一张单可以有多个答案位置；空单用来表示"语料里没有" |
| 指标 | hit@k、recall@k、MRR@k、nDCG@k、找到 / 埋没 / 丢失、分标签表、小样本警告 |
| 对比 | 逐题列出修好 / 弄坏 / 上升 / 下降，附精确符号检验 |
| 防过拟合 | 用稳定哈希拆成练习半集和封存半集 |
| 关键词标尺 | 内置的文件夹 BM25：按行窗口或按标题切块，中日韩文字切成字对，`E-217` 这类编码整体保留 |
| 运行导出 | 覆盖 MCP 工具、HTTP 搜索 API、SQLite FTS5、向量库、记忆召回，或者一张普通表格 |
| 辅助脚本 | `scripts/laf.py`，只用 Python 标准库，22 个测试 |
| 隐私 | 全部在本地运行；会提醒哪些重排器和远程嵌入服务会把文本发到本机以外 |
| 双语 | 完整的英文和中文技能文件、参考资料和完整演练 |

## 安装

技能就是包含 `SKILL.md`（英文）和 `SKILL.zh-CN.md`（中文）的那个文件夹。请复制整个文件夹，让 `scripts/`、`references/` 和 `examples/` 一起带上。

**Claude Code**

```bash
git clone https://github.com/fangdididi/lost-and-found.git ~/.claude/skills/lost-and-found
```

**Codex / 读取 `~/.agents/skills` 的智能体**

```bash
git clone https://github.com/fangdididi/lost-and-found.git ~/.agents/skills/lost-and-found
```

**Cursor**（项目技能目录）

```bash
git clone https://github.com/fangdididi/lost-and-found.git .cursor/skills/lost-and-found
```

**其他智能体**（Gemini CLI、GitHub Copilot、OpenCode、Windsurf、Cline、Kimi、各类聊天应用）：把 `SKILL.md` 粘贴进它的指令或项目规则，或者让它从本仓库地址安装技能。中文对话请用 `SKILL.zh-CN.md`。没有命令行就用不了辅助脚本，但方法用表格也能做：每张认领单一行，每行记下前十条结果。

## 使用方法

直接用平常的话提出需求：

- "我们的智能体老说在 `docs/` 里找不到东西。用 lost-and-found 查一下搜索。"
- "我们打算换成混合检索。先在我们自己的问题上测一下到底有没有用。"
- "RAG 总是引用旧版政策，帮我查清原因。"
- "检查一下记忆库想起的是不是最新的决定。"

智能体会写范围说明、和你一起建认领单、清点货架、导出运行、打分、解剖、一次一处地做改动并写信任说明，全部放在项目的 `.lost-and-found/` 文件夹里。

直接使用辅助脚本：

```bash
# 对照语料校验认领单
python3 scripts/laf.py check tickets.jsonl --root path/to/corpus

# 拆分练习 / 封存半集（结果稳定）
python3 scripts/laf.py split tickets.jsonl --practice tickets.practice.jsonl --sealed tickets.sealed.jsonl

# 在文件夹上建立朴素关键词标尺
python3 scripts/laf.py bm25 tickets.practice.jsonl --root path/to/corpus --chunk 20 --overlap 5 --out runs/yardstick.jsonl

# 按智能体实际读取的深度给任意运行打分
python3 scripts/laf.py score tickets.practice.jsonl runs/current.jsonl -k 5 --root path/to/corpus

# 逐题对比改动前后
python3 scripts/laf.py compare tickets.practice.jsonl runs/c1.jsonl runs/c2.jsonl -k 5
```

运行测试：

```bash
python3 -m unittest discover -s tests -v
```

## 示例

一家虚构自行车店的员工笔记、12 张认领单、一个只读第一条结果的智能体：

```
普通 4 行切块        hit@1 9/11   埋没：t02（第 3 名）、t08（第 2 名）
解剖                 t08 撕裂（规则所在的块丢了页面标题），t02 词语鸿沟（"three weeks" 对 "14 days"）
C1 按标题切块        修好 t08，没弄坏任何一张 -> 保留      hit@1 10/11
C2 拆分编码          没有变化 -> 回退
信任说明             "以周为单位提问的期限问题：不稳；直接查 returns.md"
                     "第一条结果不相关：直说没找到"（礼品卡空单）
```

带全部命令和真实输出的完整演练：[`examples/worked-example.zh-CN.md`](examples/worked-example.zh-CN.md)。

## 文件结构

```
lost-and-found/
├── SKILL.md                      # 技能（英文）
├── SKILL.zh-CN.md                # 技能（中文完整版）
├── README.md / README.zh-CN.md
├── LICENSE
├── scripts/
│   └── laf.py                    # check、split、bm25、score、compare（仅标准库）
├── references/
│   ├── exporting-runs.md         # 如何从真实系统导出排好序的结果
│   └── exporting-runs.zh-CN.md
├── examples/
│   ├── tiny-corpus/              # 虚构自行车店笔记（英文 + 一份中文文件）
│   ├── tickets.jsonl             # 12 张示例认领单
│   ├── worked-example.md
│   └── worked-example.zh-CN.md
└── tests/
    └── test_laf.py               # 22 个单元测试
```

## 许可证

MIT，见 [LICENSE](LICENSE)。
