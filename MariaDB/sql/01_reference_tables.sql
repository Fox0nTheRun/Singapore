-- HDB Insights | Contract HDBI-1.0.0
-- Person B: relational reference tables
USE hdb_insights;

CREATE TABLE source_dataset (
    dataset_id VARCHAR(3) NOT NULL,
    source_filename VARCHAR(255) NOT NULL,
    source_file_sha256 CHAR(64)
        CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    source_row_count BIGINT NOT NULL,

    PRIMARY KEY (dataset_id),
    UNIQUE KEY uq_source_identity (dataset_id, source_file_sha256),

    CONSTRAINT chk_source_dataset_id
        CHECK (dataset_id IN
            ('D01','D02','D03','D04','D05','D06','D07','D08')),
    CONSTRAINT chk_source_row_count
        CHECK (source_row_count >= 0),
    CONSTRAINT chk_source_hash
        CHECK (source_file_sha256 REGEXP '^[0-9a-f]{64}$')
) ENGINE=InnoDB;

CREATE TABLE town (
    town_id SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,
    town_name VARCHAR(100) NOT NULL,

    PRIMARY KEY (town_id),
    UNIQUE KEY uq_town_name (town_name),

    CONSTRAINT chk_town_name
        CHECK (CHAR_LENGTH(TRIM(town_name)) > 0)
) ENGINE=InnoDB;