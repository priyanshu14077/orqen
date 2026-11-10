"""Database roles and row-level security.

1. Four NOLOGIN roles replace `orqen_app`. Services connect as the table owner and
   switch per transaction with `SET LOCAL ROLE` (orqen_core.db.tenant_tx):

   orqen_contestant  a signed-in user acting for themselves
   orqen_setter      member of orqen_contestant, plus writing problems they author
   orqen_admin       member of orqen_setter, plus everything in the tenant
   orqen_worker      orchestrator, executors, grader, proxy and webhooks

   The human roles nest through role membership, so a policy written `TO
   orqen_contestant` also applies to setters and admins. Policies are permissive, so a
   role sees the union of its own policies and those of the roles it contains.

2. Every table gets `ENABLE ROW LEVEL SECURITY` and its policies in this one
   transaction, so no table is ever on with zero policies. The owner bypasses RLS, so
   migrations and the seed are unaffected. Policies read the tenant and user from
   `app.tenant_id` and `app.user_id`, which tenant_tx sets with SET LOCAL.

3. Grants narrow what policies can't. Contestants insert submissions through a column
   list that excludes `score`, `status`, `ranked` and `eval_rule_id`. A trigger pins
   the active eval rule and sets `ranked = false` when the submitter authored the
   problem. Contestants read hidden-test verdicts and scores, never outputs or judge
   reasons: those columns aren't granted, and `judging.sample_test_outputs` returns
   them for sample tests only.

4. Helper functions that read other tables are SECURITY DEFINER with an empty
   search_path, so one table's policy never recurses into another table's policies.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-10
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

SCHEMAS = ("identity", "authoring", "judging", "competition", "billing", "ops")
ROLES = ("orqen_contestant", "orqen_setter", "orqen_admin", "orqen_worker")
TABLES = (
    "identity.tenants",
    "identity.users",
    "identity.memberships",
    "authoring.problems",
    "authoring.problem_authors",
    "authoring.eval_rules",
    "authoring.calibration_examples",
    "authoring.test_cases",
    "judging.submissions",
    "judging.test_results",
    "competition.contests",
    "competition.contest_problems",
    "competition.contest_standings",
    "competition.practice_bests",
    "billing.plans",
    "billing.subscriptions",
    "billing.usage_periods",
    "billing.model_prices",
    "billing.paddle_events",
    "ops.llm_usage",
    "ops.audit_log",
)
FUNCTIONS = (
    "identity.tenant_id()",
    "identity.user_id()",
    "identity.shares_tenant(uuid)",
    "authoring.is_author(uuid)",
    "authoring.is_rule_author(uuid)",
    "authoring.problem_is_listed(uuid)",
    "competition.problem_in_started_contest(uuid)",
    "competition.contest_has_started(uuid)",
    "competition.contest_is_running(uuid)",
    "competition.contest_has_ended(uuid)",
    "judging.owns_submission(uuid)",
)

# The tenant and user of the current transaction. Wrapped in SELECT so the planner
# evaluates each once per statement instead of once per row.
T = "tenant_id = (SELECT identity.tenant_id())"
ME = "(SELECT identity.user_id())"


def upgrade() -> None:
    roles = ", ".join(ROLES)
    op.execute(f"""
    DO $$
    DECLARE
        r text;
    BEGIN
        FOREACH r IN ARRAY ARRAY{list(ROLES)} LOOP
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = r) THEN
                EXECUTE format('CREATE ROLE %I NOLOGIN', r);
            END IF;
        END LOOP;
    END
    $$;
    GRANT {roles} TO CURRENT_USER;
    GRANT orqen_contestant TO orqen_setter;
    GRANT orqen_setter TO orqen_admin;
    GRANT USAGE ON SCHEMA {", ".join(SCHEMAS)} TO {roles};
    """)

    # orqen_app is retired. The role stays because roles are cluster-wide.
    op.execute(f"""
    REVOKE ALL ON ALL TABLES IN SCHEMA {", ".join(SCHEMAS)} FROM orqen_app;
    REVOKE USAGE ON SCHEMA public, {", ".join(SCHEMAS)} FROM orqen_app;
    """)

    op.execute("""
    CREATE FUNCTION identity.tenant_id() RETURNS uuid
        LANGUAGE sql STABLE
        AS $$ SELECT nullif(current_setting('app.tenant_id', true), '')::uuid $$;

    CREATE FUNCTION identity.user_id() RETURNS uuid
        LANGUAGE sql STABLE
        AS $$ SELECT nullif(current_setting('app.user_id', true), '')::uuid $$;

    CREATE FUNCTION identity.shares_tenant(p_user uuid) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
        AS $$
            SELECT EXISTS (
                SELECT FROM identity.memberships
                WHERE tenant_id = identity.tenant_id() AND user_id = p_user
            )
        $$;

    CREATE FUNCTION authoring.is_author(p_problem uuid) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
        AS $$
            SELECT EXISTS (
                SELECT FROM authoring.problem_authors
                WHERE problem_id = p_problem AND user_id = identity.user_id()
            )
        $$;

    CREATE FUNCTION authoring.is_rule_author(p_rule uuid) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
        AS $$
            SELECT EXISTS (
                SELECT FROM authoring.eval_rules r
                JOIN authoring.problem_authors a ON a.problem_id = r.problem_id
                WHERE r.id = p_rule AND a.user_id = identity.user_id()
            )
        $$;

    -- In the practice archive: published, and not in a contest that hasn't ended.
    CREATE FUNCTION authoring.problem_is_listed(p_problem uuid) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
        AS $$
            SELECT EXISTS (
                SELECT FROM authoring.problems p
                WHERE p.id = p_problem AND p.visibility = 'published'
                  AND NOT EXISTS (
                      SELECT FROM competition.contest_problems cp
                      JOIN competition.contests c ON c.id = cp.contest_id
                      WHERE cp.problem_id = p.id AND c.ends_at > now()
                  )
            )
        $$;

    CREATE FUNCTION competition.contest_has_started(p_contest uuid) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
        AS $$
            SELECT EXISTS (
                SELECT FROM competition.contests
                WHERE id = p_contest AND visibility = 'published' AND starts_at <= now()
            )
        $$;

    CREATE FUNCTION competition.contest_is_running(p_contest uuid) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
        AS $$
            SELECT EXISTS (
                SELECT FROM competition.contests
                WHERE id = p_contest AND visibility = 'published'
                  AND starts_at <= now() AND now() < ends_at
            )
        $$;

    CREATE FUNCTION competition.contest_has_ended(p_contest uuid) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
        AS $$
            SELECT EXISTS (
                SELECT FROM competition.contests
                WHERE id = p_contest AND visibility = 'published' AND ends_at <= now()
            )
        $$;

    CREATE FUNCTION competition.problem_in_started_contest(p_problem uuid) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
        AS $$
            SELECT EXISTS (
                SELECT FROM competition.contest_problems cp
                JOIN competition.contests c ON c.id = cp.contest_id
                WHERE cp.problem_id = p_problem
                  AND c.visibility = 'published' AND c.starts_at <= now()
            )
        $$;

    CREATE FUNCTION judging.owns_submission(p_submission uuid) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
        AS $$
            SELECT EXISTS (
                SELECT FROM judging.submissions
                WHERE id = p_submission AND user_id = identity.user_id()
            )
        $$;
    """)

    functions = ", ".join(FUNCTIONS)
    op.execute(f"""
    REVOKE EXECUTE ON FUNCTION {functions} FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION {functions} TO orqen_contestant, orqen_worker;
    """)

    # Triggers: values a client must not choose.
    op.execute("""
    -- Whoever creates a problem is its first author.
    CREATE FUNCTION authoring.add_creator_as_author() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
        AS $$
        BEGIN
            IF NEW.created_by IS NOT NULL THEN
                INSERT INTO authoring.problem_authors (tenant_id, problem_id, user_id)
                VALUES (NEW.tenant_id, NEW.id, NEW.created_by)
                ON CONFLICT DO NOTHING;
            END IF;
            RETURN NULL;
        END
        $$;
    CREATE TRIGGER problems_add_creator_as_author
        AFTER INSERT ON authoring.problems
        FOR EACH ROW EXECUTE FUNCTION authoring.add_creator_as_author();

    -- Pins the active eval rule and decides whether the submission is ranked.
    CREATE FUNCTION judging.prepare_submission() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
        AS $$
        BEGIN
            IF NEW.eval_rule_id IS NULL THEN
                SELECT id INTO NEW.eval_rule_id
                FROM authoring.eval_rules
                WHERE problem_id = NEW.problem_id AND status = 'active';
                IF NEW.eval_rule_id IS NULL THEN
                    RAISE EXCEPTION 'problem % has no active eval rule', NEW.problem_id
                        USING ERRCODE = 'check_violation';
                END IF;
            END IF;
            NEW.ranked := NOT EXISTS (
                SELECT FROM authoring.problem_authors
                WHERE problem_id = NEW.problem_id AND user_id = NEW.user_id
            );
            RETURN NEW;
        END
        $$;
    CREATE TRIGGER submissions_prepare
        BEFORE INSERT ON judging.submissions
        FOR EACH ROW EXECUTE FUNCTION judging.prepare_submission();

    REVOKE EXECUTE ON FUNCTION authoring.add_creator_as_author(), judging.prepare_submission()
        FROM PUBLIC;
    """)

    # Sample-test outputs for the current user. The view runs as its owner, so it
    # filters by the session's tenant and user itself.
    op.execute("""
    CREATE VIEW judging.sample_test_outputs WITH (security_barrier) AS
    SELECT r.submission_id, r.test_case_id, r.output, r.criterion_scores,
           r.judge_reason, r.error_msg
    FROM judging.test_results r
    JOIN judging.submissions s ON s.id = r.submission_id
    JOIN authoring.test_cases t ON t.id = r.test_case_id
    WHERE t.is_sample
      AND s.tenant_id = identity.tenant_id()
      AND s.user_id = identity.user_id();
    GRANT SELECT ON judging.sample_test_outputs TO orqen_contestant;
    """)

    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")

    op.execute(f"""
    -- identity ---------------------------------------------------------------
    GRANT SELECT (id, slug, name, settings, created_at) ON identity.tenants
        TO orqen_contestant;
    GRANT UPDATE (name, settings) ON identity.tenants TO orqen_admin;
    GRANT SELECT ON identity.tenants TO orqen_worker;
    CREATE POLICY contestant_read ON identity.tenants FOR SELECT TO orqen_contestant
        USING (id = (SELECT identity.tenant_id()));
    CREATE POLICY admin_update ON identity.tenants FOR UPDATE TO orqen_admin
        USING (id = (SELECT identity.tenant_id()));
    CREATE POLICY worker_read ON identity.tenants FOR SELECT TO orqen_worker
        USING (id = (SELECT identity.tenant_id()));

    GRANT SELECT ON identity.users TO orqen_contestant;
    GRANT SELECT, INSERT, UPDATE ON identity.users TO orqen_worker;
    CREATE POLICY contestant_self ON identity.users FOR SELECT TO orqen_contestant
        USING (id = {ME});
    CREATE POLICY admin_tenant ON identity.users FOR SELECT TO orqen_admin
        USING (identity.shares_tenant(id));
    CREATE POLICY worker_all ON identity.users TO orqen_worker USING (true);

    GRANT SELECT ON identity.memberships TO orqen_contestant;
    GRANT INSERT, UPDATE, DELETE ON identity.memberships TO orqen_admin;
    GRANT SELECT, INSERT ON identity.memberships TO orqen_worker;
    CREATE POLICY contestant_self ON identity.memberships FOR SELECT TO orqen_contestant
        USING ({T} AND user_id = {ME});
    CREATE POLICY admin_tenant ON identity.memberships TO orqen_admin USING ({T});
    CREATE POLICY worker_tenant ON identity.memberships TO orqen_worker USING ({T});

    -- authoring --------------------------------------------------------------
    GRANT SELECT ON authoring.problems TO orqen_contestant;
    GRANT INSERT, UPDATE, DELETE ON authoring.problems TO orqen_setter;
    GRANT SELECT ON authoring.problems TO orqen_worker;
    CREATE POLICY contestant_open ON authoring.problems FOR SELECT TO orqen_contestant
        USING ({T} AND (authoring.problem_is_listed(id)
                        OR competition.problem_in_started_contest(id)));
    CREATE POLICY setter_own ON authoring.problems TO orqen_setter
        USING ({T} AND (created_by = {ME} OR authoring.is_author(id)))
        WITH CHECK ({T} AND (created_by = {ME} OR authoring.is_author(id)));
    CREATE POLICY admin_tenant ON authoring.problems TO orqen_admin USING ({T});
    CREATE POLICY worker_tenant ON authoring.problems FOR SELECT TO orqen_worker
        USING ({T});

    GRANT SELECT, INSERT, DELETE ON authoring.problem_authors TO orqen_setter;
    GRANT SELECT ON authoring.problem_authors TO orqen_worker;
    CREATE POLICY setter_own ON authoring.problem_authors TO orqen_setter
        USING ({T} AND authoring.is_author(problem_id));
    CREATE POLICY admin_tenant ON authoring.problem_authors TO orqen_admin USING ({T});
    CREATE POLICY worker_tenant ON authoring.problem_authors FOR SELECT TO orqen_worker
        USING ({T});

    GRANT SELECT, INSERT, UPDATE ON authoring.eval_rules TO orqen_setter;
    GRANT SELECT, UPDATE ON authoring.eval_rules TO orqen_worker;
    CREATE POLICY setter_own ON authoring.eval_rules TO orqen_setter
        USING ({T} AND authoring.is_author(problem_id));
    CREATE POLICY admin_tenant ON authoring.eval_rules TO orqen_admin USING ({T});
    CREATE POLICY worker_tenant ON authoring.eval_rules TO orqen_worker USING ({T});

    GRANT SELECT, INSERT, UPDATE, DELETE ON authoring.calibration_examples TO orqen_setter;
    GRANT SELECT ON authoring.calibration_examples TO orqen_worker;
    CREATE POLICY setter_own ON authoring.calibration_examples TO orqen_setter
        USING ({T} AND authoring.is_rule_author(eval_rule_id));
    CREATE POLICY admin_tenant ON authoring.calibration_examples TO orqen_admin
        USING ({T});
    CREATE POLICY worker_tenant ON authoring.calibration_examples FOR SELECT
        TO orqen_worker USING ({T});

    GRANT SELECT ON authoring.test_cases TO orqen_contestant;
    GRANT INSERT, UPDATE, DELETE ON authoring.test_cases TO orqen_setter;
    GRANT SELECT ON authoring.test_cases TO orqen_worker;
    CREATE POLICY contestant_samples ON authoring.test_cases FOR SELECT TO orqen_contestant
        USING ({T} AND is_sample AND (authoring.problem_is_listed(problem_id)
                                      OR competition.problem_in_started_contest(problem_id)));
    CREATE POLICY setter_own ON authoring.test_cases TO orqen_setter
        USING ({T} AND authoring.is_author(problem_id));
    CREATE POLICY admin_tenant ON authoring.test_cases TO orqen_admin USING ({T});
    CREATE POLICY worker_tenant ON authoring.test_cases FOR SELECT TO orqen_worker
        USING ({T});

    -- judging ----------------------------------------------------------------
    GRANT SELECT ON judging.submissions TO orqen_contestant;
    GRANT INSERT (tenant_id, user_id, problem_id, contest_id, kind, mode, payload,
                  idempotency_key, trace_id)
        ON judging.submissions TO orqen_contestant;
    GRANT SELECT, UPDATE ON judging.submissions TO orqen_worker;
    -- Your own submissions, and everyone's contest submits once the contest has ended.
    CREATE POLICY contestant_read ON judging.submissions FOR SELECT TO orqen_contestant
        USING ({T} AND (user_id = {ME}
                        OR (contest_id IS NOT NULL AND mode = 'submit'
                            AND competition.contest_has_ended(contest_id))));
    CREATE POLICY contestant_submit ON judging.submissions FOR INSERT TO orqen_contestant
        WITH CHECK ({T} AND user_id = {ME} AND (
            (contest_id IS NULL AND authoring.problem_is_listed(problem_id))
            OR (contest_id IS NOT NULL AND competition.contest_is_running(contest_id))
            OR authoring.is_author(problem_id)));
    CREATE POLICY setter_own_problems ON judging.submissions FOR SELECT TO orqen_setter
        USING ({T} AND authoring.is_author(problem_id));
    CREATE POLICY admin_tenant ON judging.submissions FOR SELECT TO orqen_admin
        USING ({T});
    CREATE POLICY worker_tenant ON judging.submissions TO orqen_worker USING ({T});

    GRANT SELECT (submission_id, test_case_id, tenant_id, verdict, score, latency_ms,
                  tokens, created_at)
        ON judging.test_results TO orqen_contestant;
    GRANT SELECT ON judging.test_results TO orqen_admin;
    GRANT SELECT, INSERT, UPDATE ON judging.test_results TO orqen_worker;
    CREATE POLICY contestant_own ON judging.test_results FOR SELECT TO orqen_contestant
        USING ({T} AND judging.owns_submission(submission_id));
    CREATE POLICY admin_tenant ON judging.test_results FOR SELECT TO orqen_admin
        USING ({T});
    CREATE POLICY worker_tenant ON judging.test_results TO orqen_worker USING ({T});

    -- competition ------------------------------------------------------------
    GRANT SELECT ON competition.contests TO orqen_contestant, orqen_worker;
    GRANT INSERT, UPDATE, DELETE ON competition.contests TO orqen_admin;
    CREATE POLICY contestant_published ON competition.contests FOR SELECT
        TO orqen_contestant USING ({T} AND visibility = 'published');
    CREATE POLICY setter_tenant ON competition.contests FOR SELECT TO orqen_setter
        USING ({T});
    CREATE POLICY admin_tenant ON competition.contests TO orqen_admin USING ({T});
    CREATE POLICY worker_tenant ON competition.contests FOR SELECT TO orqen_worker
        USING ({T});

    GRANT SELECT ON competition.contest_problems TO orqen_contestant, orqen_worker;
    GRANT INSERT, UPDATE, DELETE ON competition.contest_problems TO orqen_admin;
    CREATE POLICY contestant_started ON competition.contest_problems FOR SELECT
        TO orqen_contestant USING ({T} AND competition.contest_has_started(contest_id));
    CREATE POLICY setter_tenant ON competition.contest_problems FOR SELECT TO orqen_setter
        USING ({T});
    CREATE POLICY admin_tenant ON competition.contest_problems TO orqen_admin USING ({T});
    CREATE POLICY worker_tenant ON competition.contest_problems FOR SELECT TO orqen_worker
        USING ({T});

    GRANT SELECT ON competition.contest_standings TO orqen_contestant;
    GRANT SELECT, INSERT, UPDATE ON competition.contest_standings TO orqen_worker;
    CREATE POLICY contestant_started ON competition.contest_standings FOR SELECT
        TO orqen_contestant USING ({T} AND competition.contest_has_started(contest_id));
    CREATE POLICY admin_tenant ON competition.contest_standings FOR SELECT TO orqen_admin
        USING ({T});
    CREATE POLICY worker_tenant ON competition.contest_standings TO orqen_worker
        USING ({T});

    GRANT SELECT ON competition.practice_bests TO orqen_contestant;
    GRANT SELECT, INSERT, UPDATE ON competition.practice_bests TO orqen_worker;
    CREATE POLICY contestant_tenant ON competition.practice_bests FOR SELECT
        TO orqen_contestant USING ({T});
    CREATE POLICY worker_tenant ON competition.practice_bests TO orqen_worker USING ({T});

    -- billing ----------------------------------------------------------------
    GRANT SELECT ON billing.plans TO orqen_contestant, orqen_worker;
    CREATE POLICY contestant_active ON billing.plans FOR SELECT TO orqen_contestant
        USING (active);
    CREATE POLICY admin_all ON billing.plans FOR SELECT TO orqen_admin USING (true);
    CREATE POLICY worker_all ON billing.plans FOR SELECT TO orqen_worker USING (true);

    GRANT SELECT ON billing.subscriptions TO orqen_contestant;
    GRANT SELECT, INSERT, UPDATE ON billing.subscriptions TO orqen_worker;
    CREATE POLICY contestant_own ON billing.subscriptions FOR SELECT TO orqen_contestant
        USING ({T} AND user_id = {ME});
    CREATE POLICY admin_tenant ON billing.subscriptions FOR SELECT TO orqen_admin
        USING ({T});
    CREATE POLICY worker_tenant ON billing.subscriptions TO orqen_worker USING ({T});

    GRANT SELECT ON billing.usage_periods TO orqen_contestant;
    GRANT SELECT, INSERT, UPDATE ON billing.usage_periods TO orqen_worker;
    CREATE POLICY contestant_own ON billing.usage_periods FOR SELECT TO orqen_contestant
        USING ({T} AND user_id = {ME});
    CREATE POLICY admin_tenant ON billing.usage_periods FOR SELECT TO orqen_admin
        USING ({T});
    CREATE POLICY worker_tenant ON billing.usage_periods TO orqen_worker USING ({T});

    GRANT SELECT ON billing.model_prices TO orqen_admin, orqen_worker;
    CREATE POLICY admin_all ON billing.model_prices FOR SELECT TO orqen_admin USING (true);
    CREATE POLICY worker_all ON billing.model_prices FOR SELECT TO orqen_worker
        USING (true);

    -- Paddle webhooks arrive before Orqen knows the tenant, so no tenant filter.
    GRANT SELECT, INSERT, UPDATE ON billing.paddle_events TO orqen_worker;
    CREATE POLICY worker_all ON billing.paddle_events TO orqen_worker USING (true);

    -- ops --------------------------------------------------------------------
    GRANT SELECT ON ops.llm_usage TO orqen_contestant;
    GRANT SELECT, INSERT ON ops.llm_usage TO orqen_worker;
    CREATE POLICY contestant_own ON ops.llm_usage FOR SELECT TO orqen_contestant
        USING ({T} AND user_id = {ME});
    CREATE POLICY admin_tenant ON ops.llm_usage FOR SELECT TO orqen_admin USING ({T});
    CREATE POLICY worker_tenant ON ops.llm_usage TO orqen_worker USING ({T});

    GRANT SELECT, INSERT ON ops.audit_log TO orqen_admin, orqen_worker;
    CREATE POLICY admin_tenant ON ops.audit_log TO orqen_admin
        USING ({T}) WITH CHECK ({T} AND actor_id = {ME});
    CREATE POLICY worker_tenant ON ops.audit_log TO orqen_worker USING ({T});
    """)


def downgrade() -> None:
    op.execute(f"""
    DO $$
    DECLARE
        p record;
    BEGIN
        FOR p IN
            SELECT schemaname, tablename, policyname FROM pg_policies
            WHERE schemaname = ANY (ARRAY{list(SCHEMAS)})
        LOOP
            EXECUTE format('DROP POLICY %I ON %I.%I', p.policyname, p.schemaname, p.tablename);
        END LOOP;
    END
    $$;
    """)
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.execute(f"""
    DROP VIEW judging.sample_test_outputs;
    DROP TRIGGER submissions_prepare ON judging.submissions;
    DROP TRIGGER problems_add_creator_as_author ON authoring.problems;
    DROP FUNCTION judging.prepare_submission(), authoring.add_creator_as_author(),
        {", ".join(FUNCTIONS)};
    REVOKE ALL ON ALL TABLES IN SCHEMA {", ".join(SCHEMAS)} FROM {", ".join(ROLES)};
    REVOKE USAGE ON SCHEMA {", ".join(SCHEMAS)} FROM {", ".join(ROLES)};
    """)

    # Restore orqen_app as 0001 and 0003 left it. The new roles stay: roles are
    # cluster-wide.
    op.execute(f"""
    GRANT USAGE ON SCHEMA public, {", ".join(SCHEMAS)} TO orqen_app;
    GRANT SELECT, INSERT, UPDATE, DELETE ON
        identity.tenants, identity.users, identity.memberships, authoring.problems,
        authoring.eval_rules, authoring.calibration_examples, authoring.test_cases,
        judging.submissions, judging.test_results,
        authoring.problem_authors, competition.contests, competition.contest_problems,
        competition.contest_standings, competition.practice_bests,
        billing.subscriptions, billing.usage_periods
        TO orqen_app;
    GRANT SELECT, INSERT ON ops.llm_usage, ops.audit_log TO orqen_app;
    GRANT SELECT ON billing.plans, billing.model_prices TO orqen_app;
    GRANT SELECT, INSERT, UPDATE ON billing.paddle_events TO orqen_app;
    """)
