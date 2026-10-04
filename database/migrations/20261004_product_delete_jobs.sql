-- Snapshot the confirmed selection once; process bounded transactions thereafter.
CREATE TABLE public.product_delete_jobs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
 business_id uuid NOT NULL REFERENCES public.businesses(id) ON DELETE CASCADE,
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','completed','failed')),
 total integer NOT NULL, processed integer NOT NULL DEFAULT 0, deleted integer NOT NULL DEFAULT 0,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), last_error text
);
CREATE UNIQUE INDEX product_delete_jobs_active_idx ON public.product_delete_jobs(business_id) WHERE status='pending';
CREATE TABLE public.product_delete_job_items (
 job_id uuid NOT NULL REFERENCES public.product_delete_jobs(id) ON DELETE CASCADE,
 product_id uuid NOT NULL, PRIMARY KEY(job_id,product_id)
);
ALTER TABLE public.product_delete_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_delete_job_items ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.product_delete_jobs,public.product_delete_job_items FROM anon,authenticated;
GRANT ALL ON public.product_delete_jobs,public.product_delete_job_items TO service_role;

CREATE FUNCTION public.start_product_delete_job(p_user_id uuid,p_business_id uuid,p_expected_count integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE job_uuid uuid; actual_count integer; current_job product_delete_jobs%ROWTYPE;
BEGIN
 PERFORM 1 FROM businesses WHERE id=p_business_id AND owner_id=p_user_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Business not found'; END IF;
 SELECT * INTO current_job FROM product_delete_jobs WHERE business_id=p_business_id AND status='pending';
 IF FOUND THEN RETURN jsonb_build_object('job_id',current_job.id,'status',current_job.status,'total',current_job.total,'deleted',current_job.deleted,'processed',current_job.processed); END IF;
 IF p_expected_count<=0 THEN RAISE EXCEPTION 'Invalid selection'; END IF;
 INSERT INTO product_delete_jobs(user_id,business_id,total) VALUES(p_user_id,p_business_id,p_expected_count) RETURNING id INTO job_uuid;
 INSERT INTO product_delete_job_items(job_id,product_id) SELECT job_uuid,id FROM products WHERE business_id=p_business_id;
 GET DIAGNOSTICS actual_count=ROW_COUNT;
 IF actual_count<>p_expected_count THEN RAISE EXCEPTION 'Selection changed'; END IF;
 RETURN jsonb_build_object('job_id',job_uuid,'status','pending','total',actual_count,'deleted',0,'processed',0);
END $$;

CREATE FUNCTION public.process_product_delete_job() RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE job product_delete_jobs%ROWTYPE; ids uuid[]; removed integer; handled integer;
BEGIN
 SELECT * INTO job FROM product_delete_jobs WHERE status='pending' ORDER BY updated_at LIMIT 1 FOR UPDATE SKIP LOCKED;
 IF NOT FOUND THEN RETURN false; END IF;
 BEGIN
  IF NOT EXISTS(SELECT 1 FROM businesses WHERE id=job.business_id AND owner_id=job.user_id) THEN RAISE EXCEPTION 'Owner changed'; END IF;
  SELECT array_agg(product_id) INTO ids FROM (SELECT product_id FROM product_delete_job_items WHERE job_id=job.id ORDER BY product_id LIMIT 500) batch;
  handled:=coalesce(cardinality(ids),0);
  DELETE FROM products WHERE business_id=job.business_id AND id=ANY(ids);
  GET DIAGNOSTICS removed=ROW_COUNT;
  DELETE FROM product_delete_job_items WHERE job_id=job.id AND product_id=ANY(ids);
  UPDATE product_delete_jobs SET processed=processed+handled,deleted=deleted+removed,updated_at=now(),
   status=CASE WHEN processed+handled>=total THEN 'completed' ELSE 'pending' END WHERE id=job.id;
 EXCEPTION WHEN OTHERS THEN
  -- The subtransaction rolls back this batch; earlier batches remain reported.
  UPDATE product_delete_jobs SET status='failed',last_error=SQLSTATE,updated_at=now() WHERE id=job.id;
 END;
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION public.start_product_delete_job(uuid,uuid,integer),public.process_product_delete_job() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.start_product_delete_job(uuid,uuid,integer),public.process_product_delete_job() TO service_role;
NOTIFY pgrst,'reload schema';
