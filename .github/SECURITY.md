# 安全说明

StylePack 是**本地工具**：

- 工作台只监听 `127.0.0.1`，不对外网开放；请勿用端口转发把它暴露到公网
- 模型 API key 只存于 `web/config.local.json`（已被 .gitignore 覆盖），
  页面永不回显、日志与报错会脱敏——但请自行确保该文件不进任何同步盘/备份的公开目录
- 本地语料与生成内容（manuscript/sessions/slots）不入 git 仓库

发现安全问题请勿开公开 issue，通过 [Security Advisories](https://github.com/Yunmoli1/ai-novels-with-stylepack/security/advisories) 联系。
