USE hdb_insights_demo;

CREATE TABLE demo_resale_transaction (
    demo_record_id VARCHAR(41) NOT NULL,
    record_kind VARCHAR(10) NOT NULL DEFAULT 'demo',

    seed_record_id VARCHAR(96) NOT NULL,
    base_data_release_id VARCHAR(100) NOT NULL,

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

    PRIMARY KEY (demo_record_id),

    CONSTRAINT fk_demo_resale_seed
        FOREIGN KEY (seed_record_id, base_data_release_id)
        REFERENCES demo_seed (
            seed_record_id, base_data_release_id
        )
        ON UPDATE RESTRICT
        ON DELETE RESTRICT,

    CONSTRAINT fk_demo_resale_town
        FOREIGN KEY (town_id)
        REFERENCES town (town_id),

    CONSTRAINT fk_demo_resale_flat_type
        FOREIGN KEY (flat_type_code)
        REFERENCES flat_type (flat_type_code),

    CONSTRAINT chk_demo_record_id
        CHECK (
            demo_record_id REGEXP
            '^demo:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        ),

    CONSTRAINT chk_demo_record_kind
        CHECK (record_kind = 'demo'),

    CONSTRAINT chk_demo_month
        CHECK (
            registration_month REGEXP
            '^[0-9]{4}-(0[1-9]|1[0-2])$'
        ),

    CONSTRAINT chk_demo_storeys
        CHECK (
            storey_lower >= 1
            AND storey_upper >= storey_lower
        ),

    CONSTRAINT chk_demo_area
        CHECK (floor_area_sqm > 0),

    CONSTRAINT chk_demo_price
        CHECK (resale_price > 0),

    CONSTRAINT chk_demo_block
        CHECK (CHAR_LENGTH(TRIM(block)) > 0),

    CONSTRAINT chk_demo_street
        CHECK (CHAR_LENGTH(TRIM(street_name)) > 0),

    CONSTRAINT chk_demo_model
        CHECK (CHAR_LENGTH(TRIM(flat_model)) > 0)

) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_bin;


DESCRIBE demo_resale_transaction;

SHOW CREATE TABLE demo_resale_transaction\G