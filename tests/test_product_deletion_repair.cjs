const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict'), crypto = require('node:crypto');
const modulePath = process.env.PGLITE_MODULE || '@electric-sql/pglite';
const { PGlite } = require(modulePath), dist = path.dirname(require.resolve(modulePath));
const { pgcrypto } = require(path.join(dist, 'contrib/pgcrypto.cjs'));
const { uuid_ossp } = require(path.join(dist, 'contrib/uuid_ossp.cjs'));
(async () => {
 const db = new PGlite({ extensions: { pgcrypto, uuid_ossp } }); let checks = 0;
 const check = (a,b) => { assert.deepEqual(a,b); checks++; };
 const value = async (sql,args=[]) => (await db.query(sql,args)).rows[0].value;
 const owner='00000000-0000-4000-8000-000000000001', other='00000000-0000-4000-8000-000000000002';
 const bid='00000000-0000-4000-8000-000000000003', foreign='00000000-0000-4000-8000-000000000004';
 try {
  await db.exec(`CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;
   CREATE SCHEMA auth; CREATE TABLE auth.users(id uuid PRIMARY KEY);
   CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql AS $$ SELECT NULL::uuid $$;
   GRANT USAGE ON SCHEMA public,auth TO anon,authenticated,service_role;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon,authenticated;`);
  const root=path.join(__dirname,'../database');
  await db.exec(fs.readFileSync(path.join(root,'full_schema_bootstrap.sql'),'utf8'));
  check(await value("SELECT to_regprocedure('public.delete_products_bulk(uuid,uuid,uuid[],boolean,integer)') IS NULL value"),true);
  const repair=fs.readFileSync(path.join(root,'repairs/product_deletion.sql'),'utf8');
  await db.exec(repair);
  for(const id of [owner,other]) await db.query('INSERT INTO auth.users(id) VALUES($1)',[id]);
  for(const [id,uid] of [[bid,owner],[foreign,other]]) await db.query('INSERT INTO businesses(id,owner_id,business_id,business_name) VALUES($1::uuid,$2::uuid,$1::text,$1::text)',[id,uid]);
  await db.query("INSERT INTO products(business_id,item_key,name,price) SELECT $1,'SKU-'||i,'Product',10 FROM generate_series(1,1500) i",[bid]);
  await db.query("INSERT INTO products(business_id,item_key,name,price) VALUES($1,'OTHER','Other',10)",[foreign]);
  const job=await value('SELECT start_product_delete_job($1,$2,1500) value',[owner,bid]);
  await db.exec(repair);
  check(Number(await value('SELECT count(*) value FROM products')),1501);
  check(Number(await value('SELECT count(*) value FROM product_delete_job_items')),1500);
  check((await value('SELECT start_product_delete_job($1,$2,1500) value',[owner,bid])).job_id,job.job_id);
  for(let i=0;i<3;i++) check(await value('SELECT process_product_delete_job() value'),true);
  check(await value('SELECT status value FROM product_delete_jobs WHERE id=$1',[job.job_id]),'completed');
  check(Number(await value('SELECT count(*) value FROM products WHERE business_id=$1',[foreign])),1);
  const sql=fs.readFileSync(path.join(root,'migrations/20261004_product_delete_jobs.sql'),'utf8').replace(/\r\n/g,'\n');
  const checksum=crypto.createHash('sha256').update(sql).digest('hex');
  check(await value("SELECT checksum value FROM schema_migrations WHERE name='20261004_product_delete_jobs.sql'"),checksum);
  check(Number(await value("SELECT count(*) value FROM schema_migrations WHERE name='20261004_notifications_and_bulk_products.sql'")),0);
  for(const role of ['anon','authenticated']) {
   check(await value("SELECT has_function_privilege($1,'public.delete_products_bulk(uuid,uuid,uuid[],boolean,integer)','EXECUTE') value",[role]),false);
   check(await value("SELECT has_function_privilege($1,'public.process_product_delete_job()','EXECUTE') value",[role]),false);
   check(await value("SELECT has_table_privilege($1,'public.product_delete_jobs','SELECT') value",[role]),false);
  }
  check(await value("SELECT has_function_privilege('service_role','public.process_product_delete_job()','EXECUTE') value"),true);
  await db.query("UPDATE schema_migrations SET checksum='wrong' WHERE name='20261004_product_delete_jobs.sql'");
  await assert.rejects(db.exec(repair),/checksum mismatch/);checks++;
  await db.exec('ROLLBACK');
  console.log(`PASS: ${checks} standalone product deletion repair checks, including 1500 products and safe reruns`);
 } finally { await db.close(); }
})().catch(error => { console.error(error); process.exitCode=1; });
