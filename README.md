# 栖桥 · 公寓噪声事件分离与调解履约

将匿名投诉、监测授权、频带成分、双方调解、整改复验与观察结案串成一份可追溯的工作簿。六个业务模块，六个操作页面，Python计算与原生HTML/CSS/ES modules。

## 场景与工作流

模拟客户栖桥公寓协调处，3名协调员，12栋住宅。现在用纸质投诉夹、Excel事件表、线下调解单和回访台账：同一事件反复抄录会重复计数；算法意见和现场证据容易混在一起；整改后复发仍可能沿用原观察期结案。上游是住户匿名别名、授权凭据及合成频带，下游是协调主管、整改责任方与匿名交接档案。

1. **匿名收件与授权**：投诉编号唯一，授权可撤回再恢复；未授权仍可建卷但不能新增事件或处理任务。
2. **频带事件去重**：8个非负有限频带，按同卷/测点/时刻去重；事件会同步检查既有协议的复发条件。
3. **成分与人工归因**：真实worker完成NMF；新事件令旧快照不能再用于首次人工确认。只有主管能登记现场归因。楼道换表后分离仍可能给出看似可信的占比，因此另报逐事件相对重构误差：各测点用正常采样建立中位数+MAD稳健基线，连续3条超切点即从首次异常起停用该时段采样。
4. **双方时段协议**：归因确认后起草，指定两位参与方、跨午夜静音窗、阈值和观察天数。双方纸质签字凭据齐全才能由主管生效。在途停用会暂停引用受影响归因，起草协议被拦截；已生效协议不撤销、照常履行。
5. **整改和复验**：责任方须属于协议。所有整改交付后，静音时段的新事件才可作为复验；不允许旧事件、白天低值或停用时段采样充数。
6. **履约与匿名结案**：复发自动重开整改、取消旧观察期；补做整改复验、主管处理复发后重启观察。到期且无未处理复发才结案；结案后可主管重开并保留旧链。

### 换表/漂移采样停用

- **基线**：同一测点未被拦截的正常采样，逐事件相对重构RMSE取中位数与MAD，切点=中位数+3×1.4826×MAD（见 `backend/src/suspension_service.py`）。
- **停用**：连续3条采样超过切点即开停用，`suspended_from` 回溯到首次异常；触发批次确认隔离（`quarantined`）。停用生效期间同测点新采样先以 `pending` 拦住，不进分离、不作复验/复发、不计入协议阈值判断。
- **复测放行**：只能选用该停用下的 pending 采样（≥3条）重建基线；达标转 `released` 且仅放行恢复后的采样，未达标转 `quarantined` 并继续停用。重跑同一批数据不重复打开同一停用时段；放行后再次持续偏离会新开停用并以 `reopened_from_id` 链接旧段。
- **归因联动**：分离快照含在途停用采样的归因标记 `suspended`，调解页禁用并在后端拒绝起草；复测放行并重新分离后解除。成分页可查每段停用的起止、基线切点、逐事件误差、复测记录与受影响归因。

|角色|账号|页面与权限|典型动作|
|---|---|---|---|
|协调员|operator|收件、事件、分离、签字凭据、整改/复验登记|登记授权与线下交付收据|
|协调主管|supervisor|全部页面及受控流转、审计、演示时钟|现场归因、协议生效、处理复发、观察与结案|
|只读访客|viewer|六页只读；所有写接口403|阅读匿名卷宗与协议状态|

三个账号密码均为 `Quiet2026!`。JWT有效8小时；密码PBKDF2存储。只使用模拟别名，不含真实住户资料。

## 一天工作剧本

以演示时钟2026-11-18 16:00开始。08:30查QT031访客青叶、3栋北侧，11月17日22:30起六条窗台合成事件；09:00核对授权凭据QTC-031；09:20在成分页提交分离，280训练/80留出；10:00主管填写设备启停和减振连接件现场证据；10:30起草QTA协议（22:00–07:00，能量阈值10，观察2天），尝试无签字生效得到拒绝；11:00双方线下签字后登记凭据QTS-031，主管生效；14:00登记更换减振垫整改与收据QTR-031；推进演示时钟，在22:30采集总能量1.6的新事件，复验通过后观察；到期核对无复发后匿名交接，下载 `quiet-handover.json`。另用QT032测试撤回/无授权拦截，用新的超阈值夜间事件测试复发重开。实测脚本包含完整时间序列。

