USE hdb_insights_demo;

CREATE TABLE town (
    town_id SMALLINT UNSIGNED NOT NULL,
    town_name VARCHAR(100) NOT NULL,

    PRIMARY KEY (town_id),
    UNIQUE KEY uq_demo_town_name (town_name),

    CONSTRAINT chk_demo_town_name
        CHECK (CHAR_LENGTH(TRIM(town_name)) > 0)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_bin;


CREATE TABLE flat_type (
    flat_type_code VARCHAR(20) NOT NULL,
    display_label VARCHAR(100) NOT NULL,

    PRIMARY KEY (flat_type_code),

    CONSTRAINT chk_demo_flat_type
        CHECK (flat_type_code IN (
            '1_ROOM',
            '2_ROOM',
            '3_ROOM',
            '4_ROOM',
            '5_ROOM',
            'EXECUTIVE',
            'MULTI_GENERATION'
        ))
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_bin;


CREATE TABLE demo_seed (
    seed_record_id VARCHAR(96) NOT NULL,
    base_data_release_id VARCHAR(100) NOT NULL,
    dataset_id VARCHAR(3) NOT NULL,
    source_file_sha256 CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    source_row_number BIGINT NOT NULL,

    PRIMARY KEY (seed_record_id, base_data_release_id),

    CONSTRAINT chk_demo_seed_dataset
        CHECK (dataset_id = 'D01'),

    CONSTRAINT chk_demo_seed_source_row
        CHECK (source_row_number >= 1),

    CONSTRAINT chk_demo_seed_hash
        CHECK (source_file_sha256 REGEXP '^[0-9a-f]{64}$'),

    CONSTRAINT chk_demo_seed_release
        CHECK (CHAR_LENGTH(TRIM(base_data_release_id)) > 0)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_bin;


SHOW TABLES;

SHOW CREATE TABLE demo_seed;