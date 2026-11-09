-- Additive stock-movement ledger and cutover of current balances.
-- Apply once with the application stopped or stock writers drained.
BEGIN;

LOCK TABLE public.spare_parts IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE public.inventory_movements IN ACCESS EXCLUSIVE MODE;

ALTER TABLE public.inventory_movements
    ADD COLUMN actor_kind varchar(10) NOT NULL DEFAULT 'USER',
    ADD COLUMN reason varchar(500),
    ADD COLUMN idempotency_key uuid,
    ADD COLUMN request_hash char(64);
ALTER TABLE public.inventory_movements ALTER COLUMN actor_user_id DROP NOT NULL;

ALTER TABLE public.inventory_movements
    DROP CONSTRAINT chk_inventory_movements_nonzero_delta,
    DROP CONSTRAINT chk_inventory_movements_origin_xor,
    DROP CONSTRAINT chk_inventory_movements_type_origin,
    DROP CONSTRAINT chk_inventory_movements_stock_after;
ALTER TABLE public.inventory_movements ALTER COLUMN movement_type TYPE varchar(30);

ALTER TABLE public.inventory_movements
    ADD CONSTRAINT chk_inventory_movements_actor_kind
        CHECK (actor_kind IN ('USER','SYSTEM')),
    ADD CONSTRAINT chk_inventory_movements_actor_kind_user
        CHECK ((actor_kind = 'USER' AND actor_user_id IS NOT NULL)
            OR (actor_kind = 'SYSTEM' AND actor_user_id IS NULL AND movement_type = 'OPENING_BALANCE')),
    ADD CONSTRAINT chk_inventory_movements_reason
        CHECK ((movement_type IN ('PURCHASE_RECEIPT','SALE') AND (reason IS NULL OR length(btrim(reason)) > 0))
            OR (movement_type IN ('ADJUSTMENT_IN','ADJUSTMENT_OUT') AND length(btrim(reason)) BETWEEN 1 AND 500)
            OR (movement_type = 'OPENING_BALANCE' AND length(btrim(reason)) BETWEEN 1 AND 500)),
    ADD CONSTRAINT chk_inventory_movements_idempotency
        CHECK ((movement_type IN ('ADJUSTMENT_IN','ADJUSTMENT_OUT') AND idempotency_key IS NOT NULL AND request_hash IS NOT NULL)
            OR (movement_type = 'OPENING_BALANCE' AND actor_kind = 'USER' AND idempotency_key IS NOT NULL AND request_hash IS NOT NULL)
            OR (movement_type = 'OPENING_BALANCE' AND actor_kind = 'SYSTEM' AND idempotency_key IS NULL AND request_hash IS NULL)
            OR (movement_type IN ('PURCHASE_RECEIPT','SALE') AND idempotency_key IS NULL AND request_hash IS NULL)),
    ADD CONSTRAINT chk_inventory_movements_origin_xor
        CHECK (NOT (purchase_receipt_item_id IS NOT NULL AND sales_order_item_id IS NOT NULL)),
    ADD CONSTRAINT chk_inventory_movements_stock_after
        CHECK (stock_after = stock_before + quantity_delta AND stock_after >= 0),
    ADD CONSTRAINT chk_inventory_movements_type_origin
        CHECK (
            (movement_type = 'PURCHASE_RECEIPT' AND purchase_receipt_item_id IS NOT NULL AND sales_order_item_id IS NULL AND quantity_delta > 0 AND actor_kind = 'USER') OR
            (movement_type = 'SALE' AND sales_order_item_id IS NOT NULL AND purchase_receipt_item_id IS NULL AND quantity_delta < 0 AND actor_kind = 'USER') OR
            (movement_type = 'ADJUSTMENT_IN' AND purchase_receipt_item_id IS NULL AND sales_order_item_id IS NULL AND quantity_delta > 0 AND actor_kind = 'USER') OR
            (movement_type = 'ADJUSTMENT_OUT' AND purchase_receipt_item_id IS NULL AND sales_order_item_id IS NULL AND quantity_delta < 0 AND actor_kind = 'USER') OR
            (movement_type = 'OPENING_BALANCE' AND purchase_receipt_item_id IS NULL AND sales_order_item_id IS NULL AND actor_kind = 'USER' AND quantity_delta > 0) OR
            (movement_type = 'OPENING_BALANCE' AND purchase_receipt_item_id IS NULL AND sales_order_item_id IS NULL AND actor_kind = 'SYSTEM' AND quantity_delta >= 0 AND stock_before = 0)
        );

CREATE UNIQUE INDEX ux_inventory_movements_actor_idempotency
    ON public.inventory_movements(actor_user_id,idempotency_key)
    WHERE idempotency_key IS NOT NULL AND actor_kind='USER';
CREATE UNIQUE INDEX ux_inventory_movements_system_opening
    ON public.inventory_movements(spare_part_id)
    WHERE movement_type='OPENING_BALANCE' AND actor_kind='SYSTEM' AND spare_part_id IS NOT NULL;

CREATE OR REPLACE FUNCTION public.inventory_movements_reject_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Inventory movements are immutable';
END;
$$;
DROP TRIGGER IF EXISTS trg_inventory_movements_immutable ON public.inventory_movements;
CREATE TRIGGER trg_inventory_movements_immutable
    BEFORE UPDATE OR DELETE ON public.inventory_movements
    FOR EACH ROW EXECUTE FUNCTION public.inventory_movements_reject_mutation();

-- Preserve every prior movement as legacy history; establish current balance as one SYSTEM event per item.
INSERT INTO public.inventory_movements
    (spare_part_id,movement_type,code_snapshot,name_snapshot,quantity_delta,
     stock_before,stock_after,actor_user_id,actor_kind,reason,created_at)
SELECT id,'OPENING_BALANCE',code,name,current_stock,0,current_stock,NULL,'SYSTEM',
       'Saldo de corte de la migración de trazabilidad',CURRENT_TIMESTAMP
FROM public.spare_parts
ORDER BY id
ON CONFLICT DO NOTHING;

COMMIT;
