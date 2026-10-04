const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const modulePath=process.env.PGLITE_MODULE||'@electric-sql/pglite';
const {PGlite}=require(modulePath),dist=path.dirname(require.resolve(modulePath));
const {pgcrypto}=require(path.join(dist,'contrib/pgcrypto.cjs')),{uuid_ossp}=require(path.join(dist,'contrib/uuid_ossp.cjs'));
(async()=>{
 const db=new PGlite({extensions:{pgcrypto,uuid_ossp}});let checks=0;
 const equal=(a,b)=>{assert.deepEqual(a,b);checks++;};
 const value=async(sql,params=[])=> (await db.query(sql,params)).rows[0].value;
 const uid='00000000-0000-4000-8000-000000000001',bid='00000000-0000-4000-8000-000000000002';
 try{
  await db.exec(`CREATE ROLE anon;CREATE ROLE authenticated;CREATE ROLE service_role BYPASSRLS;
   CREATE SCHEMA auth;CREATE TABLE auth.users(id uuid PRIMARY KEY,email_confirmed_at timestamptz,encrypted_password text);
   CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql AS $$ SELECT nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
   GRANT USAGE ON SCHEMA public,auth TO anon,authenticated,service_role;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon,authenticated;`);
  const root=path.join(__dirname,'../database');
  for(const file of ['full_schema_bootstrap.sql',...fs.readdirSync(path.join(root,'migrations')).filter(f=>f.endsWith('.sql')).sort().map(f=>'migrations/'+f)])await db.exec(fs.readFileSync(path.join(root,file),'utf8'));
  await db.query('INSERT INTO auth.users(id) VALUES($1)',[uid]);
  await db.query("INSERT INTO businesses(id,owner_id,business_id,business_name) VALUES($1,$2,'test','Store')",[bid,uid]);
  const c=(await db.query("INSERT INTO whatsapp_connections(business_id,owner_id,phone_number_id,access_token_encrypted,verify_token_encrypted,test_recipients,verified_at) VALUES($1,$2,'123456789','ciphertext','ciphertext',ARRAY['972501234567'],now()) RETURNING *",[bid,uid])).rows[0];
  async function insert(id,sender='972501234567'){return (await db.query("INSERT INTO whatsapp_inbox(connection_id,revision,meta_message_id,sender,message_type,body,message_timestamp) VALUES($1,$2,$3,$4,'text','תיק',now()) ON CONFLICT(connection_id,meta_message_id) DO NOTHING RETURNING id",[c.id,c.revision,id,sender])).rows[0]?.id;}
  const first=await insert('in-1');await insert('in-1');const second=await insert('in-2');const other=await insert('in-other','972502222222');
  equal(Number(await value('SELECT count(*) value FROM whatsapp_inbox')),3);
  const job=await value('SELECT claim_whatsapp_message() value');equal(job.id,first);equal(job.attempts,1);
  const parallel=await value('SELECT claim_whatsapp_message() value');equal(parallel.id,other);
  equal(await value('SELECT claim_whatsapp_message() value'),null); // same-sender ordering
  equal(await value('SELECT begin_whatsapp_send($1,$2) value',[first,c.revision]),false); // stale lease token
  equal(await value('SELECT begin_whatsapp_send($1,$2) value',[first,job.lease_token]),true);
  equal(await value("SELECT finish_whatsapp_message($1,$2,'pending') value",[first,job.lease_token]),false); // cannot resend
  await db.query("SELECT whatsapp_delivery_status($1,'out-1','read')",[c.id]); // receipt before send response
  equal(await value("SELECT finish_whatsapp_message($1,$2,'accepted','out-1') value",[first,job.lease_token]),true);
  equal(await value('SELECT status value FROM whatsapp_inbox WHERE id=$1',[first]),'read');
  await db.query("SELECT whatsapp_delivery_status($1,'out-1','sent')",[c.id]);equal(await value('SELECT status value FROM whatsapp_inbox WHERE id=$1',[first]),'read');
  await db.query("SELECT whatsapp_delivery_status($1,'out-1','failed','meta_190')",[c.id]);equal(await value('SELECT status value FROM whatsapp_inbox WHERE id=$1',[first]),'read');
  const j2=await value('SELECT claim_whatsapp_message() value');equal(j2.id,second);
  await db.query("UPDATE whatsapp_inbox SET lease_until=now()-interval '1 second' WHERE id=$1",[second]);
  const recovered=await value('SELECT claim_whatsapp_message() value');equal(recovered.id,second);equal(recovered.attempts,2);assert.notEqual(recovered.lease_token,j2.lease_token);checks++;
  equal(await value('SELECT begin_whatsapp_send($1,$2) value',[second,j2.lease_token]),false);
  equal(await value('SELECT begin_whatsapp_send($1,$2) value',[second,recovered.lease_token]),true);
  await db.query("UPDATE whatsapp_inbox SET lease_until=now()-interval '1 second' WHERE id=$1",[second]);
  await db.query('SELECT claim_whatsapp_message()');equal(await value('SELECT status value FROM whatsapp_inbox WHERE id=$1',[second]),'unknown');
  equal(await value("SELECT finish_whatsapp_message($1,$2,'pending') value",[second,recovered.lease_token]),false);
  await db.query("UPDATE whatsapp_connections SET revision=gen_random_uuid() WHERE id=$1",[c.id]);
  const rotated=await insert('in-rotated');const rotatedJob=await value('SELECT claim_whatsapp_message() value');equal(rotatedJob.id,rotated);
  equal(await value('SELECT begin_whatsapp_send($1,$2) value',[rotated,rotatedJob.lease_token]),false);
  for(const role of ['anon','authenticated']){
   await db.exec('SET ROLE '+role);
   for(const table of ['whatsapp_connections','whatsapp_inbox','whatsapp_delivery_receipts']){await assert.rejects(db.query('SELECT * FROM '+table),/permission denied/);checks++;}
   await assert.rejects(db.query('SELECT claim_whatsapp_message()'),/permission denied/);checks++;
   await db.exec('RESET ROLE');
  }
  await db.query('DELETE FROM whatsapp_connections WHERE id=$1',[c.id]);
  equal(Number(await value('SELECT count(*) value FROM whatsapp_inbox')),0);equal(Number(await value('SELECT count(*) value FROM whatsapp_delivery_receipts')),0);
  console.log(`PASS: ${checks} WhatsApp SQL checks: durable deduplication, ordered claims, leases, send uncertainty, early/out-of-order receipts, rotation, isolation and disconnect`);
 }finally{await db.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
