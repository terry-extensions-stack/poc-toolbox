# POC Toolbox

## 本地运行

```powershell
uv sync --group test
$env:DATABASE_URL = "postgresql+asyncpg://toolbox:password@127.0.0.1:5432/poc_toolbox"
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
$env:AI_CONFIG_ENCRYPTION_KEY = "粘贴上一步生成的密钥"
uv run alembic upgrade head
uv run uvicorn poc_toolbox.main:app --host 127.0.0.1
```

先在 PostgreSQL 中创建数据库及有权管理其表的用户。环境变量示例位于
`src/poc_toolbox/config/config.example.yaml`；程序不会加载此 YAML 或 `.env` 文件。
保存并持续使用同一个加密主密钥；丢失或更换后，已有 API Key 密文将无法解密。
仅写入新 API Key 时要求主密钥，普通查询不依赖它。

Swagger 文档：<http://127.0.0.1:8000/docs>。当前 API 无鉴权，供本地使用。

`GET /` 返回服务元信息：`name`、`version`、`description`，以及 `docs_url`、`redoc_url`、`openapi_url` 文档入口。
前三项在应用初始化时从 `pyproject.toml` 的 `[project]` 读取，OpenAPI 使用同一版本号。
修改后需重启服务；Docker 部署需重新构建镜像。文件缺失、格式错误或必要字段无效时，应用初始化失败。
根路径仅展示元信息，不检查数据库或外部服务健康状态。

## Docker 部署

Compose 仅启动应用，数据库使用已有的 PostgreSQL。先创建数据库及迁移所需的账号。
首次部署时，在 PowerShell 中生成加密密钥：

```powershell
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

直接编辑 `compose.yaml` 的 `environment`：将 `DATABASE_URL` 的账号、密码、主机和数据库名
替换为实际值，将 `AI_CONFIG_ENCRYPTION_KEY` 的占位符替换为生成的密钥。
已有部署应填入原来的密钥，不要重新生成。配置完成后执行：

```powershell
docker compose build
docker compose run --rm app alembic upgrade head
docker compose up -d
docker compose logs -f app
```

保存生成的密钥，后续部署持续使用同一个值。填入真实凭据后的 Compose 文件不要提交到仓库。
Compose 直接将文件中的配置值传给容器，不再从宿主机环境变量读取这两个值。
密钥占位符仅用于示例，使用前必须替换为有效的 Fernet 密钥。
数据库位于宿主机时使用 `host.docker.internal`，位于其他服务器时填写实际主机名；
容器内的 `localhost` 指向容器自身。确保 PostgreSQL 允许容器网络访问。
URL 中的用户名或密码若包含特殊字符，需要进行 URL 编码。

访问 <http://127.0.0.1:8000/docs>。端口仅绑定宿主机回环地址。
迁移必须成功后再启动应用；容器启动不会自动迁移。
执行 `docker compose down` 停止并移除应用容器，外部数据库保留。

## 播客视频工作流

在 Compose 中填写 COS_REGION、COS_BUCKET、COS_SECRET_ID、COS_SECRET_KEY 和 COS_PREFIX。
COS 账号需要指定前缀的上传、下载和删除权限。API、worker、beat 使用相同数据库和 Redis 配置。
视频生成使用环境变量配置，不读取数据库模型配置。`SEEDANCE_API_KEY` 必填；
`SEEDANCE_BASE_URL` 默认 `https://ark.cn-beijing.volces.com/api/v3`，
`SEEDANCE_MODEL_ID` 默认 `doubao-seedance-1-0-pro-fast-251015`，与参考脚本一致。
启动 Compose 前在 shell 或 `.env` 中设置变量，并执行 `alembic upgrade head` 应用迁移。
迁移将历史 `model_config_id` 列改为可空，保留已有数据；新任务不再使用该字段。
worker 镜像包含 FFmpeg 和中文字体，Redis 保存消息，PostgreSQL 保存任务状态。

