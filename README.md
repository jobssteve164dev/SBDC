# SBDC

SBDC 是一个面向博士论文和期刊论文的科研诚信深度检查项目。它围绕一篇待检论文即时获取其引用文献，构建任务级临时对照库，发现文本复用、引用失真、统计与数据异常、图片复用及跨版本不一致，并把每一项发现还原为可复核证据。

项目不自动给作者或论文定性“造假”“抄袭”。系统负责发现异常、定位来源、保存证据和组织复核；学术不端定性必须由有权限的审查者结合原始数据、研究规范和作者说明完成。

## 当前状态

- 状态：首个 PDF 解析纵向闭环已进入实现验证。
- 当前交付：审查者登录、浏览器上传、FastAPI 任务与资产 API、Celery 异步解析、GROBID 结构化结果、PostgreSQL/MinIO 持久化和解析覆盖率页面。
- 已确认边界：不建设长期全文对照库；每次任务只为当前论文临时获取和索引引用文献。
- 下一轮入口：从 [首期实施计划](docs/06-MVP实施计划与验收.md) 的阶段 0 开始建立工程骨架和最小纵向闭环。

## 文档索引

1. [产品定义与范围](docs/01-产品定义与范围.md)
2. [开源项目调研](docs/02-开源项目调研.md)
3. [系统架构与技术栈](docs/03-系统架构与技术栈.md)
4. [检查管线设计](docs/04-检查管线设计.md)
5. [数据模型与任务生命周期](docs/05-数据模型与任务生命周期.md)
6. [MVP 实施计划与验收](docs/06-MVP实施计划与验收.md)
7. [安全、隐私与许可证边界](docs/07-安全隐私与许可证.md)
8. [架构决策记录](docs/DECISIONS.md)
9. [本地运行与验证](docs/08-本地运行与验证.md)

## 快速开始

需要 Docker Engine、Docker Compose v2，以及至少 4 GB 可用内存。首次启动会下载 GROBID 镜像。

```bash
cp .env.example .env
# 将 .env 中的占位值全部换成随机凭据
docker compose config --quiet
docker compose up --build
```

打开 <http://localhost:3000>，使用 `.env` 中的审查者账号和密码登录，再选择一篇带文本层的学术 PDF。页面会自动完成任务创建、文件验证和异步解析，并展示正文结构、参考文献覆盖率与 PDF 页码入口。API 只通过已鉴权的 Web 入口转发，不直接发布到宿主机。

完整启动、验证和故障定位见 [本地运行与验证](docs/08-本地运行与验证.md)。

## 首期技术栈

- 前端：Next.js、TypeScript、PDF.js
- API：Python、FastAPI、Pydantic、SQLAlchemy、Alembic
- 异步任务：Celery、Redis
- 持久数据：PostgreSQL
- 临时对象：MinIO 或其他 S3 兼容对象存储
- 论文解析：GROBID、PyMuPDF；扫描页按需使用 PaddleOCR
- 文本检测：Winnowing/MinHash、RapidFuzz、BGE-M3、FAISS
- 统计检测：隔离 R Worker，接入 statcheck、scrutiny、rsprite2
- 图片检测：OpenCV、Pillow/imagehash、SSCD
- 部署：Docker Compose

首期不引入长期全文搜索集群、OpenSearch、Qdrant、Kafka 或 Kubernetes。

## 许可证

SBDC 自有代码与文档采用 [MIT License](LICENSE)。第三方依赖、模型权重、数据、论文内容和用户上传材料遵循各自的许可证与权利边界。

## 项目原则

1. 所有高风险判断必须展示原文、来源、位置和检测依据。
2. 相似不等于抄袭，异常不等于造假，模型意见不等于调查结论。
3. 只有 PDF 时只报告可从论文记录验证的异常；没有原始数据时不得声称验证了数据真实性。
4. 未公开论文和原始数据默认不发送给第三方大模型。
5. 引用全文只属于当前检查任务，不进入共享或长期全文库。
6. 无法合法取得的引用全文只记录元数据和获取状态，不绕过付费墙。
