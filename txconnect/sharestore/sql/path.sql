CREATE VIRTUAL TABLE sharestore_path_fts USING fts4(content="sharestore_path", id, path);

CREATE TRIGGER sharestore_path_bu BEFORE UPDATE ON sharestore_path BEGIN DELETE FROM sharestore_path_fts WHERE docid=old.id; END;

CREATE TRIGGER sharestore_path_bd BEFORE DELETE ON sharestore_path BEGIN DELETE FROM sharestore_path_fts WHERE docid=old.id; END;
    
CREATE TRIGGER sharestore_path_au AFTER UPDATE ON sharestore_path BEGIN INSERT INTO sharestore_path_fts(docid, path) VALUES(new.id, new.path); END;

CREATE TRIGGER sharestore_path_ai AFTER INSERT ON sharestore_path BEGIN INSERT INTO sharestore_path_fts(docid, path) VALUES(new.id, new.path); END;

