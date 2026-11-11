"""Public handles for leaderboards, and per-plan submission limits.

1. `identity.users.handle` is the name leaderboards show, because email stays private.
   Handles are lower case, 3 to 20 characters of `a-z`, `0-9` and `_`, start with a
   letter or digit, and are unique. A trigger derives one from the email when a user
   is inserted without one; existing users are backfilled the same way.

   Contestants can now read the id and handle of every user in their tenant, never
   the email, and can change their own handle. Admins keep full read access.

2. A BEFORE INSERT trigger on `judging.submissions` enforces the plan limits for
   contestants. Admins and setters are exempt.

   no live subscription         SQLSTATE OQ402
   trial submission cap         SQLSTATE OQ402  (plans.submission_cap per period)
   sample runs per hour         SQLSTATE OQ429  (plans.runs_per_hour, rolling hour)
   contest submits per problem  SQLSTATE OQ429  (contests.max_submits_per_problem)

   The trigger takes a per-user advisory lock, so two concurrent inserts can't both
   pass a count. The gateway maps the SQLSTATEs to HTTP 402 and 429.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-10
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

ME = "(SELECT identity.user_id())"


def upgrade() -> None:
    op.execute("""
    -- The handle a user would get from their email, before de-duplication.
    CREATE FUNCTION identity.handle_from_email(p_email text) RETURNS text
        LANGUAGE plpgsql IMMUTABLE SET search_path = ''
        AS $$
        DECLARE
            h text := lower(split_part(p_email, '@', 1));
        BEGIN
            h := regexp_replace(h, '[^a-z0-9_]', '_', 'g');
            h := rtrim(left(regexp_replace(h, '^_+', ''), 20), '_');
            IF length(h) < 3 THEN
                h := 'user_' || h;
            END IF;
            RETURN h;
        END
        $$;

    ALTER TABLE identity.users ADD COLUMN handle text;

    WITH ranked AS (
        SELECT id, identity.handle_from_email(email) AS base,
               row_number() OVER (
                   PARTITION BY identity.handle_from_email(email) ORDER BY created_at, id
               ) AS n
        FROM identity.users
    )
    UPDATE identity.users u
    SET handle = CASE WHEN r.n = 1 THEN r.base ELSE left(r.base, 16) || '_' || r.n END
    FROM ranked r
    WHERE r.id = u.id;

    ALTER TABLE identity.users
        ALTER COLUMN handle SET NOT NULL,
        ADD CONSTRAINT users_handle_format CHECK (handle ~ '^[a-z0-9][a-z0-9_]{2,19}$'),
        ADD CONSTRAINT users_handle_key UNIQUE (handle);

    -- Fills handle when the inserter leaves it out: the email's handle, or the first
    -- free `<handle>_<n>`.
    CREATE FUNCTION identity.assign_handle() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
        AS $$
        DECLARE
            base text;
            candidate text;
            n int := 1;
        BEGIN
            IF NEW.handle IS NOT NULL THEN
                RETURN NEW;
            END IF;
            base := identity.handle_from_email(NEW.email);
            candidate := base;
            WHILE EXISTS (SELECT FROM identity.users WHERE handle = candidate) LOOP
                n := n + 1;
                candidate := left(base, 16) || '_' || n;
            END LOOP;
            NEW.handle := candidate;
            RETURN NEW;
        END
        $$;
    CREATE TRIGGER users_assign_handle
        BEFORE INSERT ON identity.users
        FOR EACH ROW EXECUTE FUNCTION identity.assign_handle();
    REVOKE EXECUTE ON FUNCTION identity.assign_handle() FROM PUBLIC;
    """)

    # Contestants see handles, not emails, across their tenant.
    op.execute(f"""
    REVOKE SELECT ON identity.users FROM orqen_contestant;
    GRANT SELECT (id, handle, is_platform_owner, created_at) ON identity.users
        TO orqen_contestant;
    GRANT UPDATE (handle) ON identity.users TO orqen_contestant;
    GRANT SELECT ON identity.users TO orqen_admin;

    DROP POLICY contestant_self ON identity.users;
    CREATE POLICY contestant_tenant ON identity.users FOR SELECT TO orqen_contestant
        USING (identity.shares_tenant(id));
    CREATE POLICY contestant_rename ON identity.users FOR UPDATE TO orqen_contestant
        USING (id = {ME}) WITH CHECK (id = {ME});
    """)

    op.execute("""
    CREATE FUNCTION judging.enforce_plan_limits() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
        AS $$
        DECLARE
            member_role text;
            sub record;
            used int;
            contest_cap int;
        BEGIN
            SELECT role INTO member_role FROM identity.memberships
            WHERE tenant_id = NEW.tenant_id AND user_id = NEW.user_id;
            IF member_role IN ('admin', 'setter') THEN
                RETURN NEW;
            END IF;

            -- Serialise this user's inserts so concurrent submits can't both pass a count.
            PERFORM pg_advisory_xact_lock(hashtextextended('orqen.submit:' || NEW.user_id, 0));

            SELECT s.current_period_start, p.runs_per_hour, p.submission_cap
            INTO sub
            FROM billing.subscriptions s
            JOIN billing.plans p ON p.id = s.plan_id
            WHERE s.tenant_id = NEW.tenant_id AND s.user_id = NEW.user_id
              AND s.status IN ('trialing', 'active')
              AND now() >= s.current_period_start AND now() < s.current_period_end;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'no live subscription'
                    USING ERRCODE = 'OQ402', HINT = 'subscribe';
            END IF;

            IF NEW.mode = 'run' THEN
                SELECT count(*) INTO used FROM judging.submissions
                WHERE user_id = NEW.user_id AND mode = 'run'
                  AND created_at > now() - interval '1 hour';
                IF used >= sub.runs_per_hour THEN
                    RAISE EXCEPTION 'sample run limit of % per hour reached', sub.runs_per_hour
                        USING ERRCODE = 'OQ429', HINT = 'runs_per_hour';
                END IF;
                RETURN NEW;
            END IF;

            IF sub.submission_cap IS NOT NULL THEN
                SELECT count(*) INTO used FROM judging.submissions
                WHERE user_id = NEW.user_id AND mode = 'submit'
                  AND created_at >= sub.current_period_start;
                IF used >= sub.submission_cap THEN
                    RAISE EXCEPTION 'plan allows % submissions per period', sub.submission_cap
                        USING ERRCODE = 'OQ402', HINT = 'submission_cap';
                END IF;
            END IF;

            IF NEW.contest_id IS NOT NULL THEN
                SELECT max_submits_per_problem INTO contest_cap
                FROM competition.contests WHERE id = NEW.contest_id;
                IF contest_cap IS NOT NULL THEN
                    SELECT count(*) INTO used FROM judging.submissions
                    WHERE contest_id = NEW.contest_id AND user_id = NEW.user_id
                      AND problem_id = NEW.problem_id AND mode = 'submit';
                    IF used >= contest_cap THEN
                        RAISE EXCEPTION 'contest allows % submits per problem', contest_cap
                            USING ERRCODE = 'OQ429', HINT = 'max_submits_per_problem';
                    END IF;
                END IF;
            END IF;
            RETURN NEW;
        END
        $$;
    -- Triggers fire in name order: limits are checked before submissions_prepare runs.
    CREATE TRIGGER submissions_enforce_limits
        BEFORE INSERT ON judging.submissions
        FOR EACH ROW EXECUTE FUNCTION judging.enforce_plan_limits();
    REVOKE EXECUTE ON FUNCTION judging.enforce_plan_limits() FROM PUBLIC;

    -- The hourly run count reads this.
    CREATE INDEX submissions_user_mode_idx ON judging.submissions
        (user_id, mode, created_at DESC);
    """)


def downgrade() -> None:
    op.execute(f"""
    DROP INDEX judging.submissions_user_mode_idx;
    DROP TRIGGER submissions_enforce_limits ON judging.submissions;
    DROP FUNCTION judging.enforce_plan_limits();

    DROP POLICY contestant_rename ON identity.users;
    DROP POLICY contestant_tenant ON identity.users;
    CREATE POLICY contestant_self ON identity.users FOR SELECT TO orqen_contestant
        USING (id = {ME});
    REVOKE SELECT ON identity.users FROM orqen_admin;
    REVOKE SELECT (id, handle, is_platform_owner, created_at), UPDATE (handle)
        ON identity.users FROM orqen_contestant;
    GRANT SELECT ON identity.users TO orqen_contestant;

    DROP TRIGGER users_assign_handle ON identity.users;
    DROP FUNCTION identity.assign_handle();
    ALTER TABLE identity.users DROP COLUMN handle;
    DROP FUNCTION identity.handle_from_email(text);
    """)
