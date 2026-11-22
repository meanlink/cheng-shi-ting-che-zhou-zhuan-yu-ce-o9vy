-- 预测逐日换版：每个场站-运营日只对应一个“在用”预测版本，
-- 已启用或结案的跨场分流所在日保持锁定，沿用换版前的原版数字。
CREATE TABLE IF NOT EXISTS forecast_day_version (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lot_id bigint NOT NULL REFERENCES parking_lot(id),
    service_day date NOT NULL,
    forecast_id bigint NOT NULL REFERENCES forecast_plan(id),
    locked boolean NOT NULL DEFAULT false,
    lock_reason text,
    switched_by text REFERENCES staff(email),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (lot_id, service_day),
    -- 锁定原因枚举由数据库兜底；锁定与原因的成对一致性由应用层 upsert 保证，
    -- 避免 ON CONFLICT 提议行在冲突处理前触发复合 CHECK。
    CHECK (lock_reason IS NULL OR lock_reason IN ('diversion_active', 'diversion_closed'))
);
CREATE INDEX IF NOT EXISTS forecast_day_version_day ON forecast_day_version (lot_id, service_day);

-- 换版请求留痕：request_id 唯一，换版未收到回执时同号重试不产生第二次换版。
-- processing 为并发占位状态：首个事务提交前，同号请求在唯一索引上等待后重放。
CREATE TABLE IF NOT EXISTS forecast_version_switch (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id text UNIQUE NOT NULL,
    lot_id bigint REFERENCES parking_lot(id),
    service_day date,
    from_forecast_id bigint REFERENCES forecast_plan(id),
    to_forecast_id bigint REFERENCES forecast_plan(id),
    status text NOT NULL CHECK (status IN ('processing', 'applied', 'rejected')),
    reject_reason text,
    requested_by text NOT NULL REFERENCES staff(email),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (status = 'processing' OR (lot_id IS NOT NULL AND service_day IS NOT NULL AND to_forecast_id IS NOT NULL)),
    CHECK (reject_reason IS NULL OR status = 'rejected'),
    CHECK (status <> 'rejected' OR reject_reason IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS forecast_version_switch_day ON forecast_version_switch (lot_id, service_day);

-- 老数据补建：已存在分流的日期直接锁定在分流当时引用的预测版本上，
-- 旧分流与复盘继续保留当时的数字。
INSERT INTO forecast_day_version (lot_id, service_day, forecast_id, locked, lock_reason, switched_by)
SELECT c.lot_id, d.service_day, d.forecast_id, true,
       CASE WHEN d.status = 'closed' THEN 'diversion_closed' ELSE 'diversion_active' END,
       d.activated_by
FROM parking_diversion d
JOIN capacity_closure c ON c.id = d.closure_id
WHERE d.status IN ('active', 'closed')
ON CONFLICT (lot_id, service_day) DO UPDATE
SET forecast_id = EXCLUDED.forecast_id,
    locked = true,
    lock_reason = EXCLUDED.lock_reason,
    updated_at = now();
