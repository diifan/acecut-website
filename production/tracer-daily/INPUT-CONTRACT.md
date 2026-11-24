## 主控接入接口与真实发布状态

真实新增发布 **0**。没有创建新生产部署或推送GitHub。已暂停的50个视频标题草稿保留在运行目录 paused-video-title-batch-20261124，不进入构建，也不能通过发布闸门。

固定输入（每次prepare重读最新内容，不锁死首次空文件哈希）：
- /data/swi-algo/Swi-App-Factory/Acecut/production/keyword-expansion/keywords.csv
- /data/swi-algo/Swi-App-Factory/Acecut/production/keyword-expansion/manifest.json

CSV：keyword,status,url,batch_id,source,volume,kd,evidence_url,metric_timestamp,source_sha256。
manifest：app=acecut,sport=tennis,sources=[{path,sha256,rows}]，累积原始导出。
执行器核对原始CSV哈希、词/指标/evidence_url/日期，严格KD<30、volume>100；抓取evidence_url，验证网球上下文、词意图/来源对齐及重复意图。source是原始CSV，不能作为网页URL。消费/预留/发布状态仅写独立 keyword-pool.sqlite，不回写主控CSV。

按授权只向主控目录写 capacity.json：checked_at=Unix秒、eligible_available=扣除占用及重复slug后、来源验证通过的可用词数。
唯一日常配置仍为 /data/swi-algo/Swi-IP-Config/swie-app-mac/data/tracer-daily-acecut/config.json。keyword-input.json仅登记固定输入路径，每轮生成当前内容哈希以校验一致性。

主控2026-11-24已确认Semrush返回-32107 Report limits exceeded，采集器正常6小时冷却；本执行器不强制重试、不修改扩充器或MAC界面/API。空池状态为 insufficient_keywords，并记录source_quota_blocked；绝不标成已准备上线。