```powershell
docker compose build
docker compose run --rm poc_toolbox alembic upgrade head
docker compose up -d
docker compose logs -f poc_toolbox_worker
```

`POST /api/podcast-jobs` 接收示例 podcast_content.json 的字段，另外必须提供
`image_url`，可选 `aspect_ratio`（默认 `9:16`，支持 `16:9`、`1:1`），不接受 `model_config_id`。
新任务只生成无后期文字的完整基础视频。`burn_subtitles` 保留为兼容字段，基础生成阶段不烧录标题或字幕。
字幕和标题通过独立接口预览、保存，每次从基础视频合成并替换当前成片，见 [编辑接口](docs/podcast-renders.md)。
请求头必须包含 `Idempotency-Key`，同一次任务重试使用同一个值；相同键与不同内容返回 422。
任务提交数据库后立即发送 Celery，由 worker 执行，不依赖定时扫描。素材 URL 必须是可直接下载的 HTTPS 地址。
队列发送未确认时返回 503，任务记录保留；使用原请求及同一 Idempotency-Key 重试会重新投递 QUEUED 任务。
字幕时间单位为毫秒，必须按顺序、不重叠，最长 30 分钟。图片必须是 JPEG。

`GET /api/podcast-jobs/{id}` 查询状态、进度与下载入口；
`GET /api/podcast-jobs?page=1&page_size=20` 分页查询；
可选参数 `image_url`、`audio_url` 按素材完整链接精确过滤，同时传入时任意一个匹配即可（OR），同一任务只返回一次。
例如 `GET /api/podcast-jobs?image_url=https%3A%2F%2Fexample.com%2Fimage.jpg&page=1&page_size=20`。
链接使用与创建请求一致的 HTTP(S) URL 校验和序列化，包含签名的查询参数也参与匹配；请通过客户端 query 参数编码传递链接。
查询包含所有任务状态，按创建时间倒序；默认每页 20 条，最多 100 条，`total` 为匹配总数。
也可使用 `GET /api/podcast-jobs?idempotency_key=my-podcast-key`，按创建请求头中的 `Idempotency-Key` 查询。
传入 `idempotency_key` 时仅按 key 过滤，忽略图片和音频过滤条件；链接参数仍须通过 URL 格式校验。
key 长度为 1–200，精确匹配，不裁剪空白、不改变大小写；唯一键匹配总数为 0 或 1，仍遵循分页规则。
无匹配时返回空列表，不传 key 或素材参数时查询全部任务。
`GET /api/podcast-jobs/{id}/download` 成功后跳转到有效期 15 分钟的 COS 签名链接。
任务响应的 `segments_url` 指向 `GET /api/podcast-jobs/{id}/segments`，支持 `page`、`page_size` 分页。
列表仅展示已完成镜头，编号从 0 开始，返回 `video_url`（处理后片段）与 `raw_video_url`（模型原始视频）。
`GET /api/podcast-jobs/{id}/segments/{index}/video` 可直接播放，支持 HTTP Range；
加 `?variant=raw` 读取原始视频。片段不含最终配音和烧录字幕，来自 API 只读挂载的共享持久卷。
片段文件被清理后返回 404；不影响已上传 COS 的最终成品。
`POST /api/podcast-jobs/{id}/retry` 将 FAILED 任务重新排队，复用已完成片段和供应商任务 ID。
供应商明确拒绝或失败的任务不会自动重新创建付费生成请求，可使用新幂等键创建新任务。

