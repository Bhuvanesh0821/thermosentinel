-- Stage 3: clearly labelled test-fixture data for demonstrations on a separate database.
--
-- Rows replayed from the test fixture carry source_mode = 'test_fixture' so they can always be
-- told apart from live NASA FIRMS data. The API refuses to run in live mode if any such row
-- exists, and refuses test-fixture mode in production or on a database not named *_test.

ALTER TABLE thermal_observations DROP CONSTRAINT thermal_observations_source_mode_check;
ALTER TABLE thermal_observations
    ADD CONSTRAINT thermal_observations_source_mode_check
    CHECK (source_mode IN ('api', 'public_feed', 'test_fixture'));

CREATE INDEX IF NOT EXISTS ix_observations_test_fixture
    ON thermal_observations (id) WHERE source_mode = 'test_fixture';
