USE hdb_insights_demo;

DELIMITER //

CREATE TRIGGER trg_demo_seed_immutable
BEFORE UPDATE ON demo_seed
FOR EACH ROW
BEGIN
    IF NOT (BINARY NEW.seed_record_id <=> BINARY OLD.seed_record_id)
       OR NOT (
           BINARY NEW.base_data_release_id
           <=> BINARY OLD.base_data_release_id
       )
       OR NOT (BINARY NEW.dataset_id <=> BINARY OLD.dataset_id)
       OR NOT (
           BINARY NEW.source_file_sha256
           <=> BINARY OLD.source_file_sha256
       )
       OR NOT (NEW.source_row_number <=> OLD.source_row_number)
    THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Demo seed identity and lineage are immutable';
    END IF;
END//


CREATE TRIGGER trg_demo_resale_identity_immutable
BEFORE UPDATE ON demo_resale_transaction
FOR EACH ROW
BEGIN
    IF NOT (
           BINARY NEW.demo_record_id
           <=> BINARY OLD.demo_record_id
       )
       OR NOT (BINARY NEW.record_kind <=> BINARY OLD.record_kind)
       OR NOT (BINARY NEW.seed_record_id <=> BINARY OLD.seed_record_id)
       OR NOT (
           BINARY NEW.base_data_release_id
           <=> BINARY OLD.base_data_release_id
       )
    THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Demo identity and seed reference are immutable';
    END IF;
END//

DELIMITER ;

SHOW TRIGGERS FROM hdb_insights_demo;