# GitHub Actions 云端定时发送配置

这个仓库可以通过 GitHub Actions 在云端每月发送一次风湿免疫单细胞/空间转录组公共数据报告。本地电脑不需要开机。

## 1. 仓库内容

云端运行需要以下文件：

- `.github/workflows/rheum-omics-monthly.yml`
- `rheum_omics_monitor/monitor.py`
- `rheum_omics_monitor/README.md`
- `rheum_omics_monitor/.env.example`
- `.gitignore`

不要上传 `rheum_omics_monitor/.env`、`reports/`、`seen_accessions.json`。

## 2. 配置 Actions Secrets

在 GitHub 仓库页面进入：

`Settings -> Secrets and variables -> Actions -> New repository secret`

只需要添加以下 3 个 secret：

```text
SMTP_USER=你的163邮箱
SMTP_AUTH_CODE=你的163客户端授权码
REPORT_TO_EMAIL=接收报告的邮箱
```

workflow 已固定使用 163 默认 SMTP 设置：`smtp.163.com:465`。`SMTP_AUTH_CODE` 使用 163 客户端授权码，不使用邮箱登录密码。

## 3. 定时规则

workflow 已配置：

```yaml
cron: "0 1 1 * *"
```

GitHub Actions 的 cron 使用 UTC 时间。这个规则对应北京时间每月 1 日 09:00。

## 4. 手动测试

在 GitHub 仓库页面进入：

`Actions -> Rheum omics monthly report -> Run workflow`

手动运行一次。运行成功后，邮箱应收到报告。

如果失败，先看失败 step：

- `Validate email secrets`：说明 secret 名称缺失或写错。
- `Check SMTP login`：说明 163 SMTP 连接或授权码登录失败。
- `Send monthly report`：说明检索或正式发信阶段失败。

## 5. 注意事项

- GitHub Actions 定时任务可能有几分钟延迟。
- 如果仓库长期无活动，GitHub 可能暂停 scheduled workflow；进入 Actions 页面可重新启用。
- 当前脚本不下载 FASTQ，不做下游分析，只检索元数据并发送邮件。