工作流按字幕下一段开始时间覆盖镜头间隙，长段自动拆成不超过 12 秒的镜头，
短段请求至少 2 秒后裁剪。每段实际末帧提取为 JPEG 并转 Base64，作为下一镜头首帧。
最终视频使用原音频，总时长以音频为准。
字幕结束时间超过音频时，将整条字幕时间轴等比例压缩到音频时长，用于规划镜头。
基础合成拼接画面、合入原音频，不添加标题或字幕；独立保存接口按 `burn_subtitles` 决定是否显示字幕。
字幕位于横向 8%–92%、纵向 86%–94% 的区域，白字细黑描边、半透明黑底，每屏最多两行，硬裁剪防止越界。
长句按实际字体宽度拆屏，按有效文字量分配原句时长；句内换屏时间为估算值，保留原句起止时间及句间空白。
开启时保存 `subtitles.srt`、`subtitles.ass`；关闭时仍保存独立 SRT。短至不足一帧的字幕屏会报错而不丢字。
字体由 `PODCAST_SUBTITLE_FONT` 指定，默认 `/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc`，镜像已安装。
Windows 本地运行可设置 `$env:PODCAST_SUBTITLE_FONT = 'C:/Windows/Fonts/msyh.ttc'`；字体不可用时任务失败。
本次升级需运行迁移 `0005`，同步部署 API、worker、beat。修改标题或字幕使用独立保存接口与新的 `Idempotency-Key`。
字幕比音频短时保留原时间轴，最后一个镜头延续至音频结束；不改变音频速度。
基础视频保存在 COS 的 `前缀/任务ID/base.mp4`，编辑成片为同目录的 `edited-保存任务ID.mp4`。
旧成片在新成片发布后异步清理，基础视频始终保留；本地中间文件保存在 podcast_data 持久卷。
FFmpeg 解码、编码各限制为 2 个线程，滤镜限制为 1 个线程，避免多 worker 并行时自动开启过多线程。
媒体处理失败时，worker 日志包含工作目录、退出码和最近的 stderr；超时会单独记录。
供应商生成失败时，worker 日志包含本地任务 ID、片段编号、供应商任务 ID、状态、错误码、错误消息与请求追踪 ID。
供应商 HTTP 错误另记录 HTTP 状态；新增诊断会脱敏 API Key 和错误消息中的 URL，不打印完整响应或素材内容。
本地中间文件暂不自动清理；删除卷后无法保证失败任务续跑，COS 成品不受影响。

状态包括 QUEUED、RUNNING、SUCCEEDED、FAILED、SUBMISSION_UNKNOWN。
任务失败时，数据库的 `error` 字段保存最近一次异常 message（脱敏并限制长度），
详情及列表接口通过同名字段返回，前端可直接展示；不返回异常堆栈。
重试和成功时清空错误。历史失败记录不会自动补全具体原因，需重新执行后记录。
若提交供应商请求时断线或进程崩溃，无法确认是否计费，任务进入 SUBMISSION_UNKNOWN，
不会自动重提；需人工核对供应商控制台。避免在不确定结果时创建重复任务。
无需 beat。数据库任务锁避免相同任务同时执行，Celery 延迟确认使 worker 异常退出后的消息可重新投递。
Worker 数据库临时断连会重试当前读写步骤，默认最多 120 秒，由 `PODCAST_DATABASE_RETRY_TIMEOUT_SECONDS` 配置。
等待间隔为 2、4、8、16 秒，之后每 20 秒一次；等待时间和单次数据库操作超时受剩余预算限制。
连接拒绝、中断、超时和数据库暂不可用可重试，SQL、参数及约束错误不重试。
每次写入使用新 Session/事务，失败事务关闭回滚，避免 `PendingRollbackError` 覆盖原始错误。
数据库恢复后检查任务锁，锁连接失效则重新获取；其他 worker 已持有锁时停止当前执行。
火山提交成功后立即记录供应商任务 ID，并原子写入工作目录的 `provider-{index}.json`，再保存数据库进度。
恢复同一任务时会核对本地记录并复用供应商任务 ID，不重复提交生成请求；请保留共享持久卷中的恢复记录。
超过重试预算仍不可用时保留原始错误和本地记录，停止当前执行，不启动整条 Celery 任务的自动重试。
数据库不可用时失败状态可能无法落库，日志会明确提示；数据库显示 RUNNING 不代表 worker 仍在运行。
恢复此类超时任务需要在数据库恢复后确认无其他执行者，再由运维投递同一任务 ID；FAILED 任务使用现有 retry 接口。
没有本地记录且持久进度为 `submitting=true` 时，仍停止并要求核对供应商任务；不能自动重提付费请求。
此能力仅适用于 worker，不改变 API 或火山提交请求的重试策略；无需数据库迁移或修改 Dockerfile，需重新构建部署 worker。
数据库提交与 Redis 投递不是原子操作：API 在两者之间退出时，客户端需用相同请求与幂等键重试。
素材下载只允许 PODCAST_ALLOWED_HOSTS 配置的主机/域名后缀，拒绝重定向，IP 网段按以下配置校验；
供应商视频下载域名若不同，需要将实际域名加入白名单。
`PODCAST_TRUSTED_DOWNLOAD_NETWORKS` 默认值为 `0.0.0.0/0,::/0`，允许所有 IPv4、IPv6 网段，包括内网和回环地址。
环境变量使用逗号分隔，例如 `198.18.0.0/15,10.0.0.0/8`，允许公网地址及指定网段；前后空格和空项会被忽略。
显式设置为空字符串或 `[]` 时仅允许公网地址；旧的 JSON 数组格式仍兼容，无效网段会在配置加载时被拒绝。
HTTPS、域名白名单和端口限制继续生效。API 和 Worker 均需使用相同配置。

