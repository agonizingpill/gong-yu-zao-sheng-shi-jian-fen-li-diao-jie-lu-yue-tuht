# 002 换表/漂移采样停用

新增四张/四项结构，由 `src.models` metadata 建立；对已存在的库需显式执行下列 DDL，create_all 不会修改既有表。

```sql
CREATE TABLE suspensions (
  id INTEGER PRIMARY KEY AUTO_INCREMENT,
  complaint_id INTEGER NOT NULL,
  position VARCHAR(60) NOT NULL,
  first_event_id INTEGER NOT NULL,
  suspended_from DATETIME NOT NULL,
  baseline_median FLOAT NOT NULL,
  baseline_mad FLOAT NOT NULL,
  cutoff FLOAT NOT NULL,
  reason VARCHAR(300) DEFAULT '',
  state VARCHAR(20) DEFAULT 'active',
  reopened_from_id INTEGER NULL,
  released_at DATETIME NULL,
  release_note VARCHAR(300) DEFAULT '',
  CONSTRAINT fk_sus_case FOREIGN KEY (complaint_id) REFERENCES complaints(id),
  CONSTRAINT fk_sus_first FOREIGN KEY (first_event_id) REFERENCES noise_events(id),
  CONSTRAINT fk_sus_prior FOREIGN KEY (reopened_from_id) REFERENCES suspensions(id)
);
CREATE TABLE suspension_events (
  id INTEGER PRIMARY KEY AUTO_INCREMENT,
  suspension_id INTEGER NOT NULL,
  event_id INTEGER NOT NULL,
  reconstruction_error FLOAT NOT NULL,
  state VARCHAR(20) DEFAULT 'quarantined',
  CONSTRAINT uq_suspension_event UNIQUE (event_id),
  CONSTRAINT fk_se_suspension FOREIGN KEY (suspension_id) REFERENCES suspensions(id),
  CONSTRAINT fk_se_event FOREIGN KEY (event_id) REFERENCES noise_events(id)
);
CREATE TABLE requalifications (
  id INTEGER PRIMARY KEY AUTO_INCREMENT,
  suspension_id INTEGER NOT NULL,
  event_ids JSON NOT NULL,
  baseline_median FLOAT NOT NULL,
  baseline_mad FLOAT NOT NULL,
  cutoff FLOAT NOT NULL,
  passed BOOLEAN NOT NULL,
  note VARCHAR(300),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_rq_suspension FOREIGN KEY (suspension_id) REFERENCES suspensions(id)
);
ALTER TABLE attributions
  ADD COLUMN suspended BOOLEAN DEFAULT 0,
  ADD COLUMN suspension_ids JSON;
```

## 语义

- 基线：同一测点未被拦截的正常采样，逐事件相对重构 RMSE 的中位数与 MAD，切点=中位数+3×1.4826×MAD。
- 连续 3 条超过切点即开停用，`suspended_from` 回溯到首次异常采样；触发批次写入 `suspension_events(state=quarantined)`。
- 停用生效期间同测点新采样以 `state=pending` 拦截，不进分离、复验、复发；复测达标转 `released`，失败转 `quarantined`。
- 复测只接受该停用下的 pending 采样；达标后停用 `state=released`，再次持续偏离新开停用并以 `reopened_from_id` 链接旧段，重跑不重复打开同一停用。
- `attributions.suspended/suspension_ids` 标记引用了在途停用采样的归因，调解起草时拒绝；已生效协议不撤销，照常履行。
