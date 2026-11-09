-- HDB Insights | Contract HDBI-1.0.0
USE hdb_insights;

CREATE TABLE age_by_ethnicity (
    survey_year SMALLINT UNSIGNED NOT NULL,
    ethnic_group_code VARCHAR(20) NOT NULL,
    age_group_code VARCHAR(20) NOT NULL,
    percentage DECIMAL(5,2) NOT NULL,

    dataset_id VARCHAR(3) NOT NULL,
    source_file_sha256 CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    source_row_number BIGINT NOT NULL,

    PRIMARY KEY (survey_year, ethnic_group_code, age_group_code),

    CONSTRAINT fk_age_ethnicity_group
        FOREIGN KEY (ethnic_group_code)
        REFERENCES ethnic_group (ethnic_group_code),

    CONSTRAINT fk_age_ethnicity_age_group
        FOREIGN KEY (age_group_code)
        REFERENCES age_group (age_group_code),

    CONSTRAINT fk_age_ethnicity_source
        FOREIGN KEY (dataset_id, source_file_sha256)
        REFERENCES source_dataset (dataset_id, source_file_sha256),

    CONSTRAINT chk_age_ethnicity_percentage
        CHECK (percentage BETWEEN 0 AND 100),

    CONSTRAINT chk_age_ethnicity_source_row
        CHECK (source_row_number >= 1)
) ENGINE=InnoDB;

CREATE TABLE age_stats_by_ethnicity (
    survey_year SMALLINT UNSIGNED NOT NULL,
    ethnic_group_code VARCHAR(20) NOT NULL,
    average_age DECIMAL(5,2) NOT NULL,
    median_age DECIMAL(5,2) NOT NULL,

    dataset_id VARCHAR(3) NOT NULL,
    source_file_sha256 CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    source_row_number BIGINT NOT NULL,

    PRIMARY KEY (survey_year, ethnic_group_code),

    CONSTRAINT fk_age_stats_ethnicity_group
        FOREIGN KEY (ethnic_group_code)
        REFERENCES ethnic_group (ethnic_group_code),

    CONSTRAINT fk_age_stats_ethnicity_source
        FOREIGN KEY (dataset_id, source_file_sha256)
        REFERENCES source_dataset (dataset_id, source_file_sha256),

    CONSTRAINT chk_age_stats_ethnicity_values
        CHECK (average_age >= 0 AND median_age >= 0),

    CONSTRAINT chk_age_stats_ethnicity_source_row
        CHECK (source_row_number >= 1)
) ENGINE=InnoDB;

CREATE TABLE population_15_plus_by_ethnicity (
    survey_year SMALLINT UNSIGNED NOT NULL,
    ethnic_group_code VARCHAR(20) NOT NULL,
    population_15_plus BIGINT NOT NULL,

    dataset_id VARCHAR(3) NOT NULL,
    source_file_sha256 CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    source_row_number BIGINT NOT NULL,

    PRIMARY KEY (survey_year, ethnic_group_code),

    CONSTRAINT fk_population_ethnicity_group
        FOREIGN KEY (ethnic_group_code)
        REFERENCES ethnic_group (ethnic_group_code),

    CONSTRAINT fk_population_ethnicity_source
        FOREIGN KEY (dataset_id, source_file_sha256)
        REFERENCES source_dataset (dataset_id, source_file_sha256),

    CONSTRAINT chk_population_ethnicity_value
        CHECK (population_15_plus >= 0),

    CONSTRAINT chk_population_ethnicity_source_row
        CHECK (source_row_number >= 1)
) ENGINE=InnoDB;