## 快速启动

```sh
cp .env.example .env
docker compose up -d --build
docker compose exec -T backend python -m scripts.seed_demo
```

前端 http://localhost:18239 ，后端 http://localhost:19239/docs ，MySQL映射17739。恰好 frontend/backend/worker/db/redis 五服务，均有真实健康检查。Redis不映射宿主端口。启动默认seed，手动重复执行只插入缺少自然键，保留人工修改、归因、协议与交接链。收尾使用 `docker compose down -v --remove-orphans`。

|技术|用途|
|---|---|
|FastAPI / Python3.12|领域校验、JWT和API|
|SQLAlchemy / MySQL8 READ COMMITTED|约束、关系持久化、同卷父行锁|
|scikit-learn / NumPy / SciPy|NMF成分分解与固定留出评价|
|Redis7 + Python worker|队列唤醒，数据库持久任务源|
|原生HTML/CSS/ES modules + Nginx|六页界面、同源API代理|

## 算法与可重复性

`backend/src/separation.py` 用seed1040合成360行非负8频带，前280行fit NMF，后80行只transform。3个成分用合成已知模板的余弦相似度作匈牙利配对，报告留出相对重构RMSE与混合占比MAE。实际事件只transform，成分占比经基底总能量加权归一，并对每条事件额外输出相对重构误差（`reconstruction_error`）供换表检测。记录训练数据与事件快照SHA256、迭代次数、失败态。worker输出持久化到分离记录和共享artifacts卷，计算前再次剔除停用拦截采样。Redis仅唤醒，worker每次循环也从数据库扫描queued；入列失败返回503且事务回滚，恢复后可重新提交。

停用领域逻辑集中在 `backend/src/suspension_service.py`，与业务服务同处投诉行锁内；表结构见 `backend/migrations/002_suspension.md`。`suspension_events` 以 `quarantined/pending/released` 三态区分已确认隔离、待复测与已放行采样，事件一对一链接保证重跑不重复开停用。本地可用 `python -m pytest backend/tests`（SQLite内存库+桩Redis，无需MySQL）验证全部停用规则与HTTP工作流。

固定合成模板不代表真实环境泛化能力；相对能量不是dB，频带分解不证明声源或住户身份，所有归因需要主管现场证据。无原始录音、不提供声学合规或法律判断。

## 结构与本地开发

`backend/src/models.py` 是投诉/事件/分离/停用/复测/归因/协议/签字/整改/复验/复发/结案关系；case/evidence/suspension/agreement/resolution服务分别处理业务，routes只解析请求与授权；两层中间件负责追踪及限流；全局约束错误409。`frontend/src/pages/` 每页负责一种工作任务，`components/common.js` 共享卷宗条、协议条、频带图、成分条与停用面板，api/store/utils分别负责请求、选卷状态和格式/下载。

本地Python3.12虚拟环境安装backend/requirements.txt，设置 `DATABASE_URL`（MySQL8），`REDIS_URL` 后在backend目录执行 `uvicorn src.app:app --reload`；前端可用Nginx配置同源代理或直接build容器。初始schema见 `backend/migrations/001_schema.md`，create_all不会自动升级已有列。

环境变量：`FRONTEND_PORT`18239、`BACKEND_PORT`19239、`DB_PORT`17739、`COMPOSE_PROJECT_NAME`quiet-mediation、`COMPOSE_SUBNET`10.221.40.0/24、`SEED_DEMO`true、`JWT_SECRET`仅演示默认，部署时自行替换。数据库/Redis/artifacts均用命名卷。所有时间为无时区演示本地时间；主管可向前推进独立演示时钟，真实生产需换可信服务器时钟。

共享枚举 `ROLES`、`CASE_STATES`、`SOURCE_TYPES`、`BANDS` 在 `backend/src/constants.py` 与 `frontend/src/constants.js` 一一对应；后端 `/enums` 暴露当前字典。测试、截图与报告单独位于 `../../test-artifacts/gb-1040/`，不混入源码。

License: MIT。
