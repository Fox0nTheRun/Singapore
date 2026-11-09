-- HDB Insights | Contract HDBI-1.0.0
USE hdb_insights;

CREATE TABLE flat_type (
    flat_type_code VARCHAR(20) NOT NULL,
    display_label VARCHAR(100) NOT NULL,
    is_total BOOLEAN NOT NULL DEFAULT FALSE,

    PRIMARY KEY (flat_type_code),

    CONSTRAINT chk_flat_type_code CHECK (
        flat_type_code IN (
            '1_ROOM', '2_ROOM', '3_ROOM', '4_ROOM',
            '5_ROOM', 'EXECUTIVE', 'MULTI_GENERATION', 'ALL'
        )
    ),
    CONSTRAINT chk_flat_type_total CHECK (
        (flat_type_code = 'ALL' AND is_total = 1)
        OR (flat_type_code <> 'ALL' AND is_total = 0)
    )
) ENGINE=InnoDB;

CREATE TABLE ethnic_group (
    ethnic_group_code VARCHAR(20) NOT NULL,
    display_label VARCHAR(100) NOT NULL,
    is_total BOOLEAN NOT NULL DEFAULT FALSE,

    PRIMARY KEY (ethnic_group_code),

    CONSTRAINT chk_ethnic_group_code CHECK (
        ethnic_group_code IN (
            'CHINESE', 'MALAY', 'INDIAN', 'OTHERS', 'ALL'
        )
    ),
    CONSTRAINT chk_ethnic_group_total CHECK (
        (ethnic_group_code = 'ALL' AND is_total = 1)
        OR (ethnic_group_code <> 'ALL' AND is_total = 0)
    )
) ENGINE=InnoDB;

CREATE TABLE age_group (
    age_group_code VARCHAR(20) NOT NULL,
    display_label VARCHAR(100) NOT NULL,
    sort_order TINYINT UNSIGNED NOT NULL,

    PRIMARY KEY (age_group_code),
    UNIQUE KEY uq_age_group_sort_order (sort_order),

    CONSTRAINT chk_age_group_order CHECK (
        (age_group_code = 'BELOW_15' AND sort_order = 1)
        OR (age_group_code = 'AGE_15_64' AND sort_order = 2)
        OR (age_group_code = 'AGE_65_PLUS' AND sort_order = 3)
    )
) ENGINE=InnoDB;