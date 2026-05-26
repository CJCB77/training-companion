-- =============================================================================
-- Row Level Security (RLS) skeleton — user data isolation
-- =============================================================================
--
-- ARCHITECTURE NOTE — read before relying on this:
--
-- In this app the Expo frontend never queries Supabase Postgres directly. Every
-- request goes through the FastAPI backend, which connects using a privileged
-- Postgres role. That role BYPASSES RLS. Therefore RLS is NOT the primary data
-- isolation mechanism here.
--
--   * PRIMARY isolation  -> FastAPI repositories scope every query by the
--                           authenticated user_id (from the validated JWT).
--   * RLS (this file)     -> defense-in-depth safety net for any direct access
--                           via the Supabase dashboard, anon/auth keys, or a
--                           future feature that connects with a non-privileged
--                           role.
--
-- Apply this skeleton in the Supabase SQL editor (or fold it into an Alembic
-- migration with op.execute) once the corresponding tables exist.
--
-- `auth.uid()` returns the Supabase-authenticated user's UUID. It is NULL when
-- queried by a privileged/service role, which is why backend queries are
-- unaffected by these policies.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Per-table template — copy this block for each user-owned table.
-- Replace <table> with the real table name. Assumes the table has a `user_id`
-- column of type uuid referencing the authenticated user.
-- -----------------------------------------------------------------------------

-- ALTER TABLE <table> ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE <table> FORCE ROW LEVEL SECURITY;  -- also enforce for table owner

-- CREATE POLICY "<table>_select_own" ON <table>
--   FOR SELECT USING (user_id = auth.uid());

-- CREATE POLICY "<table>_insert_own" ON <table>
--   FOR INSERT WITH CHECK (user_id = auth.uid());

-- CREATE POLICY "<table>_update_own" ON <table>
--   FOR UPDATE USING (user_id = auth.uid())
--               WITH CHECK (user_id = auth.uid());

-- CREATE POLICY "<table>_delete_own" ON <table>
--   FOR DELETE USING (user_id = auth.uid());


-- -----------------------------------------------------------------------------
-- Concrete tables — uncomment and apply as each model lands.
-- (Names mirror the domain model in CLAUDE.md.)
-- -----------------------------------------------------------------------------

-- programs, training_weeks, workout_days, exercise_prescriptions,
-- exercise_performances, training_history, custom exercises, ...
--
-- For child tables that don't carry user_id directly, isolate via the parent:
--
-- CREATE POLICY "exercise_performances_select_own" ON exercise_performances
--   FOR SELECT USING (
--     EXISTS (
--       SELECT 1 FROM workout_days wd
--       JOIN programs p ON p.id = wd.program_id
--       WHERE wd.id = exercise_performances.workout_day_id
--         AND p.user_id = auth.uid()
--     )
--   );