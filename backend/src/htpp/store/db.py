"""DuckDB connection and DDL. All table shapes follow docs/03."""

from __future__ import annotations

import duckdb

from htpp.config import settings

DDL = """
CREATE TABLE IF NOT EXISTS telemetry_raw (
    machine_id INTEGER NOT NULL,
    sampled_at TIMESTAMPTZ NOT NULL,
    batch_no INTEGER,
    ts_c DOUBLE,
    tr_c DOUBLE,
    ps_bar DOUBLE,
    pr_bar DOUBLE,
    process_raw VARCHAR,
    process_state VARCHAR,
    fault_state VARCHAR,
    roh_c_per_min DOUBLE,
    roh_cal_c_per_min DOUBLE,
    amb_temp_c DOUBLE,
    panel_version VARCHAR,
    panel_chip_id VARCHAR,
    ingested_at TIMESTAMPTZ,
    source_url VARCHAR,
    PRIMARY KEY (machine_id, sampled_at)
);

CREATE TABLE IF NOT EXISTS batches (
    batch_key VARCHAR PRIMARY KEY,
    machine_id INTEGER,
    batch_no INTEGER,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    total_duration_min DOUBLE,
    n_samples INTEGER,
    median_interval_s DOUBLE,
    max_gap_s DOUBLE,
    peak_tr_c DOUBLE,
    peak_ts_c DOUBLE,
    peak_pr_bar DOUBLE,
    min_pr_bar DOUBLE,
    is_complete BOOLEAN,
    had_fault BOOLEAN,
    fault_states VARCHAR[],
    panel_version VARCHAR,
    quality_flags VARCHAR[]
);

CREATE TABLE IF NOT EXISTS phases (
    batch_key VARCHAR,
    phase_index INTEGER,
    process_state VARCHAR,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    duration_min DOUBLE,
    n_samples INTEGER,
    tr_start_c DOUBLE,
    tr_end_c DOUBLE,
    tr_peak_c DOUBLE,
    mean_amb_temp_c DOUBLE,
    mean_roh_c_per_min DOUBLE,
    PRIMARY KEY (batch_key, phase_index)
);

CREATE TABLE IF NOT EXISTS batch_log (
    machine_id INTEGER,
    batch_no INTEGER,
    log_date DATE,
    feed_mass_kg DOUBLE,
    moisture_pct DOUBLE,
    feedstock_type VARCHAR,
    feedstock_mix_pct DOUBLE,
    oil_mass_kg DOUBLE,
    carbon_mass_kg DOUBLE,
    steel_mass_kg DOUBLE,
    gas_mass_kg DOUBLE,
    operator VARCHAR,
    notes VARCHAR,
    source_file VARCHAR,
    source_row INTEGER,
    PRIMARY KEY (machine_id, batch_no)
);

CREATE TABLE IF NOT EXISTS batch_yields (
    machine_id INTEGER,
    batch_no INTEGER,
    oil_yield_pct DOUBLE,
    carbon_yield_pct DOUBLE,
    steel_yield_pct DOUBLE,
    gas_yield_pct DOUBLE,
    accounted_pct DOUBLE,
    closure_error_pct DOUBLE,
    dry_feed_mass_kg DOUBLE,
    oil_yield_dry_pct DOUBLE,
    PRIMARY KEY (machine_id, batch_no)
);

CREATE TABLE IF NOT EXISTS batch_features (
    batch_key VARCHAR PRIMARY KEY,
    machine_id INTEGER,
    started_at TIMESTAMPTZ,
    heating_duration_min DOUBLE,
    gas_duration_min DOUBLE,
    cooling_duration_min DOUBLE,
    n2_purge_duration_min DOUBLE,
    carbon_discharge_duration_min DOUBLE,
    total_duration_min DOUBLE,
    peak_tr_c DOUBLE,
    mean_roh_heating_c_per_min DOUBLE,
    max_roh_c_per_min DOUBLE,
    time_above_350c_min DOUBLE,
    time_above_400c_min DOUBLE,
    time_above_450c_min DOUBLE,
    severity_index_c_min DOUBLE,
    tau_cool_min DOUBLE,
    ua_eff_w_per_k DOUBLE,
    c_eff_j_per_k DOUBLE,
    q_in_heating_w DOUBLE,
    alpha_final DOUBLE,
    e_rxn_j DOUBLE,
    max_pr_bar DOUBLE,
    mean_pr_gas_bar DOUBLE,
    pr_oscillation_count INTEGER,
    pr_integral_bar_min DOUBLE,
    mean_amb_temp_c DOUBLE,
    feed_mass_kg DOUBLE,
    moisture_pct DOUBLE,
    feedstock_type VARCHAR,
    oil_yield_pct DOUBLE,
    carbon_yield_pct DOUBLE,
    steel_yield_pct DOUBLE,
    closure_error_pct DOUBLE,
    had_fault BOOLEAN,
    quality_flags VARCHAR[],
    usable_for_training BOOLEAN
);

CREATE TABLE IF NOT EXISTS ingest_runs (
    run_id VARCHAR,
    kind VARCHAR,
    machine_id INTEGER,
    range_start TIMESTAMPTZ,
    range_end TIMESTAMPTZ,
    rows_fetched INTEGER,
    rows_inserted INTEGER,
    http_status INTEGER,
    error VARCHAR,
    duration_s DOUBLE,
    started_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS unmapped_process (
    machine_id INTEGER,
    sampled_at TIMESTAMPTZ,
    process_raw VARCHAR
);
"""


def connect() -> duckdb.DuckDBPyConnection:
    settings.db_file.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(settings.db_file))


def migrate(con: duckdb.DuckDBPyConnection | None = None) -> duckdb.DuckDBPyConnection:
    own = con is None
    con = con or connect()
    con.execute(DDL)
    if own:
        return con
    return con
