# GitHub Actions 云端定时发送配置

这个仓库可以通过 GitHub Actions 在云端每月 1 日和 15 日发送一次风湿免疫单细胞/空间转录组公共数据报告。本地电脑不需要开机。

## 1. 创建私有仓库

建议创建 GitHub 私有仓库，然后把当前工作区中这些内容上传：

- `.github/workflows/rheum-omics-monthly.yml`
- `data/rheum_omics_all_datasets.csv`
- `data/rheum_omics_latest_email_datasets.csv`
- `rheum_omics_monitor/monitor.py`
- `rheum_omics_monitor/README.md`
- `rheum_omics_monitor/.env.example`
- `rheum_omics_monitor/seen_accessions.json`
- `.gitignore`

不要上传 `rheum_omics_monitor/.env`、`rheum_omics_monitor/reports/`、临时测试文件或本地克隆目录。

## 2. 配置 Actions Secrets

在 GitHub 仓库页面进入：

`Settings -> Secrets and variables -> Actions -> New repository secret`

添加以下 3 个必需 secret：

```text
SMTP_USER=你的QQ邮箱
SMTP_AUTH_CODE=你的QQ邮箱SMTP授权码
REPORT_TO_EMAIL=接收报告的邮箱
```

workflow 默认使用 `smtp.qq.com:465`。如需覆盖，可额外添加：

```text
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
```

`SMTP_AUTH_CODE` 使用 QQ 邮箱生成的 SMTP 授权码，不使用邮箱登录密码。

为降低 NCBI 429 限流概率，建议额外添加：

```text
NCBI_EMAIL=你的联系邮箱
NCBI_API_KEY=你的NCBI API key
```

`NCBI_API_KEY` 不是必需项；没有时脚本仍会运行，并带有退避重试。

## 3. 定时规则

workflow 已配置：

```yaml
cron: "0 1 1,15 * *"
```

GitHub Actions 的 cron 使用 UTC 时间。这个规则对应北京时间每月 1 日和 15 日 09:00。每次报告默认检索过去 14 天。

## 4. 手动测试

上传后，在 GitHub 仓库页面进入：

`Actions -> Rheum omics biweekly report -> Run workflow`

手动运行一次。运行成功后，邮箱应收到报告。

邮件正文会列出本次新增候选数据集，并附带 `rheum_omics_latest_email_datasets.csv`。仓库中的 `data/rheum_omics_all_datasets.csv` 是长期全量台账，会累计既往邮件和最新运行发现过的所有数据集；`data/rheum_omics_latest_email_datasets.csv` 只保留最近一次邮件实际发送的数据集。

## 5. 注意事项

- GitHub Actions 定时任务可能有几分钟延迟。
- 如果仓库长期无活动，GitHub 可能暂停 scheduled workflow；进入 Actions 页面可重新启用。
- 当前脚本不下载 FASTQ，不做下游分析，只检索元数据并发送邮件。
- GitHub Actions 会在定时或手动发送邮件成功后自动提交 `data/rheum_omics_all_datasets.csv`、`data/rheum_omics_latest_email_datasets.csv` 和 `rheum_omics_monitor/seen_accessions.json` 的变化。
- 如果报告底部出现 NCBI 429 警告，表示 NCBI 临时限流；脚本会自动重试，下一次双周运行通常会恢复。
