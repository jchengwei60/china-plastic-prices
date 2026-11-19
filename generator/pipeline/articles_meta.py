"""Metadata for the site's articles, used by the article entry points
on the homepage and variety pages (pipeline/article_links.py).

One tuple per article: (path, title, date, category, variety slugs).
Keep the list newest-first. When a new article is published, add its
template under the bundle templates and one line here — the homepage
shows the newest 4, and each variety page shows the articles tagged
with its slug (guides have no slug: they are the general fill).
"""

ARTICLES = [
    ("/articles/2026-10-pp-hormuz-soften/",
     "霍尔木兹流量腰斩，PP现货先松了：拉丝10733我不追",
     "2026-10-21", "塑料行情周报", ("pp",)),
    ("/articles/guide-price-clause/",
     "采购合同里的原料调价条款怎么写？涨跌多少才调、谁来担（附条款示例）",
     "2026-10-20", "采购干货", ()),
    ("/articles/2026-10-pp-basis-weekly/",
     "PP价格10月19日：现货涨期货跌，基差1557我不追",
     "2026-10-19", "塑料行情周报", ("pp",)),
    ("/articles/2026-10-pp-import-vs-domestic/",
     "PP价格10月16日：基准价10657元，进口料到厂价算下来，比国产便宜还是贵？",
     "2026-10-16", "塑料行情周报", ("pp",)),
    ("/articles/2026-10-pvc-export-policy/",
     "PVC价格10月15日：SG-5基准价4868元，欧盟印度都在查中国PVC，管材厂要多备料吗？",
     "2026-10-15", "政策与产能", ("pvc",)),
    ("/articles/guide-tax-price/",
     "塑料原料含税价和不含税价怎么换算？开13%、3%、1%的票，成本差多少",
     "2026-10-15", "采购干货", ()),
    ("/articles/2026-10-pe-new-capacity/",
     "PE价格10月14日：LLDPE报9942元，一个月涨475，吹膜厂补多少够？",
     "2026-10-14", "采购干货", ("lldpe", "hdpe", "ldpe")),
    ("/articles/2026-10-pp-t30s-lock/",
     "PP价格10月13日：高位该一次锁一个月，还是分4批买？89天回测",
     "2026-10-13", "品种专题", ("pp",)),
    ("/articles/guide-injection-part-cost/",
     "注塑件原料成本怎么算？克重、水口料、色母、损耗一步步算到每件",
     "2026-10-13", "采购干货", ()),
    ("/articles/2026-10-weekly-1/",
     "塑料价格周报10月12日：PP一周涨650元，为什么涨、现在补不补？",
     "2026-10-12", "塑料行情周报", ()),
    ("/articles/2026-10-cost-after-holiday/",
     "塑料价格10月10日：节后PP涨437元/吨，1万个餐盒多花90元",
     "2026-10-10", "塑料行情周报", ("pp",)),
    ("/articles/2026-10-ldpe-spread/",
     "PE价格：高压比线性贵近2800元，吹膜厂该怎么调配比？",
     "2026-10-10", "品种专题", ("ldpe", "lldpe", "hdpe")),
    ("/articles/2026-10-raise-price/",
     "PP价格三个月涨20%，怎么跟客户开口提价？附调价函模板",
     "2026-10-10", "采购干货", ("pp",)),
    ("/articles/2026-10-overseas-lldpe/",
     "塑料行情海外篇：同是LLDPE，远东和孟加拉相差200美元以上",
     "2026-10-09", "海外行情", ("lldpe",)),
    ("/articles/2026-10-pp-why-up/",
     "PP为什么一年涨这么多？还能涨多久？PP价格行情深度解析",
     "2026-10-08", "品种专题", ("pp",)),
    ("/articles/2026-10-global-outlook/",
     "油价百元拉锯，塑料原料“成本推、需求拖”——全球10月行情速览",
     "2026-10-07", "行情周报", ()),
]
