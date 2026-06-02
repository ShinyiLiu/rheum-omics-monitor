# 风湿免疫单细胞/空间转录组公共数据监控

这个目录提供一个每月运行的监控脚本，用于检索公共数据库中和风湿免疫相关的单细胞转录组、单核转录组、空间转录组数据集，并通过 163 SMTP 发送邮件月报。

## 配置 163 邮箱

1. 登录 `mail.163.com`。
2. 在邮箱设置中开启 POP3/SMTP/IMAP 服务。
3. 生成客户端授权码。
4. 复制 `.env.example` 为 `rheum_omics_monitor/.env`，填写邮箱和授权码。`SMTP_AUTH_CODE` 使用授权码，不使用邮箱登录密码。

`.env` 配置示例：

```dotenv
SMTP_HOST=smtp.163.com
SMTP_PORT=465
SMTP_USER=your_name@163.com
SMTP_AUTH_CODE=your_163_client_authorization_code
REPORT_TO_EMAIL=your_name@163.com
```

发送 SMTP 测试邮件：

```powershell
python .\rheum_omics_monitor\monitor.py --test-email
```

## 手动运行

只生成报告，不发邮件：

```powershell
python .\rheum_omics_monitor\monitor.py --since-days 35 --include-seen
```

生成报告并发邮件：

```powershell
python .\rheum_omics_monitor\monitor.py --since-days 35 --send-email
```

报告会写入 `rheum_omics_monitor/reports/`。脚本会维护 `seen_accessions.json`，默认邮件只发送首次发现的数据集。

## GitHub Actions 云端运行

仓库根目录已包含 `.github/workflows/rheum-omics-monthly.yml`，可以在 GitHub Actions 云端每月 1 日北京时间 09:00 自动运行。

云端运行时不要上传 `.env`，而是在 GitHub 仓库的 Actions Secrets 中配置：

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_AUTH_CODE`
- `REPORT_TO_EMAIL`

详细步骤见仓库根目录的 `GITHUB_DEPLOYMENT.md`。

## 当前检索源

- NCBI GEO
- NCBI SRA
- ENA
- CELLxGENE Discover

脚本会先用数据库接口拉取候选记录，再在本地用风湿免疫疾病关键词和单细胞/空间转录组关键词二次过滤，避免把 bulk RNA-seq 混入报告。
