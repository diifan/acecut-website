# AceCut Website

AceCut 官网独立维护仓库：https://github.com/diifan/acecut-website

纯 HTML / CSS / JavaScript，Bun 用于本地开发与构建。生产发布仅包含静态文件，不需要运行 Bun 服务。设计来自产品经理提供的 acecut-website.zip，保留原稿布局、图片、文案与交互。

## 本地开发

安装 Bun 1.2+（本地已验证 1.4.3），在本仓库根目录执行：

```sh
bun run dev
# http://localhost:4173

bun run build
bun run preview
```

无需第三方依赖。`public/` 是网站源码，`scripts/` 是开发和构建脚本，`dist/` 是构建产物，不提交到 Git。修改页面后刷新浏览器查看。

## Vercel 部署

1. Vercel → Add New → Project → 导入 `diifan/acecut-website`。
2. Framework Preset 选择 **Other**，Root Directory 使用仓库根目录 `./`，生产分支为 `main`。
3. 仓库的 `vercel.json` 已声明 Install Command `bun install`、Build Command `bun run build`、Output Directory `dist`，无需重复覆盖。
4. 点击 Deploy，先确认 Vercel 提供的部署地址能正常打开。
5. 项目 Settings → Domains → 添加 `acecut.goswie.com`。
6. 复制该页面给出的 CNAME 目标地址，进入 GoDaddy → goswie.com → DNS → 新增记录：

| 字段 | 值 |
| --- | --- |
| Type | CNAME |
| Name / Host | acecut |
| Value / Points to | Vercel 为该项目显示的 CNAME 目标，原样复制 |
| TTL | 默认值 |

如果已经有名为 acecut 的冲突记录，确认后更新该记录。不要更改主站的 @、www、MX 或 Nameservers。不要使用局域网 IP 或 4173 端口作为 DNS 值。

7. 返回 Vercel 等待域名显示 Valid Configuration，HTTPS 证书由 Vercel 自动配置。若出现域名归属验证，按页面要求增加对应 TXT 记录。
8. 打开 https://acecut.goswie.com/ 检查页面。绑定 GitHub 后，推送 main 会触发 Vercel 生产部署；需要预览的修改使用分支和 Pull Request。

官方说明：[Vercel 域名配置](https://vercel.com/docs/domains/working-with-domains/add-a-domain)、[GoDaddy CNAME](https://www.godaddy.com/help/add-a-cname-record-19236)。

## 后续维护

- 正文及 SEO 元数据：`public/index.html`
- 页面样式及响应式布局：`public/style.css`
- Courtside 滚动交互：`public/reviews.js`
- 图片：`public/assets/`
- 域名 SEO：`public/robots.txt`、`public/sitemap.xml`
- Vercel 配置：`vercel.json`

canonical、Open Graph URL、sitemap 已配置为 https://acecut.goswie.com/。

## 内容待更新

原稿的 4 个下载入口目前指向 App Store 搜索结果，上架后统一替换成正式应用链接。字体使用 Google Fonts，离线会回退到系统字体。功能描述和产品示意图沿用原稿，正式发布前确认其符合发布版本，并接入需要的隐私政策及条款。

## 已完成验证

- Bun 1.4.3 安装、构建通过。
- HTML 资源、锚点、H1、CSS 图片引用和 sitemap XML 检查通过。
- Chromium 通过 HTTP 检查 1440×1000、390×844、320×740：图片、字体加载正常，无横向溢出和页面 JavaScript 错误。
- FAQ 展开、滚动暂停及减少动画偏好检查通过。
- `validation/` 为本地验收截图，不提交到仓库或发布目录。
