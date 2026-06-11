# 风湿免疫单细胞/空间转录组公共数据监控

这个目录提供一个双周运行的监控脚本，用于检索公共数据库中和风湿免疫相关的单细胞转录组、单核转录组、空间转录组数据集，并通过 QQ 邮箱 SMTP 发送邮件报告。报告会保留英文原始标题，并在下方附中文标题辅助阅读。

## 配置 QQ 邮箱

1. 登录 QQ 邮箱网页版。
2. 在邮箱设置中开启 POP3/SMTP/IMAP 服务。
3. 生成 SMTP 授权码。
4. 复制 `.env.example` 为 `rheum_omics_monitor/.env`，填写邮箱和授权码。`SMTP_AUTH_CODE` 使用授权码，不使用邮箱登录密码。

`.env` 配置示例：

```dotenv
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=your_name@qq.com
SMTP_AUTH_CODE=your_qq_smtp_authorization_code
REPORT_TO_EMAIL=your_name@qq.com
```

可选配置，用于降低 NCBI 429 限流概率：

```dotenv
NCBI_EMAIL=your_contact_email@example.com
NCBI_API_KEY=your_ncbi_api_key
```

发送 SMTP 测试邮件：

```powershell
python .\rheum_omics_monitor\monitor.py --test-email
```

## 手动运行

只生成报告，不发邮件：

```powershell
python .\rheum_omics_monitor\monitor.py --since-days 14 --include-seen
```

生成报告并发邮件：

```powershell
python .\rheum_omics_monitor\monitor.py --since-days 14 --send-email
```

报告会写入 `rheum_omics_monitor/reports/`。脚本会维护 `seen_accessions.json`，默认邮件只发送首次发现的数据集。

脚本还会维护两个 CSV 台账：

- `data/rheum_omics_all_datasets.csv`：全量长期台账，包含既往邮件和最新运行发现过的所有数据集。
- `data/rheum_omics_latest_email_datasets.csv`：本次邮件实际发送的新数据集列表，也会作为 CSV 附件随邮件发送；如果本次没有新增数据集，则只包含表头。

如需覆盖默认路径，可使用 `--registry-file` 指定全量台账路径，用 `--latest-file` 指定邮件附件 CSV 路径。

## GitHub Actions 云端运行

仓库根目录已包含 `.github/workflows/rheum-omics-monthly.yml`，可以在 GitHub Actions 云端每月 1 日和 15 日北京时间 09:00 自动运行，每次检索过去 14 天。

云端运行时不要上传 `.env`，而是在 GitHub 仓库的 Actions Secrets 中配置：

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_AUTH_CODE`
- `REPORT_TO_EMAIL`
- `NCBI_EMAIL`（可选）
- `NCBI_API_KEY`（可选）

详细步骤见仓库根目录的 `GITHUB_DEPLOYMENT.md`。

## 当前检索源

- NCBI GEO
- NCBI SRA
- ENA
- CELLxGENE Discover

脚本会先用数据库接口拉取候选记录，再在本地用风湿免疫疾病关键词和单细胞/空间转录组关键词二次过滤，避免把 bulk RNA-seq 混入周报。
