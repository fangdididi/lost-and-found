# 完整演练：Kestrel Bikes 员工笔记

一家虚构的小自行车店把员工知识放在一个文件夹里：退货政策、保修页面、车间笔记、收银系统错误日志，以及一份中文门店须知。店里的助手智能体在这个文件夹里搜索，回答员工问题前**只读第一条结果**。下面的每一步都可以在仓库根目录重跑。

文件：`examples/tiny-corpus/`（语料）和 `examples/tickets.jsonl`（12 张认领单）。语料和问题本身是英文为主、夹带两道中文题，用来展示混合语言的情况。

> 12 张认领单只是演示，不是正式测量。真实运行需要 30 到 60 张查找单。辅助脚本每次打分都会提醒这一点（"THIN SET"，样本过少）。

## 1. 范围说明

```
被测系统：  在 examples/tiny-corpus 上做关键词搜索，4 行一块，重叠 1 行
语料：      全部员工笔记，不排除任何内容
读取深度：  k = 1（智能体只根据第一条结果作答）
答案单位：  对的章节（用引文钉位置）
未命中代价：员工给客户错误的退款或保修答复
```

## 2. 认领单

11 张查找单和 1 张空单。标签覆盖同义词、改述、精确错误码、日志文件、两处答案和两道中文题。示例行：

```json
{"id": "t03", "ask": "what does E-217 mean", "where": [{"path": "errors.log", "quote": "E-217 card reader lost pairing"}], "tags": ["exact-code", "log"], "kind": "find"}
{"id": "t08", "ask": "Are refunds for faulty items handled under the returns policy?", "where": [{"path": "returns.md", "quote": "see warranty.md instead"}, {"path": "warranty.md", "quote": "To start a claim"}], "tags": ["two-places"], "kind": "find"}
{"id": "t09", "ask": "周一开门吗", "where": [{"path": "notes/门店须知.md", "quote": "周一闭店盘点"}], "tags": ["chinese"], "kind": "find"}
{"id": "t12", "ask": "Do you sell gift cards?", "where": [], "tags": ["absent"], "kind": "none"}
```

```
$ python3 scripts/laf.py check examples/tickets.jsonl --root examples/tiny-corpus
12 tickets (11 find, 1 none)
tags: synonym=2, paraphrase=2, log=2, direct=2, chinese=2, exact-code=1, two-places=1, absent=1
corpus: 5 text files read, 0 skipped
OK: no problems found
```

只有 12 张单，所以演示跳过了练习/封存拆分。真实认领单这样拆：

```
$ python3 scripts/laf.py split tickets.jsonl --practice tickets.practice.jsonl --sealed tickets.sealed.jsonl
```

## 3. 货架清点

| 类型 | 磁盘上 | 已索引 | 差额 |
|---|---|---|---|
| .md | 4 | 4 | 0 |
| .log | 1 | 1 | 0 |

没有 PDF，没有被跳过的文件，索引基于当前文件构建。货架上没有要修的。

## 4. 基线

```
$ python3 scripts/laf.py bm25 examples/tickets.jsonl --root examples/tiny-corpus --chunk 4 --overlap 1 --out runs/c0.jsonl
indexed 23 plain chunks (4 lines, 1 overlap); 0 files skipped; run -> runs/c0.jsonl

$ python3 scripts/laf.py score examples/tickets.jsonl runs/c0.jsonl -k 1 --root examples/tiny-corpus
find-tickets 11, none-tickets 1, k=1
hit@1  81.8%  recall@1  81.8%  MRR@1 0.818  nDCG@1 0.818
found 9  buried(below k) 2  lost 0
THIN SET: under 20 find-tickets; one ticket moves hit@k by 5+ points. Read tickets, not decimals.

by tag:
  chinese            n=2   hit@1 100.0%  MRR 1.000
  direct             n=2   hit@1 100.0%  MRR 1.000
  exact-code         n=1   hit@1 100.0%  MRR 1.000
  log                n=2   hit@1 100.0%  MRR 1.000
  paraphrase         n=2   hit@1  50.0%  MRR 0.500
  synonym            n=2   hit@1 100.0%  MRR 1.000
  two-places         n=1   hit@1   0.0%  MRR 0.000

not found in top k:
  t02      buried  first rank 3  tags paraphrase
  t08      buried  first rank 2  tags two-places

none-tickets (should find nothing; review the top hit):
  t12      top notes/workshop.md score 2.3337
```

按张数说：11 张里 9 张排第一。2 张埋没，0 张丢失，说明资料都在货架上，这是排序问题。两道中文题都找到了，因为脚本把中文切成相邻字对（"周一""一闭""闭店"）。

## 5. 解剖

| 认领单 | 原因 | 探测 | 拟议修法 |
|---|---|---|---|
| t08 | 撕裂 | 排第一的是页面引言（第 1-4 行："Returns and refunds ... returns policy"）。规则（"see warranty.md instead"，第 25 行）所在的块已经不带页面标题，所问的词更少。 | 按标题切块，并把标题路径一起索引 |
| t02 | 词语鸿沟 | "Can a customer return a complete bike after three weeks?" 把 "Who can return" 一节排在第一。改用文档原话（"complete bikes days delivery"）再问，正确的块排第一。 | 基于语义的（向量/混合）检索腿，或规定按文档的单位提问 |
| t12 | （空单） | 排第一的是一段只共享常见词的车间内容。智能体读到它可能会编出答案。 | 在信任说明里加回答规则 |

## 6. 改动

```
C1  假设：按标题切块能修好撕裂类未命中（t08）
    改动：--headings（原为普通切块），大小 4，重叠 1
    预期：t08 被修好，没有被弄坏的
```

```
$ python3 scripts/laf.py compare examples/tickets.jsonl runs/c0.jsonl runs/c1.jsonl -k 1
hit@1:  81.8% ->  90.9%   MRR@1: 0.818 -> 0.909
fixed   1   t08
broken  0
rose    0
fell    0
same    10
tickets better 1, worse 0, sign-test p=1.000
Difference could easily be chance on this set; confirm on the sealed half.
```

假设在运行前就写好了，被修好的正是预测的那一张，而且没有弄坏任何一张。在真实认领单上，保留规则要求修好数减弄坏数至少为 2；这里只是演示，所以 C1 *暂时*保留，并标记在下一套更大的认领单上复查。

```
C2  假设：在这里没有必要把 E-217 这类编码整体保留
    改动：--split-codes
    结果：11 张不变，修好 0，弄坏 0  ->  回退（没有收益，也没有保留它的理由）
```

C1 之后，`hit@1` 是 90.9%，`recall@1` 却是 86.4%：t08 有两个答案位置，而一条结果只能装下一个。对这个智能体没关系（一个位置就能回答问题）；如果智能体必须同时引用两页，这就要紧了。

## 7. 信任说明

```
搜索信任说明 - Kestrel 员工笔记，关键词搜索，按标题 4 行切块，k=1，12 张演示单
能稳定找到：     直接提问、errors.log 中的错误码、中文门店须知、目前测过的同义词
找不太稳：       用不同单位表述的期限问题（t02："three weeks" 对 "14 days"）；
                 问退货期限时直接打开 returns.md 的 "Time limits" 一节
找不到：         目前没有已知缺货
不要依赖搜索的事：库存和实时价格（不在这些笔记里）
第一条结果不相关时：回答"员工笔记里没有"，不要拿最接近的段落作答
复查时机：       新增笔记时，或切换到向量/混合检索之前
```

这家店的下一步：从员工的真实提问里把认领单扩到 30 张以上，拆分，然后只在练习半集上用 t02 这类改述题测试混合检索。