Kubernetes Secret 可通过普通字符串配置，无需 JSON：

```yaml
stringData:
  PODCAST_TRUSTED_DOWNLOAD_NETWORKS: "0.0.0.0/0,::/0"
```

## 数据接口

播客视频支持可选 `layout` 配置，实现横屏素材居中、顶部标题、底部字幕，以及前端拖拽布局。
请求示例、坐标换算和兼容规则见 [播客布局说明](docs/podcast-layout.md)。

`/api/model-configs` 和 `/api/ai-templates` 都支持 POST 创建、GET 分页查询，
以及 `/{id}` 的 GET、PATCH、DELETE。模型配置创建字段为 `name`、`base_url`、
`model_id`、`api_key`；模板创建字段为 `name`、`user_prompt`、`model_config_id`，
可选 `system_prompt`。PATCH 只更新提供的字段，不接受显式 null。

模型配置响应以 `has_api_key` 表示已设置密钥，不返回明文或密文。省略更新请求的
`api_key` 会保留已有密文。重复名称及删除被引用的配置返回 409；引用不存在的配置返回 422。
删除不存在的记录返回 204；查询、更新不存在的记录返回 404。

列表参数为 `page`（默认 1）、`page_size`（默认 20，最大 100），返回
`items`、`total`、`page`、`page_size`。模板列表可用 `model_config_id` 筛选。
错误响应使用 `error.code`、`error.message`，校验错误详情不包含输入值。

Repository 通过构造函数接收 `AsyncSession`，只 flush，不提交或回滚。
调用方用 `async with session.begin()` 组合操作；API 使用请求事务，在发送响应前提交。
模板查询显式加载关联模型配置，避免异步懒加载。

## 迁移

```powershell
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "Describe schema change"
uv run alembic downgrade -1
```

提交迁移前检查自动生成内容。应用启动不会建表；已有手工创建的表需先核对结构，再决定如何建立迁移基线。
首次安装使用 `upgrade head`；降级初始迁移会删除两张表及其数据。

## 测试

```powershell
$env:TEST_DATABASE_URL = "postgresql+asyncpg://toolbox:password@127.0.0.1:5432/poc_toolbox_test"
uv run pytest -q
```

测试必须指向专用 PostgreSQL 测试数据库，账号需要创建 schema 的权限。
每项集成测试创建唯一 schema，运行真实迁移并在结束时降级、清理该 schema。
未提供 `TEST_DATABASE_URL` 时 PostgreSQL 集成测试显式跳过，其余测试照常运行。
