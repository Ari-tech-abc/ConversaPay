const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');
const modulePath = process.env.PGLITE_MODULE || '@electric-sql/pglite';
const { PGlite } = require(modulePath);
const distPath = path.dirname(require.resolve(modulePath));
const { pgcrypto } = require(path.join(distPath, 'contrib/pgcrypto.cjs'));
const { uuid_ossp } = require(path.join(distPath, 'contrib/uuid_ossp.cjs'));
(async () => {
  const db = new PGlite({ extensions: { pgcrypto, uuid_ossp } });
  try {
    await db.exec(`CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;
      CREATE SCHEMA auth; CREATE TABLE auth.users(id UUID PRIMARY KEY, email_confirmed_at TIMESTAMPTZ);
      CREATE FUNCTION auth.uid() RETURNS UUID LANGUAGE SQL AS $$ SELECT nullif(current_setting('request.jwt.claim.sub', true),'')::uuid $$;
      GRANT USAGE ON SCHEMA public, auth TO anon, authenticated, service_role;
      ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated;
      CREATE TABLE public.schema_migrations(name TEXT PRIMARY KEY, checksum TEXT NOT NULL);`);
    const root = path.join(__dirname, '../database');
    const files = ['full_schema_bootstrap.sql', ...fs.readdirSync(path.join(root, 'migrations')).filter(f => f.endsWith('.sql')).sort().map(f => `migrations/${f}`)];
    await db.exec('BEGIN');
    for (const file of files) {
      try { await db.exec(fs.readFileSync(path.join(root, file), 'utf8')); }
      catch (error) { throw new Error(`${file}: ${error.message}`); }
    }
    await db.exec('COMMIT');
    const scalar = async (sql, params = []) => (await db.query(sql, params)).rows[0].value;
    const tables = (await db.query("SELECT tablename FROM pg_tables WHERE schemaname='public'")).rows;
    for (const { tablename } of tables) {
      assert.equal(await scalar('SELECT relrowsecurity AS value FROM pg_class WHERE oid=$1::regclass', [`public.${tablename}`]), true, tablename);
      for (const role of ['anon', 'authenticated']) {
        for (const privilege of ['SELECT', 'INSERT', 'UPDATE', 'DELETE']) {
          assert.equal(await scalar('SELECT has_table_privilege($1,$2,$3) AS value', [role, `public.${tablename}`, privilege]), false, `${role}/${tablename}/${privilege}`);
        }
      }
      assert.equal(await scalar('SELECT has_table_privilege($1,$2,$3) AS value', ['service_role', `public.${tablename}`, 'SELECT,INSERT,UPDATE,DELETE']), true);
    }
    const user = '00000000-0000-4000-8000-000000000001';
    const business = '00000000-0000-4000-8000-000000000002';
    const order = '00000000-0000-4000-8000-000000000003';
    await db.query('INSERT INTO auth.users(id) VALUES($1)', [user]);
    await db.query("INSERT INTO public.profiles(user_id,email_verification_token,email_verification_expires_at) VALUES($1,'0123456789abcdef',now()+interval '1 hour')", [user]);
    for (const role of ['anon', 'authenticated']) {
      await db.exec(`SET ROLE ${role}`);
      await assert.rejects(db.query('SELECT * FROM public.profiles'), /permission denied/);
      await assert.rejects(db.query('SELECT public.mark_email_verified($1)', [user]), /permission denied/);
      await assert.rejects(db.query('SELECT public.consume_email_verification($1,$2)', [user, '0123456789abcdef']), /permission denied/);
      await assert.rejects(db.query('SELECT public.update_order_payment_atomic($1,$2,$3)', [user, 'paid', 'succeeded']), /permission denied/);
      await db.exec('RESET ROLE');
    }
    await db.exec('SET ROLE service_role');
    assert.equal(await scalar('SELECT public.mark_email_verified($1) AS value', [user]), false);
    assert.equal(await scalar('SELECT public.consume_email_verification($1,$2) AS value', [user, 'incorrect-token-value']), false);
    assert.equal(await scalar('SELECT public.consume_email_verification($1,$2) AS value', [user, '0123456789abcdef']), true);
    assert.equal(await scalar('SELECT public.consume_email_verification($1,$2) AS value', [user, '0123456789abcdef']), false);
    await db.query("UPDATE public.profiles SET email_verification_token='expired0123456789', email_verification_expires_at=now()-interval '1 hour' WHERE user_id=$1", [user]);
    assert.equal(await scalar('SELECT public.consume_email_verification($1,$2) AS value', [user, 'expired0123456789']), false);
    await db.exec('RESET ROLE');
    await db.query('UPDATE auth.users SET email_confirmed_at=now() WHERE id=$1', [user]);
    await db.exec('SET ROLE service_role');
    assert.equal(await scalar('SELECT public.mark_email_verified($1) AS value', [user]), true);
    await db.query("INSERT INTO public.businesses(id,business_id,business_name,owner_id) VALUES($1,'test','Test',$2)", [business,user]);
    await db.query("INSERT INTO public.orders(id,business_id,order_number,total,currency) VALUES($1,$2,'test',100,'ILS')", [order,business]);
    await db.query(`INSERT INTO public.payments(business_id,order_id,amount,currency,metadata) VALUES($1,$2,100,'ILS','{"provider":"stripe","provider_session_id":"cs_test"}')`, [business,order]);
    const transition = (amount=100,currency='ILS',session='cs_test',paid=true) => scalar('SELECT public.update_order_payment_atomic($1,$2,$3,$4,$5,$6,$7,$8,$9) AS value', [order,paid?'paid':'pending',paid?'succeeded':'failed',{},paid,amount,currency,session,'stripe']);
    assert.equal(await transition(99), false);
    assert.equal(await transition(100,'USD'), false);
    assert.equal(await transition(100,'ILS','cs_other'), false);
    assert.equal(await scalar('SELECT status AS value FROM public.orders WHERE id=$1',[order]), 'pending');
    assert.equal(await transition(), true);
    assert.equal(await scalar('SELECT status AS value FROM public.orders WHERE id=$1',[order]), 'paid');
    assert.equal(await transition(100,'ILS','cs_test',false), true);
    assert.equal(await scalar('SELECT status AS value FROM public.orders WHERE id=$1',[order]), 'paid');
    assert.equal(await scalar('SELECT status AS value FROM public.payments WHERE order_id=$1',[order]), 'succeeded');
    await db.query("UPDATE public.orders SET status='refunded' WHERE id=$1",[order]);
    assert.equal(await transition(), true);
    assert.equal(await scalar('SELECT status AS value FROM public.orders WHERE id=$1',[order]), 'refunded');
    await db.exec('RESET ROLE');
    console.log(`PASS: all ${files.length} SQL files execute; ${tables.length} tables enforce role isolation; email tokens and payment transitions validated in PostgreSQL`);
  } finally { await db.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
