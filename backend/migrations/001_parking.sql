CREATE TABLE IF NOT EXISTS staff (
    email text PRIMARY KEY,
    display_name text NOT NULL,
    password_hash text NOT NULL,
    role text NOT NULL CHECK (role IN ('analyst','operator','supervisor'))
);
CREATE TABLE IF NOT EXISTS parking_lot (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text UNIQUE NOT NULL,
    name text NOT NULL,
    district text NOT NULL,
    capacity integer NOT NULL CHECK (capacity > 0),
    zones text[] NOT NULL,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','maintenance','closed')),
    current_occupancy integer NOT NULL DEFAULT 0 CHECK (current_occupancy >= 0),
    capacity_version integer NOT NULL DEFAULT 1,
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS interval_observation (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lot_id bigint NOT NULL REFERENCES parking_lot(id),
    observed_at timestamptz NOT NULL,
    entry_count integer NOT NULL CHECK (entry_count >= 0),
    exit_count integer NOT NULL CHECK (exit_count >= 0),
    occupancy integer NOT NULL CHECK (occupancy >= 0),
    source_file text NOT NULL,
    source_row text NOT NULL,
    entered_by text NOT NULL REFERENCES staff(email),
    UNIQUE(lot_id, observed_at, source_file, source_row)
);
CREATE TABLE IF NOT EXISTS forecast_plan (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text UNIQUE NOT NULL,
    lot_id bigint NOT NULL REFERENCES parking_lot(id),
    horizon_start date NOT NULL,
    horizon_days integer NOT NULL CHECK (horizon_days BETWEEN 3 AND 14),
    capacity_snapshot integer NOT NULL CHECK (capacity_snapshot > 0),
    status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','backtested','blocked','pending_review','published','rejected')),
    calendar_complete boolean NOT NULL DEFAULT false,
    capacity_change_confirmed boolean NOT NULL DEFAULT false,
    predictions jsonb,
    mae numeric(12,2),
    mape numeric(12,4),
    model_version text,
    created_by text NOT NULL REFERENCES staff(email),
    reviewed_by text REFERENCES staff(email),
    review_note text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS dispatch_alert (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    forecast_id bigint NOT NULL REFERENCES forecast_plan(id),
    lot_id bigint NOT NULL REFERENCES parking_lot(id),
    alert_time timestamptz NOT NULL,
    zone text NOT NULL,
    message text NOT NULL,
    severity text NOT NULL CHECK (severity IN ('info','watch','critical')),
    status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','sent','acknowledged')),
    created_by text NOT NULL REFERENCES staff(email),
    sent_by text REFERENCES staff(email),
    acknowledged_by text REFERENCES staff(email),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS audit_event (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor text NOT NULL REFERENCES staff(email),
    entity_type text NOT NULL,
    entity_id text NOT NULL,
    action text NOT NULL,
    detail text NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_observation_lot_time ON interval_observation(lot_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_forecast_lot_start ON forecast_plan(lot_id, horizon_start);
