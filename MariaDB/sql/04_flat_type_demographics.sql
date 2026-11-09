-- HDB Insights | Contract HDBI-1.0.0
USE hdb_insights;

CREATE TABLE age_by_flat_type (
    survey_year SMALLINT UNSIGNED NOT NULL,
    flat_type_code VARCHAR(20) NOT NULL,
    age_group_code VARCHAR(20) NOT NULL,
    percentage DECIMAL(5,2) NOT NULL,

    dataset_id VARCHAR(3) NOT NULL,
    source_file_sha256 CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    source_row_number BIGINT NOT NULL,

    PRIMARY KEY (survey_year, flat_type_code, age_group_code),

    CONSTRAINT fk_age_flat_type
        FOREIGN KEY (flat_type_code)
        REFERENCES flat_type (flat_type_code),

    CONSTRAINT fk_age_flat_age_group
        FOREIGN KEY (age_group_code)
        REFERENCES age_group (age_group_code),

    CONSTRAINT fk_age_flat_source
        FOREIGN KEY (dataset_id, source_file_sha256)
        REFERENCES source_dataset (dataset_id, source_file_sha256),

    CONSTRAINT chk_age_flat_percentage
        CHECK (percentage BETWEEN 0 AND 100),

    CONSTRAINT chk_age_flat_source_row
        CHECK (source_row_number >= 1)
) ENGINE=InnoDB;

CREATE TABLE age_stats_by_flat_type (
    survey_year SMALLINT UNSIGNED NOT NULL,
    flat_type_code VARCHAR(20) NOT NULL,
    average_age DECIMAL(5,2) NOT NULL,
    median_age DECIMAL(5,2) NOT NULL,

    dataset_id VARCHAR(3) NOT NULL,
    source_file_sha256 CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    source_row_number BIGINT NOT NULL,

    PRIMARY KEY (survey_year, flat_type_code),

    CONSTRAINT fk_age_stats_flat_type
        FOREIGN KEY (flat_type_code)
        REFERENCES flat_type (flat_type_code),

    CONSTRAINT fk_age_stats_flat_source
        FOREIGN KEY (dataset_id, source_file_sha256)
        REFERENCES source_dataset (dataset_id, source_file_sha256),

    CONSTRAINT chk_age_stats_flat_values
        CHECK (average_age >= 0 AND median_age >= 0),

    CONSTRAINT chk_age_stats_flat_source_row
        CHECK (source_row_number >= 1)
) ENGINE=InnoDB;

CREATE TABLE population_15_plus_by_flat_type (
    survey_year SMALLINT UNSIGNED NOT NULL,
    flat_type_code VARCHAR(20) NOT NULL,
    population_15_plus BIGINT NOT NULL,

    dataset_id VARCHAR(3) NOT NULL,
    source_file_sha256 CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    source_row_number BIGINT NOT NULL,

    PRIMARY KEY (survey_year, flat_type_code),

    CONSTRAINT fk_population_flat_type
        FOREIGN KEY (flat_type_code)
        REFERENCES flat_type (flat_type_code),

    CONSTRAINT fk_population_flat_source
        FOREIGN KEY (dataset_id, source_file_sha256)
        REFERENCES source_dataset (dataset_id, source_file_sha256),

    CONSTRAINT chk_population_flat_value
        CHECK (population_15_plus >= 0),

    CONSTRAINT chk_population_flat_source_row
        CHECK (source_row_number >= 1)
) ENGINE=InnoDB;