ILANG
[TYPE:agents][PROJECT:mealkitdeals][LANG:zh]

::STATE{@PROJECT, kind:coupon-niche-static-site, runtime:python-stdlib+github-actions+cloudflare-pages}

::OBJECTIVE{maintain_promo_radar}
  target: 保持餐盒优惠垂直站用公开数据自动更新 零服务器 零运行时推理
  ACCEPT: scraper/build 读 .ilang/site.ilang 站能在 Pages 上更新
  NON_GOALS: 编优惠 编价格 编佣金 刷量 运行时调用付费 LLM/API

::MODULE{ALLOWED}
  改 .ilang/site.ilang 增减厂商或抓取入口
  改进 scraper 解析（仍只读公开页 遵守 robots.txt）
  改进 templates / build 的展示与 JSON-LD
  调整 GitHub Actions cron
  绑定自定义域名并更新 site.ilang 的 domain

::MODULE{FORBIDDEN}
  编造优惠名、价格、有效期、佣金比例
  抓登录后内容或绕过反爬
  在代码里硬编码一份与 site.ilang 脱节的厂商清单
  购买粉丝、刷点击、伪造搜索量

::MODULE{DATA}
  真源配置: .ilang/site.ilang
  数据集: data/offers.json（workflow 覆盖）
  页面输出: site/（build.py 生成）

::RULE{抓不到 price⇒不写 price 字段也不进 Offer JSON-LD 的 price}
::RULE{valid_until 过期⇒标 expired 或下架 不许冒充有效}
::BOUNDARY{never:编优惠 编价格 编佣金|scope:permanent}
