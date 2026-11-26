-- HDB Insights | Contract HDBI-1.0.0
USE hdb_insights;

CREATE TABLE mobility_observation (
    survey_year SMALLINT UNSIGNED NOT NULL,
    workplace_area VARCHAR(100) NOT NULL,
    workplace_area_kind VARCHAR(20) NOT NULL,
    residence_region_code VARCHAR(20) NOT NULL,
    transport_mode_code VARCHAR(30) NOT NULL,
    count BIGINT NULL,
    count_status VARCHAR(20) NOT NULL,
    source_column VARCHAR(255) NOT NULL,

    dataset_id VARCHAR(3) NOT NULL,
    source_file_sha256 CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    source_row_number BIGINT NOT NULL,

    PRIMARY KEY (
        survey_year,
        workplace_area,
        residence_region_code,
        transport_mode_code
    ),

    CONSTRAINT fk_mobility_source
        FOREIGN KEY (dataset_id, source_file_sha256)
        REFERENCES source_dataset (dataset_id, source_file_sha256),

    CONSTRAINT chk_mobility_area_kind CHECK (
        workplace_area_kind IN ('total', 'special', 'planning_area')
    ),

    CONSTRAINT chk_mobility_region CHECK (
        residence_region_code IN (
            'ALL', 'CENTRAL', 'EAST',
            'NORTH', 'NORTH_EAST', 'WEST'
        )
    ),

    CONSTRAINT chk_mobility_mode CHECK (
        transport_mode_code IN (
            'ALL', 'RAIL_BUS', 'CAR_TAXI_PRIVATE_HIRE',
            'OTHER', 'NO_TRANSPORT'
        )
    ),

    CONSTRAINT chk_mobility_count_status CHECK (
        (
            count_status = 'reported'
            AND count IS NOT NULL
            AND count >= 0
        )
        OR
        (
            count_status = 'unresolved_dash'
            AND count IS NULL
        )
    ),

    CONSTRAINT chk_mobility_dataset CHECK (
        dataset_id = 'D08'
    ),

    CONSTRAINT chk_mobility_source_row CHECK (
        source_row_number >= 1
    ),

    CONSTRAINT chk_mobility_area_name CHECK (
        CHAR_LENGTH(TRIM(workplace_area)) > 0
    )
) ENGINE=InnoDB;

CREATE TABLE application_metadata (
    metadata_id TINYINT UNSIGNED NOT NULL,
    contract_version VARCHAR(30) NOT NULL,
    data_release_id VARCHAR(100) NOT NULL,
    loaded_at_utc DATETIME(6) NOT NULL,

    PRIMARY KEY (metadata_id),

    CONSTRAINT chk_metadata_singleton CHECK (
        metadata_id = 1
    ),

    CONSTRAINT chk_metadata_contract CHECK (
        CHAR_LENGTH(TRIM(contract_version)) > 0
    ),

    CONSTRAINT chk_metadata_release CHECK (
        CHAR_LENGTH(TRIM(data_release_id)) > 0
    )
) ENGINE=InnoDB;