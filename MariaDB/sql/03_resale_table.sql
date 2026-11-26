-- HDB Insights | Contract HDBI-1.0.0
USE hdb_insights;

CREATE TABLE resale_transaction (
    record_id VARCHAR(96) NOT NULL,
    registration_month CHAR(7) NOT NULL,
    town_id SMALLINT UNSIGNED NOT NULL,
    flat_type_code VARCHAR(20) NOT NULL,
    block VARCHAR(20) NOT NULL,
    street_name VARCHAR(100) NOT NULL,
    storey_lower SMALLINT UNSIGNED NOT NULL,
    storey_upper SMALLINT UNSIGNED NOT NULL,
    floor_area_sqm DECIMAL(8,2) NOT NULL,
    flat_model VARCHAR(100) NOT NULL,
    lease_commence_year SMALLINT UNSIGNED NOT NULL,
    remaining_lease_months SMALLINT UNSIGNED NOT NULL,
    resale_price DECIMAL(14,2) NOT NULL,

    dataset_id VARCHAR(3) NOT NULL,
    source_file_sha256 CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    source_row_number BIGINT NOT NULL,

    PRIMARY KEY (record_id),

    UNIQUE KEY uq_resale_source_row (
        dataset_id, source_file_sha256, source_row_number
    ),

    KEY idx_resale_town_type_month (
        town_id, flat_type_code, registration_month
    ),
    KEY idx_resale_month_record (
        registration_month, record_id
    ),

    CONSTRAINT fk_resale_town
        FOREIGN KEY (town_id)
        REFERENCES town (town_id),

    CONSTRAINT fk_resale_flat_type
        FOREIGN KEY (flat_type_code)
        REFERENCES flat_type (flat_type_code),

    CONSTRAINT fk_resale_source
        FOREIGN KEY (dataset_id, source_file_sha256)
        REFERENCES source_dataset (dataset_id, source_file_sha256),

    CONSTRAINT chk_resale_month CHECK (
        registration_month REGEXP
        '^[0-9]{4}-(0[1-9]|1[0-2])$'
    ),
    CONSTRAINT chk_resale_storeys CHECK (
        storey_lower >= 1 AND storey_lower <= storey_upper
    ),
    CONSTRAINT chk_resale_area CHECK (
        floor_area_sqm > 0
    ),
    CONSTRAINT chk_resale_price CHECK (
        resale_price > 0
    ),
    CONSTRAINT chk_resale_flat_type CHECK (
        flat_type_code <> 'ALL'
    ),
    CONSTRAINT chk_resale_dataset CHECK (
        dataset_id = 'D01'
    ),
    CONSTRAINT chk_resale_source_row CHECK (
        source_row_number >= 1
    )
) ENGINE=InnoDB;