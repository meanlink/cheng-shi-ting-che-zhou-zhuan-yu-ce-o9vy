CREATE TABLE IF NOT EXISTS overflow_window (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reference text NOT NULL UNIQUE,
    forecast_id bigint NOT NULL REFERENCES forecast_plan(id),
    target_lot_id bigint NOT NULL REFERENCES parking_lot(id),
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL,
    service_day date GENERATED ALWAYS AS ((starts_at AT TIME ZONE 'UTC')::date) STORED,
    bay_limit integer NOT NULL CHECK (bay_limit > 0),
    forecast_turnover numeric(12,2) NOT NULL CHECK (forecast_turnover >= 0),
    reason text NOT NULL,
    status text NOT NULL DEFAULT 'proposed' CHECK (status IN
        ('proposed','approved','open','paused','ended','reconciled','cancelled')),
    created_by text NOT NULL REFERENCES staff(email),
    approved_by text REFERENCES staff(email),
    opened_at timestamptz,
    ended_at timestamptz,
    pause_reason text,
    admitted bigint NOT NULL DEFAULT 0 CHECK (admitted >= 0),
    released bigint NOT NULL DEFAULT 0 CHECK (released BETWEEN 0 AND admitted),
    peak_parked integer NOT NULL DEFAULT 0 CHECK (peak_parked BETWEEN 0 AND bay_limit),
    CHECK (ends_at - starts_at BETWEEN interval '15 minutes' AND interval '8 hours'),
    CHECK ((starts_at AT TIME ZONE 'UTC')::date = (ends_at AT TIME ZONE 'UTC')::date),
    CHECK (admitted - released <= peak_parked),
    CHECK (status NOT IN ('ended','reconciled') OR (admitted = released AND ended_at IS NOT NULL)),
    CHECK (status NOT IN ('open','paused','ended','reconciled') OR opened_at IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS overflow_window_capacity ON overflow_window (target_lot_id, service_day)
    WHERE status IN ('approved','open','paused');

CREATE TABLE IF NOT EXISTS overflow_gate_batch (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    window_id bigint NOT NULL REFERENCES overflow_window(id),
    receipt text NOT NULL,
    admitted integer NOT NULL CHECK (admitted >= 0),
    released integer NOT NULL CHECK (released >= 0),
    parked_after integer NOT NULL CHECK (parked_after >= 0),
    recorded_by text NOT NULL REFERENCES staff(email),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (window_id, receipt),
    CHECK (admitted > 0 OR released > 0)
);

CREATE TABLE IF NOT EXISTS overflow_closeout (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    window_id bigint NOT NULL REFERENCES overflow_window(id),
    revision integer NOT NULL CHECK (revision > 0),
    ledger_reference text NOT NULL,
    counted_admitted bigint NOT NULL CHECK (counted_admitted >= 0),
    counted_released bigint NOT NULL CHECK (counted_released >= 0),
    admission_delta bigint NOT NULL,
    release_delta bigint NOT NULL,
    note text NOT NULL,
    status text NOT NULL CHECK (status IN ('flagged','ready','returned','accepted')),
    submitted_by text NOT NULL REFERENCES staff(email),
    submitted_at timestamptz NOT NULL DEFAULT now(),
    reviewed_by text REFERENCES staff(email),
    review_note text,
    UNIQUE (window_id, revision),
    CHECK ((status = 'flagged') = (admission_delta <> 0 OR release_delta <> 0)),
    CHECK (status NOT IN ('returned','accepted') OR reviewed_by IS NOT NULL)
);
