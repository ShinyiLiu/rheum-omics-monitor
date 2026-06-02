# GitHub Actions 云端定时发送配置

这个仓库可以通过 GitHub Actions 在云端每两周左右发送一次风湿免疫单细胞/空间转录组公共数据报告。本地电脑不需要开机。

## 1. 仓库内容

云端运行需要以下文件：

- `.github/workflows/rheum-omics-monthly.yml`
- `rheum_omics_monitor/monitor.py`
- `rheum_omics_monitor/README.md`
- `rheum_omics_monitor/.env.example`
- `.gitignore`

不要上传 `rheum_omics_monitor/.env`、`reports/`、`seen_accessions.json`。

## 2. 配置 QQ 邮箱 Actions Secrets

腾讯企业邮箱不是普通 QQ 邮箱。当前 workflow 默认使用普通 QQ 邮箱 SMTP：`smtp.qq.com:465`。

你需要在 QQ 邮箱网页端开启 SMTP 服务，并生成授权码。密码不要填 QQ 登录密码，要填 QQ 邮箱授权码。

在 GitHub 仓库页面进入：

`Settings -> Secrets and variables -> Actions -> New repository secret`

添加以下 3 个 secret：

```text
SMTP_USER=你的QQ邮箱地址，例如 123456@qq.com
SMTP_AUTH_CODE=你的QQ邮箱SMTP授权码
REPORT_TO_EMAIL=接收报告的邮箱
```

可选覆盖项：如果以后改用腾讯企业邮箱，可以额外添加：

```text
SMTP_HOST=smtp.exmail.qq.com
SMTP_PORT=465
```

## 3. NCBI 限流缓解

GitHub Actions 使用共享云端 IP，偶尔会遇到 NCBI `HTTP 429 Too Many Requests`。脚本已经加入限速和退避重试；如果仍频繁出现，可以额外添加：

```text
NCBI_EMAIL=你的联系邮箱
NCBI_API_KEY=你的 NCBI API key
```

`NCBI_API_KEY` 不是必须项，但能提高 NCBI E-utilities 的稳定性。

## 4. 定时规则

workflow 已配置：

```yaml
cron: "0 1 1,15 * *"
```

GitHub Actions 的 cron 使用 UTC 时间。这个规则对应北京时间每月 1 日和 15 日 09:00。每次检索最近 14 天，并把每个数据源请求上限降为 40 条。

## 5. 手动测试

在 GitHub 仓库页面进入：

`Actions -> Rheum omics biweekly report -> Run workflow`

手动运行一次。运行成功后，邮箱应收到报告。

如果失败，先看失败 step：

- `Validate email secrets`：说明 secret 名称缺失或写错。
- `Check SMTP login`：说明 QQ 邮箱 SMTP 连接或授权码登录失败。
- `Send biweekly report`：说明检索或正式发信阶段失败。

## 6. 注意事项

- GitHub Actions 定时任务可能有几分钟延迟。
- 如果仓库长期无活动，GitHub 可能暂停 scheduled workflow；进入 Actions 页面可重新启用。
- 当前脚本不下载 FASTQ，不做下游分析，只检索元数据并发送邮件。
