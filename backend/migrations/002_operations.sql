CREATE TABLE IF NOT EXISTS capacity_closure (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reference text UNIQUE NOT NULL,
    lot_id bigint NOT NULL REFERENCES parking_lot(id),
    starts_on date NOT NULL,
    ends_on date NOT NULL CHECK (ends_on - starts_on BETWEEN 0 AND 29),
    blocked_spaces integer NOT NULL CHECK (blocked_spaces > 0),
    reason text NOT NULL CHECK (length(trim(reason)) >= 4),
    status text NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','approved','cancelled')),
    created_by text NOT NULL REFERENCES staff(email),
    approved_by text REFERENCES staff(email),
    cancelled_by text REFERENCES staff(email),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (status <> 'approved' OR approved_by IS NOT NULL),
    CHECK (status <> 'cancelled' OR cancelled_by IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS closure_lot_window ON capacity_closure (lot_id, starts_on, ends_on) WHERE status = 'approved';

CREATE TABLE IF NOT EXISTS parking_diversion (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    closure_id bigint NOT NULL REFERENCES capacity_closure(id),
    forecast_id bigint NOT NULL REFERENCES forecast_plan(id),
    target_lot_id bigint NOT NULL REFERENCES parking_lot(id),
    service_day date NOT NULL,
    reserved_spaces integer NOT NULL CHECK (reserved_spaces > 0),
    forecast_turnover numeric(12,2) NOT NULL CHECK (forecast_turnover >= 0),
    target_headroom_at_activation integer CHECK (target_headroom_at_activation >= reserved_spaces),
    dispatch_note text NOT NULL CHECK (length(trim(dispatch_note)) >= 4),
    status text NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','active','closed','cancelled')),
    created_by text NOT NULL REFERENCES staff(email),
    activated_by text REFERENCES staff(email),
    cancelled_by text REFERENCES staff(email),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (status NOT IN ('active','closed') OR (activated_by IS NOT NULL AND target_headroom_at_activation IS NOT NULL)),
    CHECK (status <> 'cancelled' OR cancelled_by IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_diversion_per_closure_day ON parking_diversion (closure_id, service_day) WHERE status <> 'cancelled';
CREATE INDEX IF NOT EXISTS diversion_target_day ON parking_diversion (target_lot_id, service_day) WHERE status IN ('active','closed');

CREATE TABLE IF NOT EXISTS diversion_settlement (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    diversion_id bigint UNIQUE NOT NULL REFERENCES parking_diversion(id),
    ledger_reference text NOT NULL CHECK (length(trim(ledger_reference)) >= 4),
    observation_count integer NOT NULL CHECK (observation_count > 0),
    observed_turnover bigint NOT NULL CHECK (observed_turnover >= 0),
    actual_diverted integer NOT NULL CHECK (actual_diverted >= 0),
    analysis_note text NOT NULL CHECK (length(trim(analysis_note)) >= 4),
    status text NOT NULL DEFAULT 'submitted' CHECK (status IN ('submitted','returned','accepted')),
    revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
    submitted_by text NOT NULL REFERENCES staff(email),
    reviewed_by text REFERENCES staff(email),
    review_note text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (status = 'submitted' OR (reviewed_by IS NOT NULL AND review_note IS NOT NULL))
);
