-- Esquema completo vacío para instalación en una base nueva.
-- Fuente: pg_dump --schema-only de multiagentedb, 2026-11-04.
-- No crea filas de usuarios, inventario, categorías ni registros de negocio.
-- Ejecutar conectado a la base destino con un rol que pueda crear objetos en public.
-- No aplicar sobre una base con datos que deban conservarse.
BEGIN;
CREATE SCHEMA IF NOT EXISTS public AUTHORIZATION CURRENT_USER;

--
-- PostgreSQL database dump
--

-- Dumped from database version 17.4
-- Dumped by pg_dump version 17.4

-- Started on 2026-11-04 00:18:17

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- TOC entry 921 (class 1247 OID 19728)
-- Name: diagnosis_type_enum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.diagnosis_type_enum AS ENUM (
    'HARDWARE',
    'SOFTWARE',
    'HYBRID',
    'NONE'
);



--
-- TOC entry 942 (class 1247 OID 19812)
-- Name: logistics_mode_enum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.logistics_mode_enum AS ENUM (
    'PHYSICAL_STORE',
    'COURIER_SHIPMENT'
);



--
-- TOC entry 945 (class 1247 OID 19818)
-- Name: logistics_status_enum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.logistics_status_enum AS ENUM (
    'PENDING_RECEIPT',
    'RECEIVED_AT_WORKSHOP',
    'READY_FOR_DISPATCH',
    'IN_TRANSIT',
    'DELIVERED',
    'FAILED_DELIVERY'
);



--
-- TOC entry 954 (class 1247 OID 19854)
-- Name: notification_type_enum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.notification_type_enum AS ENUM (
    'QUOTE_CONFIRMATION',
    'PAYMENT_NOTICE',
    'LOGISTICS_UPDATE',
    'WARRANTY_UPDATE',
    'STATUS_CHANGE'
);



--
-- TOC entry 936 (class 1247 OID 19790)
-- Name: payment_method_enum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.payment_method_enum AS ENUM (
    'CREDIT_CARD',
    'DEBIT_CARD',
    'BANK_TRANSFER',
    'CASH',
    'PAYMENT_GATEWAY'
);



--
-- TOC entry 933 (class 1247 OID 19778)
-- Name: payment_status_enum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.payment_status_enum AS ENUM (
    'PENDING',
    'COMPLETED',
    'FAILED',
    'REFUNDED',
    'PARTIALLY_REFUNDED'
);



--
-- TOC entry 930 (class 1247 OID 19768)
-- Name: quote_status_enum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.quote_status_enum AS ENUM (
    'PENDING',
    'ACCEPTED',
    'REJECTED',
    'EXPIRED',
    'CANCELLED'
);



--
-- TOC entry 927 (class 1247 OID 19760)
-- Name: quote_type_enum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.quote_type_enum AS ENUM (
    'REPAIR',
    'DIRECT_SALE',
    'PC_BUILD'
);



--
-- TOC entry 939 (class 1247 OID 19802)
-- Name: refund_status_enum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.refund_status_enum AS ENUM (
    'REQUESTED',
    'APPROVED',
    'PROCESSED',
    'REJECTED'
);



--
-- TOC entry 918 (class 1247 OID 19716)
-- Name: request_type_enum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.request_type_enum AS ENUM (
    'REPAIR',
    'SALE',
    'PC_BUILD',
    'SUPPORT',
    'WARRANTY_CLAIM'
);



--
-- TOC entry 924 (class 1247 OID 19738)
-- Name: ticket_status_enum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.ticket_status_enum AS ENUM (
    'NEW',
    'IN_DIAGNOSIS',
    'QUOTED',
    'PAYMENT_PENDING',
    'PAID',
    'IN_REPAIR',
    'READY_FOR_DELIVERY',
    'DELIVERED',
    'CANCELLED',
    'WARRANTY_IN_REVIEW'
);



--
-- TOC entry 915 (class 1247 OID 19709)
-- Name: user_role_enum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.user_role_enum AS ENUM (
    'CUSTOMER',
    'TECHNICIAN',
    'ADMIN'
);



--
-- TOC entry 951 (class 1247 OID 19842)
-- Name: warranty_claim_status_enum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.warranty_claim_status_enum AS ENUM (
    'IN_REVIEW',
    'APPROVED_REPAIR',
    'APPROVED_REPLACEMENT',
    'APPROVED_REFUND',
    'REJECTED'
);



--
-- TOC entry 948 (class 1247 OID 19832)
-- Name: warranty_status_enum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.warranty_status_enum AS ENUM (
    'ACTIVE',
    'EXPIRED',
    'VOIDED',
    'CLAIMED'
);



--
-- TOC entry 297 (class 1255 OID 20303)
-- Name: accounting_check_entry_balance(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.accounting_check_entry_balance() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    target_id BIGINT;
    entry_row accounting_entries%ROWTYPE;
    line_count BIGINT;
    debit_sum NUMERIC(14,2);
    credit_sum NUMERIC(14,2);
BEGIN
    IF TG_TABLE_NAME = 'accounting_entry_lines' THEN
        target_id := COALESCE(NEW.entry_id, OLD.entry_id);
    ELSE
        target_id := COALESCE(NEW.id, OLD.id);
    END IF;
    SELECT * INTO entry_row FROM accounting_entries WHERE id = target_id;
    IF NOT FOUND THEN
        RETURN NULL;
    END IF;
    SELECT count(*), COALESCE(sum(debit), 0), COALESCE(sum(credit), 0)
      INTO line_count, debit_sum, credit_sum
      FROM accounting_entry_lines WHERE entry_id = target_id;
    IF line_count < 2 OR line_count > 100 OR
       debit_sum <= 0 OR debit_sum <> credit_sum OR
       debit_sum <> entry_row.debit_total OR credit_sum <> entry_row.credit_total THEN
        RAISE EXCEPTION 'Accounting entry lines do not balance' USING ERRCODE = '23514';
    END IF;
    IF entry_row.status = 'REVERSED' AND NOT EXISTS (
        SELECT 1 FROM accounting_entries reversal WHERE reversal.reversal_of_entry_id = target_id
    ) THEN
        RAISE EXCEPTION 'Reversed entry requires a reversal record' USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END;
$$;



--
-- TOC entry 285 (class 1255 OID 20302)
-- Name: accounting_guard_entry_update(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.accounting_guard_entry_update() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Accounting entries cannot be deleted' USING ERRCODE = '55000';
    END IF;
    IF ROW(NEW.entry_number, NEW.operation_date, NEW.concept, NEW.detail, NEW.category_id,
           NEW.currency, NEW.debit_total, NEW.credit_total, NEW.responsible_user_id,
           NEW.idempotency_key, NEW.request_hash, NEW.reversal_of_entry_id,
           NEW.reversal_reason, NEW.created_at)
       IS DISTINCT FROM
       ROW(OLD.entry_number, OLD.operation_date, OLD.concept, OLD.detail, OLD.category_id,
           OLD.currency, OLD.debit_total, OLD.credit_total, OLD.responsible_user_id,
           OLD.idempotency_key, OLD.request_hash, OLD.reversal_of_entry_id,
           OLD.reversal_reason, OLD.created_at) THEN
        RAISE EXCEPTION 'Accounting entry fields are immutable' USING ERRCODE = '55000';
    END IF;
    IF OLD.status <> 'CONFIRMED' OR NEW.status <> 'REVERSED' OR OLD.reversed_at IS NOT NULL OR
       NEW.reversed_at IS NULL OR NEW.updated_at IS NULL OR NEW.updated_at < OLD.updated_at THEN
        RAISE EXCEPTION 'Invalid accounting status transition' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;



--
-- TOC entry 284 (class 1255 OID 20301)
-- Name: accounting_reject_mutation(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.accounting_reject_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    RAISE EXCEPTION 'Accounting history is immutable' USING ERRCODE = '55000';
END;
$$;



--
-- TOC entry 283 (class 1255 OID 20173)
-- Name: update_updated_at_column(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;



SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 253 (class 1259 OID 20272)
-- Name: accounting_audit_events; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.accounting_audit_events (
    id bigint NOT NULL,
    entry_id bigint NOT NULL,
    actor_user_id bigint NOT NULL,
    event_type character varying(24) NOT NULL,
    related_entry_id bigint,
    reason text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT accounting_audit_event_shape CHECK (((((event_type)::text = 'ENTRY_CREATED'::text) AND (related_entry_id IS NULL) AND (reason IS NULL)) OR (((event_type)::text = ANY ((ARRAY['ENTRY_REVERSED'::character varying, 'REVERSAL_CREATED'::character varying])::text[])) AND (related_entry_id IS NOT NULL) AND (reason IS NOT NULL)))),
    CONSTRAINT accounting_audit_events_event_type_check CHECK (((event_type)::text = ANY ((ARRAY['ENTRY_CREATED'::character varying, 'ENTRY_REVERSED'::character varying, 'REVERSAL_CREATED'::character varying])::text[]))),
    CONSTRAINT accounting_audit_events_reason_check CHECK (((reason IS NULL) OR (char_length(reason) <= 2000)))
);



--
-- TOC entry 252 (class 1259 OID 20271)
-- Name: accounting_audit_events_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.accounting_audit_events ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.accounting_audit_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 246 (class 1259 OID 20188)
-- Name: accounting_categories; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.accounting_categories (
    id bigint NOT NULL,
    code character varying(40) NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);



--
-- TOC entry 245 (class 1259 OID 20187)
-- Name: accounting_categories_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.accounting_categories ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.accounting_categories_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 249 (class 1259 OID 20201)
-- Name: accounting_entries; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.accounting_entries (
    id bigint NOT NULL,
    entry_number bigint NOT NULL,
    operation_date date NOT NULL,
    concept character varying(200) NOT NULL,
    detail text NOT NULL,
    category_id bigint NOT NULL,
    currency character(3) DEFAULT 'PEN'::bpchar NOT NULL,
    debit_total numeric(14,2) NOT NULL,
    credit_total numeric(14,2) NOT NULL,
    status character varying(10) DEFAULT 'CONFIRMED'::character varying NOT NULL,
    responsible_user_id bigint NOT NULL,
    idempotency_key uuid,
    request_hash character(64),
    reversal_of_entry_id bigint,
    reversal_reason text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    reversed_at timestamp with time zone,
    CONSTRAINT accounting_entries_concept_check CHECK (((char_length(btrim((concept)::text)) >= 1) AND (char_length(btrim((concept)::text)) <= 200))),
    CONSTRAINT accounting_entries_credit_total_check CHECK ((credit_total > (0)::numeric)),
    CONSTRAINT accounting_entries_currency_check CHECK ((currency = 'PEN'::bpchar)),
    CONSTRAINT accounting_entries_debit_total_check CHECK ((debit_total > (0)::numeric)),
    CONSTRAINT accounting_entries_detail_check CHECK (((char_length(btrim(detail)) >= 1) AND (char_length(btrim(detail)) <= 4000))),
    CONSTRAINT accounting_entries_status_check CHECK (((status)::text = ANY ((ARRAY['CONFIRMED'::character varying, 'REVERSED'::character varying])::text[]))),
    CONSTRAINT accounting_entry_idempotency_pair CHECK ((((idempotency_key IS NULL) AND (request_hash IS NULL)) OR ((idempotency_key IS NOT NULL) AND (request_hash IS NOT NULL) AND (request_hash ~ '^[0-9a-f]{64}$'::text)))),
    CONSTRAINT accounting_entry_not_self_reversal CHECK (((reversal_of_entry_id IS NULL) OR (reversal_of_entry_id <> id))),
    CONSTRAINT accounting_entry_reversal_reason CHECK ((((reversal_of_entry_id IS NULL) AND (reversal_reason IS NULL)) OR ((reversal_of_entry_id IS NOT NULL) AND (reversal_reason IS NOT NULL) AND ((char_length(btrim(reversal_reason)) >= 1) AND (char_length(btrim(reversal_reason)) <= 2000))))),
    CONSTRAINT accounting_entry_reversed_timestamp CHECK (((((status)::text = 'CONFIRMED'::text) AND (reversed_at IS NULL)) OR (((status)::text = 'REVERSED'::text) AND (reversed_at IS NOT NULL))))
);



--
-- TOC entry 248 (class 1259 OID 20200)
-- Name: accounting_entries_entry_number_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.accounting_entries ALTER COLUMN entry_number ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.accounting_entries_entry_number_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 247 (class 1259 OID 20199)
-- Name: accounting_entries_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.accounting_entries ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.accounting_entries_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 251 (class 1259 OID 20247)
-- Name: accounting_entry_lines; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.accounting_entry_lines (
    id bigint NOT NULL,
    entry_id bigint NOT NULL,
    line_number smallint NOT NULL,
    account_code character varying(40) NOT NULL,
    account_name character varying(200) NOT NULL,
    description text,
    debit numeric(14,2) DEFAULT 0 NOT NULL,
    credit numeric(14,2) DEFAULT 0 NOT NULL,
    CONSTRAINT accounting_entry_line_one_side CHECK (((debit > (0)::numeric) <> (credit > (0)::numeric))),
    CONSTRAINT accounting_entry_lines_account_code_check CHECK (((char_length(btrim((account_code)::text)) >= 1) AND (char_length(btrim((account_code)::text)) <= 40))),
    CONSTRAINT accounting_entry_lines_account_name_check CHECK (((char_length(btrim((account_name)::text)) >= 1) AND (char_length(btrim((account_name)::text)) <= 200))),
    CONSTRAINT accounting_entry_lines_credit_check CHECK ((credit >= (0)::numeric)),
    CONSTRAINT accounting_entry_lines_debit_check CHECK ((debit >= (0)::numeric)),
    CONSTRAINT accounting_entry_lines_description_check CHECK (((description IS NULL) OR (char_length(description) <= 1000))),
    CONSTRAINT accounting_entry_lines_line_number_check CHECK (((line_number >= 1) AND (line_number <= 100)))
);



--
-- TOC entry 250 (class 1259 OID 20246)
-- Name: accounting_entry_lines_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.accounting_entry_lines ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.accounting_entry_lines_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 272 (class 1259 OID 20544)
-- Name: customer_audit_events; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.customer_audit_events (
    id bigint NOT NULL,
    customer_id bigint NOT NULL,
    actor_user_id bigint NOT NULL,
    event_type character varying(30) NOT NULL,
    changed_fields jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT customer_audit_events_event_type_check CHECK (((event_type)::text = ANY ((ARRAY['CREATED'::character varying, 'UPDATED'::character varying, 'ACCOUNT_LINKED'::character varying, 'DEACTIVATED'::character varying])::text[])))
);



--
-- TOC entry 271 (class 1259 OID 20543)
-- Name: customer_audit_events_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.customer_audit_events ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.customer_audit_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 270 (class 1259 OID 20514)
-- Name: customers; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.customers (
    id bigint NOT NULL,
    display_name character varying(200) NOT NULL,
    phone character varying(30) NOT NULL,
    email character varying(255),
    origin character varying(10) NOT NULL,
    user_id bigint,
    active boolean DEFAULT true NOT NULL,
    created_by_user_id bigint,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT chk_customers_portal_link CHECK ((((origin)::text <> 'PORTAL'::text) OR (user_id IS NOT NULL))),
    CONSTRAINT customers_display_name_check CHECK (((char_length(btrim((display_name)::text)) >= 2) AND (char_length(btrim((display_name)::text)) <= 200))),
    CONSTRAINT customers_origin_check CHECK (((origin)::text = ANY ((ARRAY['MANUAL'::character varying, 'PORTAL'::character varying])::text[]))),
    CONSTRAINT customers_phone_check CHECK (((char_length(btrim((phone)::text)) >= 7) AND (char_length(btrim((phone)::text)) <= 30)))
);



--
-- TOC entry 269 (class 1259 OID 20513)
-- Name: customers_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.customers ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.customers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 263 (class 1259 OID 20430)
-- Name: inventory_movements; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.inventory_movements (
    id bigint NOT NULL,
    spare_part_id bigint,
    purchase_receipt_item_id bigint,
    movement_type character varying(30) NOT NULL,
    code_snapshot character varying(50) NOT NULL,
    name_snapshot character varying(150) NOT NULL,
    quantity_delta integer NOT NULL,
    stock_before integer NOT NULL,
    stock_after integer NOT NULL,
    actor_user_id bigint,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    sales_order_item_id bigint,
    actor_kind character varying(10) DEFAULT 'USER'::character varying NOT NULL,
    reason character varying(500),
    idempotency_key uuid,
    request_hash character(64),
    CONSTRAINT chk_inventory_movements_actor_kind CHECK (((actor_kind)::text = ANY ((ARRAY['USER'::character varying, 'SYSTEM'::character varying])::text[]))),
    CONSTRAINT chk_inventory_movements_actor_kind_user CHECK ((((actor_kind)::text = 'USER'::text) AND (actor_user_id IS NOT NULL)) OR (((actor_kind)::text = 'SYSTEM'::text) AND (actor_user_id IS NULL) AND ((movement_type)::text = 'OPENING_BALANCE'::text))),
    CONSTRAINT chk_inventory_movements_reason CHECK ((((movement_type)::text = ANY ((ARRAY['PURCHASE_RECEIPT'::character varying, 'SALE'::character varying])::text[])) AND ((reason IS NULL) OR (length(btrim((reason)::text)) > 0))) OR (((movement_type)::text = ANY ((ARRAY['ADJUSTMENT_IN'::character varying, 'ADJUSTMENT_OUT'::character varying, 'OPENING_BALANCE'::character varying])::text[])) AND (length(btrim((reason)::text)) BETWEEN 1 AND 500))),
    CONSTRAINT chk_inventory_movements_idempotency CHECK ((((movement_type)::text = ANY ((ARRAY['ADJUSTMENT_IN'::character varying, 'ADJUSTMENT_OUT'::character varying])::text[])) AND (idempotency_key IS NOT NULL) AND (request_hash IS NOT NULL)) OR (((movement_type)::text = 'OPENING_BALANCE'::text) AND ((actor_kind)::text = 'USER'::text) AND (idempotency_key IS NOT NULL) AND (request_hash IS NOT NULL)) OR (((movement_type)::text = 'OPENING_BALANCE'::text) AND ((actor_kind)::text = 'SYSTEM'::text) AND (idempotency_key IS NULL) AND (request_hash IS NULL)) OR (((movement_type)::text = ANY ((ARRAY['PURCHASE_RECEIPT'::character varying, 'SALE'::character varying])::text[])) AND (idempotency_key IS NULL) AND (request_hash IS NULL))),
    CONSTRAINT chk_inventory_movements_origin_xor CHECK (NOT ((purchase_receipt_item_id IS NOT NULL) AND (sales_order_item_id IS NOT NULL))),
    CONSTRAINT chk_inventory_movements_stock_after CHECK (((stock_after = (stock_before + quantity_delta)) AND (stock_after >= 0))),
    CONSTRAINT chk_inventory_movements_type_origin CHECK ((((movement_type)::text = 'PURCHASE_RECEIPT'::text) AND (purchase_receipt_item_id IS NOT NULL) AND (sales_order_item_id IS NULL) AND (quantity_delta > 0) AND ((actor_kind)::text = 'USER'::text)) OR (((movement_type)::text = 'SALE'::text) AND (sales_order_item_id IS NOT NULL) AND (purchase_receipt_item_id IS NULL) AND (quantity_delta < 0) AND ((actor_kind)::text = 'USER'::text)) OR (((movement_type)::text = 'ADJUSTMENT_IN'::text) AND (purchase_receipt_item_id IS NULL) AND (sales_order_item_id IS NULL) AND (quantity_delta > 0) AND ((actor_kind)::text = 'USER'::text)) OR (((movement_type)::text = 'ADJUSTMENT_OUT'::text) AND (purchase_receipt_item_id IS NULL) AND (sales_order_item_id IS NULL) AND (quantity_delta < 0) AND ((actor_kind)::text = 'USER'::text)) OR (((movement_type)::text = 'OPENING_BALANCE'::text) AND (purchase_receipt_item_id IS NULL) AND (sales_order_item_id IS NULL) AND ((actor_kind)::text = 'USER'::text) AND (quantity_delta > 0)) OR (((movement_type)::text = 'OPENING_BALANCE'::text) AND (purchase_receipt_item_id IS NULL) AND (sales_order_item_id IS NULL) AND ((actor_kind)::text = 'SYSTEM'::text) AND (quantity_delta >= 0) AND (stock_before = 0)))),
    CONSTRAINT inventory_movements_check CHECK ((stock_after = (stock_before + quantity_delta))),
    CONSTRAINT inventory_movements_stock_before_check CHECK ((stock_before >= 0))
);



--
-- TOC entry 262 (class 1259 OID 20429)
-- Name: inventory_movements_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.inventory_movements ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.inventory_movements_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 276 (class 1259 OID 20639)
-- Name: inventory_reservation_items; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.inventory_reservation_items (
    id bigint NOT NULL,
    reservation_id bigint NOT NULL,
    quote_detail_id bigint NOT NULL,
    spare_part_id bigint NOT NULL,
    code_snapshot character varying(50) NOT NULL,
    name_snapshot character varying(150) NOT NULL,
    quantity integer NOT NULL,
    unit_price numeric(10,2) NOT NULL,
    subtotal numeric(12,2) NOT NULL,
    CONSTRAINT inventory_reservation_items_check CHECK ((subtotal = (unit_price * (quantity)::numeric))),
    CONSTRAINT inventory_reservation_items_quantity_check CHECK ((quantity > 0)),
    CONSTRAINT inventory_reservation_items_unit_price_check CHECK ((unit_price > (0)::numeric))
);



--
-- TOC entry 275 (class 1259 OID 20638)
-- Name: inventory_reservation_items_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.inventory_reservation_items ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.inventory_reservation_items_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 274 (class 1259 OID 20606)
-- Name: inventory_reservations; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.inventory_reservations (
    id bigint NOT NULL,
    quote_id bigint NOT NULL,
    customer_id bigint NOT NULL,
    idempotency_key character varying(200) NOT NULL,
    status character varying(12) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    accepted_by_user_id bigint NOT NULL,
    accepted_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    released_by_user_id bigint,
    released_at timestamp with time zone,
    release_reason character varying(30),
    consumed_at timestamp with time zone,
    CONSTRAINT chk_inventory_reservation_terminal CHECK (((((status)::text = 'RESERVED'::text) AND (released_at IS NULL) AND (consumed_at IS NULL)) OR (((status)::text = 'RELEASED'::text) AND (released_at IS NOT NULL) AND (consumed_at IS NULL)) OR (((status)::text = 'CONSUMED'::text) AND (released_at IS NULL) AND (consumed_at IS NOT NULL)))),
    CONSTRAINT inventory_reservations_release_reason_check CHECK (((release_reason IS NULL) OR ((release_reason)::text = ANY ((ARRAY['REJECTED'::character varying, 'CANCELLED'::character varying, 'EXPIRED'::character varying])::text[])))),
    CONSTRAINT inventory_reservations_status_check CHECK (((status)::text = ANY ((ARRAY['RESERVED'::character varying, 'RELEASED'::character varying, 'CONSUMED'::character varying])::text[])))
);



--
-- TOC entry 273 (class 1259 OID 20605)
-- Name: inventory_reservations_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.inventory_reservations ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.inventory_reservations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 240 (class 1259 OID 20075)
-- Name: logistics_records; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.logistics_records (
    id bigint NOT NULL,
    ticket_id bigint,
    mode public.logistics_mode_enum DEFAULT 'PHYSICAL_STORE'::public.logistics_mode_enum NOT NULL,
    status public.logistics_status_enum DEFAULT 'PENDING_RECEIPT'::public.logistics_status_enum NOT NULL,
    courier_company character varying(100),
    tracking_number character varying(100),
    shipping_address text,
    recipient_name character varying(150),
    recipient_phone character varying(20),
    scheduled_date timestamp with time zone,
    received_at timestamp with time zone,
    delivered_at timestamp with time zone,
    observations text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    sales_order_id bigint,
    commercial_customer_id bigint,
    created_by_user_id bigint
);



--
-- TOC entry 239 (class 1259 OID 20074)
-- Name: logistics_records_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.logistics_records ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.logistics_records_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 236 (class 1259 OID 20024)
-- Name: payments; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.payments (
    id bigint NOT NULL,
    ticket_id bigint,
    quote_id bigint,
    customer_id bigint,
    payment_code character varying(50) NOT NULL,
    amount numeric(10,2) NOT NULL,
    status public.payment_status_enum DEFAULT 'PENDING'::public.payment_status_enum NOT NULL,
    payment_method public.payment_method_enum,
    transaction_reference character varying(100),
    notes text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    commercial_customer_id bigint NOT NULL,
    confirmed_by_user_id bigint,
    confirmed_at timestamp with time zone,
    idempotency_key character varying(200),
    CONSTRAINT chk_positive_payment_amount CHECK ((amount > (0)::numeric))
);



--
-- TOC entry 235 (class 1259 OID 20023)
-- Name: payments_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.payments ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.payments_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 228 (class 1259 OID 19938)
-- Name: purchase_order_items; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.purchase_order_items (
    id bigint NOT NULL,
    purchase_order_id bigint NOT NULL,
    spare_part_id bigint,
    custom_item_name character varying(150),
    quantity integer NOT NULL,
    unit_cost numeric(10,2) NOT NULL,
    subtotal numeric(10,2) NOT NULL
);



--
-- TOC entry 227 (class 1259 OID 19937)
-- Name: purchase_order_items_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.purchase_order_items ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.purchase_order_items_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 226 (class 1259 OID 19923)
-- Name: purchase_orders; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.purchase_orders (
    id bigint NOT NULL,
    supplier_id bigint NOT NULL,
    total_amount numeric(10,2) DEFAULT 0.00 NOT NULL,
    status character varying(30) DEFAULT 'PENDING'::character varying NOT NULL,
    estimated_arrival timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);



--
-- TOC entry 225 (class 1259 OID 19922)
-- Name: purchase_orders_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.purchase_orders ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.purchase_orders_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 261 (class 1259 OID 20410)
-- Name: purchase_receipt_items; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.purchase_receipt_items (
    id bigint NOT NULL,
    receipt_id bigint NOT NULL,
    purchase_item_id bigint NOT NULL,
    quantity_received numeric(12,3) NOT NULL,
    CONSTRAINT purchase_receipt_items_quantity_received_check CHECK ((quantity_received > (0)::numeric))
);



--
-- TOC entry 260 (class 1259 OID 20409)
-- Name: purchase_receipt_items_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.purchase_receipt_items ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.purchase_receipt_items_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 259 (class 1259 OID 20387)
-- Name: purchase_receipts; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.purchase_receipts (
    id bigint NOT NULL,
    purchase_id bigint NOT NULL,
    actor_user_id bigint NOT NULL,
    idempotency_key uuid NOT NULL,
    request_hash character(64) NOT NULL,
    received_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    notes text,
    CONSTRAINT purchase_receipts_request_hash_check CHECK ((request_hash ~ '^[0-9a-f]{64}$'::text))
);



--
-- TOC entry 258 (class 1259 OID 20386)
-- Name: purchase_receipts_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.purchase_receipts ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.purchase_receipts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 282 (class 1259 OID 20767)
-- Name: quote_audit_events; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.quote_audit_events (
    id bigint NOT NULL,
    quote_id bigint NOT NULL,
    actor_user_id bigint NOT NULL,
    event_type character varying(30) NOT NULL,
    changed_fields jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT quote_audit_events_event_type_check CHECK (((event_type)::text = ANY ((ARRAY['CREATED'::character varying, 'ACCEPTED'::character varying, 'REJECTED'::character varying, 'CANCELLED'::character varying, 'EXPIRED'::character varying, 'PAYMENT_CONFIRMED'::character varying])::text[])))
);



--
-- TOC entry 281 (class 1259 OID 20766)
-- Name: quote_audit_events_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.quote_audit_events ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.quote_audit_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 234 (class 1259 OID 20005)
-- Name: quote_details; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.quote_details (
    id bigint NOT NULL,
    quote_id bigint NOT NULL,
    spare_part_id bigint,
    custom_item_name character varying(150),
    quantity integer DEFAULT 1 NOT NULL,
    unit_price numeric(10,2) NOT NULL,
    subtotal numeric(10,2) NOT NULL,
    CONSTRAINT chk_positive_quantity CHECK ((quantity > 0)),
    CONSTRAINT chk_positive_subtotal CHECK ((subtotal >= (0)::numeric))
);



--
-- TOC entry 233 (class 1259 OID 20004)
-- Name: quote_details_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.quote_details ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.quote_details_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 232 (class 1259 OID 19981)
-- Name: quotes; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.quotes (
    id bigint NOT NULL,
    ticket_id bigint,
    quote_type public.quote_type_enum DEFAULT 'REPAIR'::public.quote_type_enum NOT NULL,
    tier_name character varying(50) DEFAULT 'STANDARD'::character varying,
    labor_cost numeric(10,2) DEFAULT 0.00 NOT NULL,
    parts_cost numeric(10,2) DEFAULT 0.00 NOT NULL,
    total_amount numeric(10,2) DEFAULT 0.00 NOT NULL,
    status public.quote_status_enum DEFAULT 'PENDING'::public.quote_status_enum NOT NULL,
    observations text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    customer_id bigint NOT NULL,
    origin character varying(10),
    created_by_user_id bigint,
    accepted_by_user_id bigint,
    accepted_at timestamp with time zone,
    expires_at timestamp with time zone,
    customer_name_snapshot character varying(200),
    customer_phone_snapshot character varying(30),
    customer_email_snapshot character varying(255),
    CONSTRAINT chk_positive_labor_cost CHECK ((labor_cost >= (0)::numeric)),
    CONSTRAINT chk_positive_parts_cost CHECK ((parts_cost >= (0)::numeric)),
    CONSTRAINT chk_positive_total_amount CHECK ((total_amount >= (0)::numeric)),
    CONSTRAINT chk_quotes_origin CHECK (((origin IS NULL) OR ((origin)::text = ANY ((ARRAY['MANUAL'::character varying, 'PORTAL'::character varying, 'CHAT'::character varying])::text[])))),
    CONSTRAINT chk_quotes_ticket_kind CHECK ((((quote_type = ANY (ARRAY['DIRECT_SALE'::public.quote_type_enum, 'PC_BUILD'::public.quote_type_enum])) AND (ticket_id IS NULL)) OR ((quote_type = 'REPAIR'::public.quote_type_enum) AND (ticket_id IS NOT NULL))))
);



--
-- TOC entry 231 (class 1259 OID 19980)
-- Name: quotes_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.quotes ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.quotes_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 220 (class 1259 OID 19881)
-- Name: recovery_tokens; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.recovery_tokens (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    token character varying(255) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    used boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);



--
-- TOC entry 219 (class 1259 OID 19880)
-- Name: recovery_tokens_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.recovery_tokens ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.recovery_tokens_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 238 (class 1259 OID 20053)
-- Name: refunds; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.refunds (
    id bigint NOT NULL,
    payment_id bigint NOT NULL,
    ticket_id bigint,
    amount numeric(10,2) NOT NULL,
    reason text NOT NULL,
    status public.refund_status_enum DEFAULT 'REQUESTED'::public.refund_status_enum NOT NULL,
    processed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    requested_by_user_id bigint,
    CONSTRAINT chk_positive_refund_amount CHECK ((amount > (0)::numeric))
);



--
-- TOC entry 237 (class 1259 OID 20052)
-- Name: refunds_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.refunds ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.refunds_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 280 (class 1259 OID 20705)
-- Name: sales_order_items; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.sales_order_items (
    id bigint NOT NULL,
    sales_order_id bigint NOT NULL,
    quote_detail_id bigint NOT NULL,
    spare_part_id bigint,
    code_snapshot character varying(50),
    name_snapshot character varying(150) NOT NULL,
    quantity integer NOT NULL,
    unit_price numeric(10,2) NOT NULL,
    subtotal numeric(12,2) NOT NULL,
    CONSTRAINT sales_order_items_check CHECK ((subtotal = (unit_price * (quantity)::numeric))),
    CONSTRAINT sales_order_items_quantity_check CHECK ((quantity > 0)),
    CONSTRAINT sales_order_items_unit_price_check CHECK ((unit_price > (0)::numeric))
);



--
-- TOC entry 279 (class 1259 OID 20704)
-- Name: sales_order_items_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.sales_order_items ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.sales_order_items_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 278 (class 1259 OID 20666)
-- Name: sales_orders; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.sales_orders (
    id bigint NOT NULL,
    code character varying(50) NOT NULL,
    quote_id bigint NOT NULL,
    payment_id bigint NOT NULL,
    customer_id bigint NOT NULL,
    status character varying(20) NOT NULL,
    total_amount numeric(10,2) NOT NULL,
    customer_name_snapshot character varying(200) NOT NULL,
    customer_phone_snapshot character varying(30) NOT NULL,
    customer_email_snapshot character varying(255),
    created_by_user_id bigint NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT sales_orders_status_check CHECK (((status)::text = ANY ((ARRAY['PAID'::character varying, 'PREPARING'::character varying, 'FULFILLED'::character varying, 'CANCELLED'::character varying])::text[]))),
    CONSTRAINT sales_orders_total_amount_check CHECK ((total_amount > (0)::numeric))
);



--
-- TOC entry 277 (class 1259 OID 20665)
-- Name: sales_orders_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.sales_orders ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.sales_orders_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 268 (class 1259 OID 20504)
-- Name: schema_migrations; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.schema_migrations (
    version character varying(3) NOT NULL,
    filename character varying(200) NOT NULL,
    checksum character(64) NOT NULL,
    verified_by character varying(120) NOT NULL,
    applied_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT schema_migrations_checksum_check CHECK ((checksum ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT schema_migrations_verified_by_check CHECK (((char_length(btrim((verified_by)::text)) >= 1) AND (char_length(btrim((verified_by)::text)) <= 120))),
    CONSTRAINT schema_migrations_version_check CHECK (((version)::text ~ '^[0-9]{3}$'::text))
);



--
-- TOC entry 222 (class 1259 OID 19896)
-- Name: spare_parts; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.spare_parts (
    id bigint NOT NULL,
    code character varying(50) NOT NULL,
    name character varying(150) NOT NULL,
    category character varying(50),
    description text,
    unit_price numeric(10,2) NOT NULL,
    current_stock integer DEFAULT 0 NOT NULL,
    minimum_threshold integer DEFAULT 5 NOT NULL,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_positive_stock CHECK ((current_stock >= 0)),
    CONSTRAINT chk_positive_threshold CHECK ((minimum_threshold >= 0)),
    CONSTRAINT chk_positive_unit_price CHECK ((unit_price >= (0)::numeric))
);



--
-- TOC entry 221 (class 1259 OID 19895)
-- Name: spare_parts_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.spare_parts ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.spare_parts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 265 (class 1259 OID 20459)
-- Name: supplier_purchase_audit_events; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.supplier_purchase_audit_events (
    id bigint NOT NULL,
    purchase_id bigint NOT NULL,
    actor_user_id bigint NOT NULL,
    event_type character varying(30) NOT NULL,
    changed_fields jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT supplier_purchase_audit_events_event_type_check CHECK (((event_type)::text = ANY ((ARRAY['CREATED'::character varying, 'UPDATED'::character varying, 'RECEIPT_CONFIRMED'::character varying, 'PAYMENT_STATUS_CHANGED'::character varying, 'CANCELLED'::character varying])::text[])))
);



--
-- TOC entry 264 (class 1259 OID 20458)
-- Name: supplier_purchase_audit_events_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.supplier_purchase_audit_events ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.supplier_purchase_audit_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 257 (class 1259 OID 20361)
-- Name: supplier_purchase_items; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.supplier_purchase_items (
    id bigint NOT NULL,
    purchase_id bigint NOT NULL,
    spare_part_id bigint,
    code_snapshot character varying(50),
    description_snapshot character varying(300) NOT NULL,
    quantity numeric(12,3) NOT NULL,
    unit_cost numeric(14,2) NOT NULL,
    discount_amount numeric(14,2) DEFAULT 0 NOT NULL,
    tax_amount numeric(14,2) DEFAULT 0 NOT NULL,
    line_total numeric(14,2) NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT supplier_purchase_items_description_snapshot_check CHECK (((char_length(btrim((description_snapshot)::text)) >= 1) AND (char_length(btrim((description_snapshot)::text)) <= 300))),
    CONSTRAINT supplier_purchase_items_discount_amount_check CHECK ((discount_amount >= (0)::numeric)),
    CONSTRAINT supplier_purchase_items_line_total_check CHECK ((line_total >= (0)::numeric)),
    CONSTRAINT supplier_purchase_items_quantity_check CHECK ((quantity > (0)::numeric)),
    CONSTRAINT supplier_purchase_items_tax_amount_check CHECK ((tax_amount >= (0)::numeric)),
    CONSTRAINT supplier_purchase_items_unit_cost_check CHECK ((unit_cost >= (0)::numeric))
);



--
-- TOC entry 256 (class 1259 OID 20360)
-- Name: supplier_purchase_items_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.supplier_purchase_items ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.supplier_purchase_items_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 255 (class 1259 OID 20315)
-- Name: supplier_purchases; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.supplier_purchases (
    id bigint NOT NULL,
    supplier_id bigint NOT NULL,
    purchase_order_id bigint,
    supplier_name_snapshot character varying(200) NOT NULL,
    supplier_tax_id_snapshot character varying(20),
    document_type character varying(30) NOT NULL,
    document_series character varying(30),
    document_number character varying(40) NOT NULL,
    issue_date date NOT NULL,
    due_date date,
    currency character(3) DEFAULT 'PEN'::bpchar NOT NULL,
    subtotal numeric(14,2) NOT NULL,
    tax_total numeric(14,2) DEFAULT 0 NOT NULL,
    discount_total numeric(14,2) DEFAULT 0 NOT NULL,
    other_charges numeric(14,2) DEFAULT 0 NOT NULL,
    total_amount numeric(14,2) NOT NULL,
    payment_method character varying(20) NOT NULL,
    payment_status character varying(10) NOT NULL,
    status character varying(24) DEFAULT 'REGISTERED'::character varying NOT NULL,
    notes text,
    created_by bigint NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT chk_supplier_purchase_due_date CHECK (((due_date IS NULL) OR (due_date >= issue_date))),
    CONSTRAINT supplier_purchases_currency_check CHECK ((currency = 'PEN'::bpchar)),
    CONSTRAINT supplier_purchases_discount_total_check CHECK ((discount_total >= (0)::numeric)),
    CONSTRAINT supplier_purchases_document_number_check CHECK (((char_length(btrim((document_number)::text)) >= 1) AND (char_length(btrim((document_number)::text)) <= 40))),
    CONSTRAINT supplier_purchases_document_type_check CHECK (((char_length(btrim((document_type)::text)) >= 1) AND (char_length(btrim((document_type)::text)) <= 30))),
    CONSTRAINT supplier_purchases_other_charges_check CHECK ((other_charges >= (0)::numeric)),
    CONSTRAINT supplier_purchases_payment_method_check CHECK (((payment_method)::text = ANY ((ARRAY['TRANSFER'::character varying, 'CASH'::character varying, 'CARD'::character varying, 'OTHER'::character varying])::text[]))),
    CONSTRAINT supplier_purchases_payment_status_check CHECK (((payment_status)::text = ANY ((ARRAY['PENDING'::character varying, 'PAID'::character varying])::text[]))),
    CONSTRAINT supplier_purchases_status_check CHECK (((status)::text = ANY ((ARRAY['REGISTERED'::character varying, 'PARTIALLY_RECEIVED'::character varying, 'RECEIVED'::character varying, 'CANCELLED'::character varying])::text[]))),
    CONSTRAINT supplier_purchases_subtotal_check CHECK ((subtotal >= (0)::numeric)),
    CONSTRAINT supplier_purchases_tax_total_check CHECK ((tax_total >= (0)::numeric)),
    CONSTRAINT supplier_purchases_total_amount_check CHECK ((total_amount >= (0)::numeric))
);



--
-- TOC entry 254 (class 1259 OID 20314)
-- Name: supplier_purchases_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.supplier_purchases ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.supplier_purchases_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 224 (class 1259 OID 19914)
-- Name: suppliers; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.suppliers (
    id bigint NOT NULL,
    name character varying(200) NOT NULL,
    contact_email character varying(255),
    phone character varying(30),
    delivery_lead_days integer DEFAULT 3,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    tax_id character varying(20),
    contact_name character varying(200),
    address text
);

CREATE TABLE public.supplier_audit_events (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    supplier_id bigint NOT NULL,
    actor_user_id bigint NOT NULL,
    event_type character varying(20) NOT NULL CHECK (event_type IN ('CREATED', 'UPDATED')),
    changed_fields jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX ix_supplier_audit_events_supplier_created
    ON public.supplier_audit_events (supplier_id, created_at DESC, id DESC);



--
-- TOC entry 223 (class 1259 OID 19913)
-- Name: suppliers_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.suppliers ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.suppliers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 267 (class 1259 OID 20484)
-- Name: ticket_audit_events; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.ticket_audit_events (
    id bigint NOT NULL,
    ticket_id bigint NOT NULL,
    actor_user_id bigint NOT NULL,
    event_type character varying(20) NOT NULL,
    changed_fields jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ticket_audit_events_event_type_check CHECK (((event_type)::text = ANY ((ARRAY['CREATED'::character varying, 'UPDATED'::character varying, 'STATUS_CHANGED'::character varying, 'CANCELLED'::character varying, 'QUOTE_CREATED'::character varying])::text[])))
);



--
-- TOC entry 266 (class 1259 OID 20483)
-- Name: ticket_audit_events_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.ticket_audit_events ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.ticket_audit_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 230 (class 1259 OID 19954)
-- Name: tickets; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.tickets (
    id bigint NOT NULL,
    code character varying(20) NOT NULL,
    customer_id bigint,
    technician_id bigint,
    title character varying(200) NOT NULL,
    failure_description text NOT NULL,
    request_type public.request_type_enum DEFAULT 'REPAIR'::public.request_type_enum NOT NULL,
    diagnosis_type public.diagnosis_type_enum DEFAULT 'NONE'::public.diagnosis_type_enum NOT NULL,
    status public.ticket_status_enum DEFAULT 'NEW'::public.ticket_status_enum NOT NULL,
    hardware_diagnosis text,
    software_diagnosis text,
    estimated_labor_hours numeric(4,1) DEFAULT 0.0,
    is_remote_service boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    origin character varying(10),
    contact_name character varying(200),
    contact_phone character varying(20),
    contact_email character varying(255),
    advance_amount numeric(10,2),
    advance_payment_method character varying(12),
    commercial_customer_id bigint NOT NULL,
    created_by_user_id bigint,
    CONSTRAINT chk_tickets_advance CHECK ((((advance_amount IS NULL) AND (advance_payment_method IS NULL)) OR ((advance_amount > (0)::numeric) AND ((advance_payment_method)::text = ANY ((ARRAY['YAPE_PLIN'::character varying, 'CASH'::character varying, 'CARD'::character varying])::text[]))))),
    CONSTRAINT chk_tickets_origin CHECK (((origin IS NULL) OR ((origin)::text = ANY ((ARRAY['MANUAL'::character varying, 'ONLINE'::character varying])::text[])))),
    CONSTRAINT chk_tickets_origin_customer CHECK (((origin IS NULL) OR (((origin)::text = 'MANUAL'::text) AND (contact_name IS NOT NULL) AND (contact_phone IS NOT NULL)) OR (((origin)::text = 'ONLINE'::text) AND (customer_id IS NOT NULL))))
);



--
-- TOC entry 229 (class 1259 OID 19953)
-- Name: tickets_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.tickets ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.tickets_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 218 (class 1259 OID 19866)
-- Name: users; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.users (
    id bigint NOT NULL,
    email character varying(255) NOT NULL,
    phone character varying(20) NOT NULL,
    password_hash character varying(255) NOT NULL,
    name character varying(100) NOT NULL,
    last_name character varying(100),
    role public.user_role_enum DEFAULT 'CUSTOMER'::public.user_role_enum NOT NULL,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_email_format CHECK (((email)::text ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'::text))
);



--
-- TOC entry 217 (class 1259 OID 19865)
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.users ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.users_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);



--
-- TOC entry 242 (class 1259 OID 20092)
-- Name: warranties; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.warranties (
    id bigint NOT NULL,
    ticket_id bigint,
    quote_id bigint,
    customer_id bigint,
    warranty_code character varying(50) NOT NULL,
    item_or_service_name character varying(200) NOT NULL,
    serial_number character varying(100),
    warranty_months integer DEFAULT 6 NOT NULL,
    start_date date DEFAULT CURRENT_DATE NOT NULL,
    end_date date NOT NULL,
    status public.warranty_status_enum DEFAULT 'ACTIVE'::public.warranty_status_enum NOT NULL,
    terms_and_conditions text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    sales_order_id bigint,
    commercial_customer_id bigint,
    created_by_user_id bigint,
    CONSTRAINT chk_valid_warranty_dates CHECK ((end_date >= start_date))
);



--
-- TOC entry 241 (class 1259 OID 20091)
-- Name: warranties_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.warranties ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.warranties_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 244 (class 1259 OID 20123)
-- Name: warranty_claims; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.warranty_claims (
    id bigint NOT NULL,
    warranty_id bigint NOT NULL,
    ticket_id bigint,
    claim_code character varying(50) NOT NULL,
    reason text NOT NULL,
    status public.warranty_claim_status_enum DEFAULT 'IN_REVIEW'::public.warranty_claim_status_enum NOT NULL,
    resolution_notes text,
    resolved_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);



--
-- TOC entry 243 (class 1259 OID 20122)
-- Name: warranty_claims_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.warranty_claims ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.warranty_claims_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 5153 (class 2606 OID 20282)
-- Name: accounting_audit_events accounting_audit_events_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.accounting_audit_events
    ADD CONSTRAINT accounting_audit_events_pkey PRIMARY KEY (id);


--
-- TOC entry 5133 (class 2606 OID 20198)
-- Name: accounting_categories accounting_categories_code_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.accounting_categories
    ADD CONSTRAINT accounting_categories_code_key UNIQUE (code);


--
-- TOC entry 5135 (class 2606 OID 20196)
-- Name: accounting_categories accounting_categories_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.accounting_categories
    ADD CONSTRAINT accounting_categories_pkey PRIMARY KEY (id);


--
-- TOC entry 5137 (class 2606 OID 20223)
-- Name: accounting_entries accounting_entries_entry_number_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.accounting_entries
    ADD CONSTRAINT accounting_entries_entry_number_key UNIQUE (entry_number);


--
-- TOC entry 5139 (class 2606 OID 20221)
-- Name: accounting_entries accounting_entries_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.accounting_entries
    ADD CONSTRAINT accounting_entries_pkey PRIMARY KEY (id);


--
-- TOC entry 5141 (class 2606 OID 20225)
-- Name: accounting_entries accounting_entries_reversal_of_entry_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.accounting_entries
    ADD CONSTRAINT accounting_entries_reversal_of_entry_id_key UNIQUE (reversal_of_entry_id);


--
-- TOC entry 5148 (class 2606 OID 20262)
-- Name: accounting_entry_lines accounting_entry_lines_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.accounting_entry_lines
    ADD CONSTRAINT accounting_entry_lines_pkey PRIMARY KEY (id);


--
-- TOC entry 5198 (class 2606 OID 20552)
-- Name: customer_audit_events customer_audit_events_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.customer_audit_events
    ADD CONSTRAINT customer_audit_events_pkey PRIMARY KEY (id);


--
-- TOC entry 5191 (class 2606 OID 20527)
-- Name: customers customers_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT customers_pkey PRIMARY KEY (id);


--
-- TOC entry 5193 (class 2606 OID 20529)
-- Name: customers customers_user_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT customers_user_id_key UNIQUE (user_id);


--
-- TOC entry 5177 (class 2606 OID 20439)
-- Name: inventory_movements inventory_movements_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory_movements
    ADD CONSTRAINT inventory_movements_pkey PRIMARY KEY (id);


--
-- TOC entry 5179 (class 2606 OID 20441)
-- Name: inventory_movements inventory_movements_purchase_receipt_item_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory_movements
    ADD CONSTRAINT inventory_movements_purchase_receipt_item_id_key UNIQUE (purchase_receipt_item_id);


--
-- TOC entry 5206 (class 2606 OID 20646)
-- Name: inventory_reservation_items inventory_reservation_items_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory_reservation_items
    ADD CONSTRAINT inventory_reservation_items_pkey PRIMARY KEY (id);


--
-- TOC entry 5208 (class 2606 OID 20648)
-- Name: inventory_reservation_items inventory_reservation_items_quote_detail_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory_reservation_items
    ADD CONSTRAINT inventory_reservation_items_quote_detail_id_key UNIQUE (quote_detail_id);


--
-- TOC entry 5201 (class 2606 OID 20614)
-- Name: inventory_reservations inventory_reservations_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory_reservations
    ADD CONSTRAINT inventory_reservations_pkey PRIMARY KEY (id);


--
-- TOC entry 5203 (class 2606 OID 20616)
-- Name: inventory_reservations inventory_reservations_quote_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory_reservations
    ADD CONSTRAINT inventory_reservations_quote_id_key UNIQUE (quote_id);


--
-- TOC entry 5120 (class 2606 OID 20085)
-- Name: logistics_records logistics_records_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.logistics_records
    ADD CONSTRAINT logistics_records_pkey PRIMARY KEY (id);


--
-- TOC entry 5112 (class 2606 OID 20036)
-- Name: payments payments_payment_code_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_payment_code_key UNIQUE (payment_code);


--
-- TOC entry 5114 (class 2606 OID 20034)
-- Name: payments payments_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_pkey PRIMARY KEY (id);


--
-- TOC entry 5088 (class 2606 OID 19942)
-- Name: purchase_order_items purchase_order_items_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_pkey PRIMARY KEY (id);


--
-- TOC entry 5086 (class 2606 OID 19931)
-- Name: purchase_orders purchase_orders_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.purchase_orders
    ADD CONSTRAINT purchase_orders_pkey PRIMARY KEY (id);


--
-- TOC entry 5173 (class 2606 OID 20415)
-- Name: purchase_receipt_items purchase_receipt_items_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.purchase_receipt_items
    ADD CONSTRAINT purchase_receipt_items_pkey PRIMARY KEY (id);


--
-- TOC entry 5168 (class 2606 OID 20395)
-- Name: purchase_receipts purchase_receipts_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.purchase_receipts
    ADD CONSTRAINT purchase_receipts_pkey PRIMARY KEY (id);


--
-- TOC entry 5225 (class 2606 OID 20775)
-- Name: quote_audit_events quote_audit_events_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.quote_audit_events
    ADD CONSTRAINT quote_audit_events_pkey PRIMARY KEY (id);


--
-- TOC entry 5106 (class 2606 OID 20012)
-- Name: quote_details quote_details_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.quote_details
    ADD CONSTRAINT quote_details_pkey PRIMARY KEY (id);


--
-- TOC entry 5101 (class 2606 OID 19998)
-- Name: quotes quotes_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.quotes
    ADD CONSTRAINT quotes_pkey PRIMARY KEY (id);


--
-- TOC entry 5075 (class 2606 OID 19887)
-- Name: recovery_tokens recovery_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.recovery_tokens
    ADD CONSTRAINT recovery_tokens_pkey PRIMARY KEY (id);


--
-- TOC entry 5077 (class 2606 OID 19889)
-- Name: recovery_tokens recovery_tokens_token_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.recovery_tokens
    ADD CONSTRAINT recovery_tokens_token_key UNIQUE (token);


--
-- TOC entry 5117 (class 2606 OID 20063)
-- Name: refunds refunds_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.refunds
    ADD CONSTRAINT refunds_pkey PRIMARY KEY (id);


--
-- TOC entry 5220 (class 2606 OID 20712)
-- Name: sales_order_items sales_order_items_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sales_order_items
    ADD CONSTRAINT sales_order_items_pkey PRIMARY KEY (id);


--
-- TOC entry 5222 (class 2606 OID 20714)
-- Name: sales_order_items sales_order_items_quote_detail_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sales_order_items
    ADD CONSTRAINT sales_order_items_quote_detail_id_key UNIQUE (quote_detail_id);


--
-- TOC entry 5212 (class 2606 OID 20678)
-- Name: sales_orders sales_orders_code_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sales_orders
    ADD CONSTRAINT sales_orders_code_key UNIQUE (code);


--
-- TOC entry 5214 (class 2606 OID 20682)
-- Name: sales_orders sales_orders_payment_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sales_orders
    ADD CONSTRAINT sales_orders_payment_id_key UNIQUE (payment_id);


--
-- TOC entry 5216 (class 2606 OID 20676)
-- Name: sales_orders sales_orders_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sales_orders
    ADD CONSTRAINT sales_orders_pkey PRIMARY KEY (id);


--
-- TOC entry 5218 (class 2606 OID 20680)
-- Name: sales_orders sales_orders_quote_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sales_orders
    ADD CONSTRAINT sales_orders_quote_id_key UNIQUE (quote_id);


--
-- TOC entry 5189 (class 2606 OID 20512)
-- Name: schema_migrations schema_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.schema_migrations
    ADD CONSTRAINT schema_migrations_pkey PRIMARY KEY (version);


--
-- TOC entry 5079 (class 2606 OID 19912)
-- Name: spare_parts spare_parts_code_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.spare_parts
    ADD CONSTRAINT spare_parts_code_key UNIQUE (code);


--
-- TOC entry 5081 (class 2606 OID 19910)
-- Name: spare_parts spare_parts_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.spare_parts
    ADD CONSTRAINT spare_parts_pkey PRIMARY KEY (id);


--
-- TOC entry 5184 (class 2606 OID 20467)
-- Name: supplier_purchase_audit_events supplier_purchase_audit_events_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.supplier_purchase_audit_events
    ADD CONSTRAINT supplier_purchase_audit_events_pkey PRIMARY KEY (id);


--
-- TOC entry 5165 (class 2606 OID 20374)
-- Name: supplier_purchase_items supplier_purchase_items_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.supplier_purchase_items
    ADD CONSTRAINT supplier_purchase_items_pkey PRIMARY KEY (id);


--
-- TOC entry 5161 (class 2606 OID 20340)
-- Name: supplier_purchases supplier_purchases_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.supplier_purchases
    ADD CONSTRAINT supplier_purchases_pkey PRIMARY KEY (id);


--
-- TOC entry 5083 (class 2606 OID 19921)
-- Name: suppliers suppliers_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.suppliers
    ADD CONSTRAINT suppliers_pkey PRIMARY KEY (id);


--
-- TOC entry 5187 (class 2606 OID 20492)
-- Name: ticket_audit_events ticket_audit_events_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ticket_audit_events
    ADD CONSTRAINT ticket_audit_events_pkey PRIMARY KEY (id);


--
-- TOC entry 5093 (class 2606 OID 19969)
-- Name: tickets tickets_code_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_code_key UNIQUE (code);


--
-- TOC entry 5095 (class 2606 OID 19967)
-- Name: tickets tickets_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_pkey PRIMARY KEY (id);


--
-- TOC entry 5170 (class 2606 OID 20397)
-- Name: purchase_receipts uq_purchase_receipt_actor_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.purchase_receipts
    ADD CONSTRAINT uq_purchase_receipt_actor_key UNIQUE (purchase_id, actor_user_id, idempotency_key);


--
-- TOC entry 5175 (class 2606 OID 20417)
-- Name: purchase_receipt_items uq_purchase_receipt_line; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.purchase_receipt_items
    ADD CONSTRAINT uq_purchase_receipt_line UNIQUE (receipt_id, purchase_item_id);


--
-- TOC entry 5103 (class 2606 OID 20824)
-- Name: quotes uq_quotes_id_customer; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.quotes
    ADD CONSTRAINT uq_quotes_id_customer UNIQUE (id, customer_id);


--
-- TOC entry 5097 (class 2606 OID 20822)
-- Name: tickets uq_tickets_id_commercial_customer; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT uq_tickets_id_commercial_customer UNIQUE (id, commercial_customer_id);


--
-- TOC entry 5071 (class 2606 OID 19879)
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- TOC entry 5073 (class 2606 OID 19877)
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);

ALTER TABLE public.supplier_audit_events
    ADD CONSTRAINT fk_supplier_audit_events_supplier
    FOREIGN KEY (supplier_id) REFERENCES public.suppliers(id) ON DELETE RESTRICT;
ALTER TABLE public.supplier_audit_events
    ADD CONSTRAINT fk_supplier_audit_events_actor_user
    FOREIGN KEY (actor_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- TOC entry 5156 (class 2606 OID 20284)
-- Name: accounting_audit_events ux_accounting_audit_entry_event; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.accounting_audit_events
    ADD CONSTRAINT ux_accounting_audit_entry_event UNIQUE (entry_id, event_type);


--
-- TOC entry 5151 (class 2606 OID 20264)
-- Name: accounting_entry_lines ux_accounting_entry_line_number; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.accounting_entry_lines
    ADD CONSTRAINT ux_accounting_entry_line_number UNIQUE (entry_id, line_number);


--
-- TOC entry 5125 (class 2606 OID 20104)
-- Name: warranties warranties_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.warranties
    ADD CONSTRAINT warranties_pkey PRIMARY KEY (id);


--
-- TOC entry 5127 (class 2606 OID 20106)
-- Name: warranties warranties_warranty_code_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.warranties
    ADD CONSTRAINT warranties_warranty_code_key UNIQUE (warranty_code);


--
-- TOC entry 5129 (class 2606 OID 20134)
-- Name: warranty_claims warranty_claims_claim_code_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.warranty_claims
    ADD CONSTRAINT warranty_claims_claim_code_key UNIQUE (claim_code);


--
-- TOC entry 5131 (class 2606 OID 20132)
-- Name: warranty_claims warranty_claims_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.warranty_claims
    ADD CONSTRAINT warranty_claims_pkey PRIMARY KEY (id);


--
-- TOC entry 5118 (class 1259 OID 20170)
-- Name: idx_logistics_ticket_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_logistics_ticket_id ON public.logistics_records USING btree (ticket_id);


--
-- TOC entry 5107 (class 1259 OID 20169)
-- Name: idx_payments_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_payments_status ON public.payments USING btree (status);


--
-- TOC entry 5108 (class 1259 OID 20168)
-- Name: idx_payments_ticket_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_payments_ticket_id ON public.payments USING btree (ticket_id);


--
-- TOC entry 5104 (class 1259 OID 20167)
-- Name: idx_quote_details_quote_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_quote_details_quote_id ON public.quote_details USING btree (quote_id);


--
-- TOC entry 5185 (class 1259 OID 20503)
-- Name: idx_ticket_audit_ticket_created; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_ticket_audit_ticket_created ON public.ticket_audit_events USING btree (ticket_id, created_at, id);


--
-- TOC entry 5089 (class 1259 OID 20165)
-- Name: idx_tickets_customer_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_tickets_customer_id ON public.tickets USING btree (customer_id);


--
-- TOC entry 5090 (class 1259 OID 20166)
-- Name: idx_tickets_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_tickets_status ON public.tickets USING btree (status);


--
-- TOC entry 5122 (class 1259 OID 20172)
-- Name: idx_warranties_code; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_warranties_code ON public.warranties USING btree (warranty_code);


--
-- TOC entry 5123 (class 1259 OID 20171)
-- Name: idx_warranties_customer_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_warranties_customer_id ON public.warranties USING btree (customer_id);


--
-- TOC entry 5154 (class 1259 OID 20300)
-- Name: ix_accounting_audit_timeline; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_accounting_audit_timeline ON public.accounting_audit_events USING btree (entry_id, created_at, id);


--
-- TOC entry 5142 (class 1259 OID 20243)
-- Name: ix_accounting_entries_category; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_accounting_entries_category ON public.accounting_entries USING btree (category_id);


--
-- TOC entry 5143 (class 1259 OID 20242)
-- Name: ix_accounting_entries_date_number; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_accounting_entries_date_number ON public.accounting_entries USING btree (operation_date DESC, entry_number DESC);


--
-- TOC entry 5144 (class 1259 OID 20245)
-- Name: ix_accounting_entries_responsible; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_accounting_entries_responsible ON public.accounting_entries USING btree (responsible_user_id);


--
-- TOC entry 5145 (class 1259 OID 20244)
-- Name: ix_accounting_entries_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_accounting_entries_status ON public.accounting_entries USING btree (status);


--
-- TOC entry 5149 (class 1259 OID 20270)
-- Name: ix_accounting_entry_lines_entry; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_accounting_entry_lines_entry ON public.accounting_entry_lines USING btree (entry_id, line_number);


--
-- TOC entry 5199 (class 1259 OID 20563)
-- Name: ix_customer_audit_customer_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_customer_audit_customer_date ON public.customer_audit_events USING btree (customer_id, created_at, id);


--
-- TOC entry 5194 (class 1259 OID 20540)
-- Name: ix_customers_display_name; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_customers_display_name ON public.customers USING btree (lower((display_name)::text), id);


--
-- TOC entry 5195 (class 1259 OID 20542)
-- Name: ix_customers_email; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_customers_email ON public.customers USING btree (lower((email)::text)) WHERE (email IS NOT NULL);


--
-- TOC entry 5196 (class 1259 OID 20541)
-- Name: ix_customers_phone; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_customers_phone ON public.customers USING btree (phone);


--
-- TOC entry 5180 (class 1259 OID 20457)
-- Name: ix_inventory_movements_part_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_inventory_movements_part_date ON public.inventory_movements USING btree (spare_part_id, created_at DESC, id DESC);

CREATE UNIQUE INDEX ux_inventory_movements_actor_idempotency ON public.inventory_movements USING btree (actor_user_id, idempotency_key) WHERE ((idempotency_key IS NOT NULL) AND ((actor_kind)::text = 'USER'::text));

CREATE UNIQUE INDEX ux_inventory_movements_system_opening ON public.inventory_movements USING btree (spare_part_id) WHERE (((movement_type)::text = 'OPENING_BALANCE'::text) AND ((actor_kind)::text = 'SYSTEM'::text) AND (spare_part_id IS NOT NULL));


--
-- TOC entry 5209 (class 1259 OID 20664)
-- Name: ix_inventory_reservation_items_part; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_inventory_reservation_items_part ON public.inventory_reservation_items USING btree (spare_part_id, reservation_id);


--
-- TOC entry 5204 (class 1259 OID 20637)
-- Name: ix_inventory_reservations_active_expiry; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_inventory_reservations_active_expiry ON public.inventory_reservations USING btree (expires_at, quote_id) WHERE ((status)::text = 'RESERVED'::text);


--
-- TOC entry 5109 (class 1259 OID 20603)
-- Name: ix_payments_commercial_customer_created; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_payments_commercial_customer_created ON public.payments USING btree (commercial_customer_id, created_at DESC, id DESC);


--
-- TOC entry 5110 (class 1259 OID 20836)
-- Name: ix_payments_customer_status_created; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_payments_customer_status_created ON public.payments USING btree (commercial_customer_id, status, created_at DESC, id DESC);


--
-- TOC entry 5171 (class 1259 OID 20428)
-- Name: ix_purchase_receipt_items_purchase_item; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_purchase_receipt_items_purchase_item ON public.purchase_receipt_items USING btree (purchase_item_id, id);


--
-- TOC entry 5166 (class 1259 OID 20408)
-- Name: ix_purchase_receipts_purchase; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_purchase_receipts_purchase ON public.purchase_receipts USING btree (purchase_id, received_at, id);


--
-- TOC entry 5223 (class 1259 OID 20786)
-- Name: ix_quote_audit_quote_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_quote_audit_quote_date ON public.quote_audit_events USING btree (quote_id, created_at, id);


--
-- TOC entry 5098 (class 1259 OID 20591)
-- Name: ix_quotes_customer_created; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_quotes_customer_created ON public.quotes USING btree (customer_id, created_at DESC, id DESC);


--
-- TOC entry 5099 (class 1259 OID 20837)
-- Name: ix_quotes_customer_status_created; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_quotes_customer_status_created ON public.quotes USING btree (customer_id, status, created_at DESC, id DESC);


--
-- TOC entry 5210 (class 1259 OID 20703)
-- Name: ix_sales_orders_customer_created; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_sales_orders_customer_created ON public.sales_orders USING btree (customer_id, created_at DESC, id DESC);


--
-- TOC entry 5182 (class 1259 OID 20478)
-- Name: ix_supplier_purchase_audit_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_supplier_purchase_audit_date ON public.supplier_purchase_audit_events USING btree (purchase_id, created_at, id);


--
-- TOC entry 5163 (class 1259 OID 20385)
-- Name: ix_supplier_purchase_items_purchase; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_supplier_purchase_items_purchase ON public.supplier_purchase_items USING btree (purchase_id, id);


--
-- TOC entry 5157 (class 1259 OID 20359)
-- Name: ix_supplier_purchases_payment_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_supplier_purchases_payment_status ON public.supplier_purchases USING btree (payment_status, issue_date DESC, id DESC);


--
-- TOC entry 5158 (class 1259 OID 20358)
-- Name: ix_supplier_purchases_status_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_supplier_purchases_status_date ON public.supplier_purchases USING btree (status, issue_date DESC, id DESC);


--
-- TOC entry 5159 (class 1259 OID 20357)
-- Name: ix_supplier_purchases_supplier_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_supplier_purchases_supplier_date ON public.supplier_purchases USING btree (supplier_id, issue_date DESC, id DESC);


--
-- TOC entry 5091 (class 1259 OID 20574)
-- Name: ix_tickets_commercial_customer_created; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_tickets_commercial_customer_created ON public.tickets USING btree (commercial_customer_id, created_at DESC, id DESC);


--
-- TOC entry 5146 (class 1259 OID 20241)
-- Name: ux_accounting_entries_actor_idempotency; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ux_accounting_entries_actor_idempotency ON public.accounting_entries USING btree (responsible_user_id, idempotency_key) WHERE (idempotency_key IS NOT NULL);


--
-- TOC entry 5181 (class 1259 OID 20796)
-- Name: ux_inventory_movements_sales_item; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ux_inventory_movements_sales_item ON public.inventory_movements USING btree (sales_order_item_id) WHERE (sales_order_item_id IS NOT NULL);


--
-- TOC entry 5121 (class 1259 OID 20745)
-- Name: ux_logistics_sales_order; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ux_logistics_sales_order ON public.logistics_records USING btree (sales_order_id) WHERE (sales_order_id IS NOT NULL);


--
-- TOC entry 5115 (class 1259 OID 20604)
-- Name: ux_payments_idempotency_key; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ux_payments_idempotency_key ON public.payments USING btree (idempotency_key) WHERE (idempotency_key IS NOT NULL);


--
-- TOC entry 5162 (class 1259 OID 20356)
-- Name: ux_supplier_purchase_document; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ux_supplier_purchase_document ON public.supplier_purchases USING btree (supplier_id, upper(btrim((document_type)::text)), upper(btrim((COALESCE(document_series, ''::character varying))::text)), upper(btrim((document_number)::text))) WHERE ((status)::text <> 'CANCELLED'::text);


--
-- TOC entry 5084 (class 1259 OID 20313)
-- Name: ux_suppliers_tax_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ux_suppliers_tax_id ON public.suppliers USING btree (upper(btrim((tax_id)::text))) WHERE ((tax_id IS NOT NULL) AND (btrim((tax_id)::text) <> ''::text));


--
-- TOC entry 5320 (class 2620 OID 20306)
-- Name: accounting_audit_events accounting_audit_append_only; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER accounting_audit_append_only BEFORE DELETE OR UPDATE ON public.accounting_audit_events FOR EACH ROW EXECUTE FUNCTION public.accounting_reject_mutation();

ALTER TABLE public.accounting_audit_events DISABLE TRIGGER accounting_audit_append_only;


--
-- TOC entry 5316 (class 2620 OID 20307)
-- Name: accounting_entries accounting_balance_after_entry; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE CONSTRAINT TRIGGER accounting_balance_after_entry AFTER INSERT OR UPDATE ON public.accounting_entries DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.accounting_check_entry_balance();


--
-- TOC entry 5318 (class 2620 OID 20309)
-- Name: accounting_entry_lines accounting_balance_after_line; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE CONSTRAINT TRIGGER accounting_balance_after_line AFTER INSERT ON public.accounting_entry_lines DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.accounting_check_entry_balance();


--
-- TOC entry 5317 (class 2620 OID 20304)
-- Name: accounting_entries accounting_entries_immutable; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER accounting_entries_immutable BEFORE DELETE OR UPDATE ON public.accounting_entries FOR EACH ROW EXECUTE FUNCTION public.accounting_guard_entry_update();

ALTER TABLE public.accounting_entries DISABLE TRIGGER accounting_entries_immutable;


--
-- TOC entry 5319 (class 2620 OID 20305)
-- Name: accounting_entry_lines accounting_lines_immutable; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER accounting_lines_immutable BEFORE DELETE OR UPDATE ON public.accounting_entry_lines FOR EACH ROW EXECUTE FUNCTION public.accounting_reject_mutation();

ALTER TABLE public.accounting_entry_lines DISABLE TRIGGER accounting_lines_immutable;


--
-- TOC entry 5313 (class 2620 OID 20181)
-- Name: logistics_records trg_logistics_records_updated_at; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_logistics_records_updated_at BEFORE UPDATE ON public.logistics_records FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- TOC entry 5311 (class 2620 OID 20179)
-- Name: payments trg_payments_updated_at; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_payments_updated_at BEFORE UPDATE ON public.payments FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- TOC entry 5308 (class 2620 OID 20176)
-- Name: purchase_orders trg_purchase_orders_updated_at; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_purchase_orders_updated_at BEFORE UPDATE ON public.purchase_orders FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- TOC entry 5310 (class 2620 OID 20178)
-- Name: quotes trg_quotes_updated_at; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_quotes_updated_at BEFORE UPDATE ON public.quotes FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- TOC entry 5312 (class 2620 OID 20180)
-- Name: refunds trg_refunds_updated_at; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_refunds_updated_at BEFORE UPDATE ON public.refunds FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- TOC entry 5307 (class 2620 OID 20175)
-- Name: spare_parts trg_spare_parts_updated_at; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_spare_parts_updated_at BEFORE UPDATE ON public.spare_parts FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- TOC entry 5309 (class 2620 OID 20177)
-- Name: tickets trg_tickets_updated_at; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_tickets_updated_at BEFORE UPDATE ON public.tickets FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- TOC entry 5306 (class 2620 OID 20174)
-- Name: users trg_users_updated_at; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON public.users FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- TOC entry 5314 (class 2620 OID 20182)
-- Name: warranties trg_warranties_updated_at; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_warranties_updated_at BEFORE UPDATE ON public.warranties FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();


--
-- TOC entry 5315 (class 2620 OID 20183)
-- Name: warranty_claims trg_warranty_claims_updated_at; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_warranty_claims_updated_at BEFORE UPDATE ON public.warranty_claims FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE OR REPLACE FUNCTION public.inventory_movements_reject_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    RAISE EXCEPTION 'Inventory movements are immutable';
END;
$function$;

CREATE TRIGGER trg_inventory_movements_immutable
BEFORE UPDATE OR DELETE ON public.inventory_movements
FOR EACH ROW EXECUTE FUNCTION public.inventory_movements_reject_mutation();


--
-- TOC entry 5266 (class 2606 OID 20290)
-- Name: accounting_audit_events accounting_audit_events_actor_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.accounting_audit_events
    ADD CONSTRAINT accounting_audit_events_actor_user_id_fkey FOREIGN KEY (actor_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- TOC entry 5267 (class 2606 OID 20285)
-- Name: accounting_audit_events accounting_audit_events_entry_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.accounting_audit_events
    ADD CONSTRAINT accounting_audit_events_entry_id_fkey FOREIGN KEY (entry_id) REFERENCES public.accounting_entries(id) ON DELETE RESTRICT;


--
-- TOC entry 5268 (class 2606 OID 20295)
-- Name: accounting_audit_events accounting_audit_events_related_entry_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.accounting_audit_events
    ADD CONSTRAINT accounting_audit_events_related_entry_id_fkey FOREIGN KEY (related_entry_id) REFERENCES public.accounting_entries(id) ON DELETE RESTRICT;


--
-- TOC entry 5262 (class 2606 OID 20226)
-- Name: accounting_entries accounting_entries_category_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.accounting_entries
    ADD CONSTRAINT accounting_entries_category_id_fkey FOREIGN KEY (category_id) REFERENCES public.accounting_categories(id) ON DELETE RESTRICT;


--
-- TOC entry 5263 (class 2606 OID 20231)
-- Name: accounting_entries accounting_entries_responsible_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.accounting_entries
    ADD CONSTRAINT accounting_entries_responsible_user_id_fkey FOREIGN KEY (responsible_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- TOC entry 5264 (class 2606 OID 20236)
-- Name: accounting_entries accounting_entries_reversal_of_entry_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.accounting_entries
    ADD CONSTRAINT accounting_entries_reversal_of_entry_id_fkey FOREIGN KEY (reversal_of_entry_id) REFERENCES public.accounting_entries(id) ON DELETE RESTRICT;


--
-- TOC entry 5265 (class 2606 OID 20265)
-- Name: accounting_entry_lines accounting_entry_lines_entry_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.accounting_entry_lines
    ADD CONSTRAINT accounting_entry_lines_entry_id_fkey FOREIGN KEY (entry_id) REFERENCES public.accounting_entries(id) ON DELETE RESTRICT;


--
-- TOC entry 5288 (class 2606 OID 20558)
-- Name: customer_audit_events customer_audit_events_actor_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.customer_audit_events
    ADD CONSTRAINT customer_audit_events_actor_user_id_fkey FOREIGN KEY (actor_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- TOC entry 5289 (class 2606 OID 20553)
-- Name: customer_audit_events customer_audit_events_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.customer_audit_events
    ADD CONSTRAINT customer_audit_events_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE RESTRICT;


--
-- TOC entry 5286 (class 2606 OID 20535)
-- Name: customers customers_created_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT customers_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- TOC entry 5287 (class 2606 OID 20530)
-- Name: customers customers_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT customers_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- TOC entry 5278 (class 2606 OID 20787)
-- Name: inventory_movements fk_inventory_movements_sales_order_item; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory_movements
    ADD CONSTRAINT fk_inventory_movements_sales_order_item FOREIGN KEY (sales_order_item_id) REFERENCES public.sales_order_items(id) ON DELETE RESTRICT;


--
-- TOC entry 5250 (class 2606 OID 20735)
-- Name: logistics_records fk_logistics_commercial_customer; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.logistics_records
    ADD CONSTRAINT fk_logistics_commercial_customer FOREIGN KEY (commercial_customer_id) REFERENCES public.customers(id) ON DELETE RESTRICT;


--
-- TOC entry 5251 (class 2606 OID 20740)
-- Name: logistics_records fk_logistics_created_by; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.logistics_records
    ADD CONSTRAINT fk_logistics_created_by FOREIGN KEY (created_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- TOC entry 5252 (class 2606 OID 20730)
-- Name: logistics_records fk_logistics_sales_order; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.logistics_records
    ADD CONSTRAINT fk_logistics_sales_order FOREIGN KEY (sales_order_id) REFERENCES public.sales_orders(id) ON DELETE RESTRICT;


--
-- TOC entry 5241 (class 2606 OID 20593)
-- Name: payments fk_payments_commercial_customer; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT fk_payments_commercial_customer FOREIGN KEY (commercial_customer_id) REFERENCES public.customers(id) ON DELETE RESTRICT;


--
-- TOC entry 5242 (class 2606 OID 20598)
-- Name: payments fk_payments_confirmed_by; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT fk_payments_confirmed_by FOREIGN KEY (confirmed_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- TOC entry 5243 (class 2606 OID 20831)
-- Name: payments fk_payments_quote_customer; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT fk_payments_quote_customer FOREIGN KEY (quote_id, commercial_customer_id) REFERENCES public.quotes(id, customer_id) ON DELETE RESTRICT;


--
-- TOC entry 5234 (class 2606 OID 20585)
-- Name: quotes fk_quotes_accepted_by; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.quotes
    ADD CONSTRAINT fk_quotes_accepted_by FOREIGN KEY (accepted_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- TOC entry 5235 (class 2606 OID 20580)
-- Name: quotes fk_quotes_created_by; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.quotes
    ADD CONSTRAINT fk_quotes_created_by FOREIGN KEY (created_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- TOC entry 5236 (class 2606 OID 20575)
-- Name: quotes fk_quotes_customer; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.quotes
    ADD CONSTRAINT fk_quotes_customer FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE RESTRICT;


--
-- TOC entry 5237 (class 2606 OID 20825)
-- Name: quotes fk_quotes_ticket_customer; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.quotes
    ADD CONSTRAINT fk_quotes_ticket_customer FOREIGN KEY (ticket_id, customer_id) REFERENCES public.tickets(id, commercial_customer_id) ON DELETE RESTRICT;


--
-- TOC entry 5247 (class 2606 OID 20761)
-- Name: refunds fk_refunds_requested_by; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.refunds
    ADD CONSTRAINT fk_refunds_requested_by FOREIGN KEY (requested_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- TOC entry 5230 (class 2606 OID 20564)
-- Name: tickets fk_tickets_commercial_customer; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT fk_tickets_commercial_customer FOREIGN KEY (commercial_customer_id) REFERENCES public.customers(id) ON DELETE RESTRICT;


--
-- TOC entry 5231 (class 2606 OID 20569)
-- Name: tickets fk_tickets_created_by; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT fk_tickets_created_by FOREIGN KEY (created_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- TOC entry 5254 (class 2606 OID 20751)
-- Name: warranties fk_warranties_commercial_customer; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.warranties
    ADD CONSTRAINT fk_warranties_commercial_customer FOREIGN KEY (commercial_customer_id) REFERENCES public.customers(id) ON DELETE RESTRICT;


--
-- TOC entry 5255 (class 2606 OID 20756)
-- Name: warranties fk_warranties_created_by; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.warranties
    ADD CONSTRAINT fk_warranties_created_by FOREIGN KEY (created_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- TOC entry 5256 (class 2606 OID 20746)
-- Name: warranties fk_warranties_sales_order; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.warranties
    ADD CONSTRAINT fk_warranties_sales_order FOREIGN KEY (sales_order_id) REFERENCES public.sales_orders(id) ON DELETE RESTRICT;


--
-- TOC entry 5279 (class 2606 OID 20452)
-- Name: inventory_movements inventory_movements_actor_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory_movements
    ADD CONSTRAINT inventory_movements_actor_user_id_fkey FOREIGN KEY (actor_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- TOC entry 5280 (class 2606 OID 20447)
-- Name: inventory_movements inventory_movements_purchase_receipt_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory_movements
    ADD CONSTRAINT inventory_movements_purchase_receipt_item_id_fkey FOREIGN KEY (purchase_receipt_item_id) REFERENCES public.purchase_receipt_items(id) ON DELETE RESTRICT;


--
-- TOC entry 5281 (class 2606 OID 20442)
-- Name: inventory_movements inventory_movements_spare_part_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory_movements
    ADD CONSTRAINT inventory_movements_spare_part_id_fkey FOREIGN KEY (spare_part_id) REFERENCES public.spare_parts(id) ON DELETE SET NULL;


--
-- TOC entry 5294 (class 2606 OID 20654)
-- Name: inventory_reservation_items inventory_reservation_items_quote_detail_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory_reservation_items
    ADD CONSTRAINT inventory_reservation_items_quote_detail_id_fkey FOREIGN KEY (quote_detail_id) REFERENCES public.quote_details(id) ON DELETE RESTRICT;


--
-- TOC entry 5295 (class 2606 OID 20649)
-- Name: inventory_reservation_items inventory_reservation_items_reservation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory_reservation_items
    ADD CONSTRAINT inventory_reservation_items_reservation_id_fkey FOREIGN KEY (reservation_id) REFERENCES public.inventory_reservations(id) ON DELETE RESTRICT;


--
-- TOC entry 5296 (class 2606 OID 20659)
-- Name: inventory_reservation_items inventory_reservation_items_spare_part_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory_reservation_items
    ADD CONSTRAINT inventory_reservation_items_spare_part_id_fkey FOREIGN KEY (spare_part_id) REFERENCES public.spare_parts(id) ON DELETE RESTRICT;


--
-- TOC entry 5290 (class 2606 OID 20627)
-- Name: inventory_reservations inventory_reservations_accepted_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory_reservations
    ADD CONSTRAINT inventory_reservations_accepted_by_user_id_fkey FOREIGN KEY (accepted_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- TOC entry 5291 (class 2606 OID 20622)
-- Name: inventory_reservations inventory_reservations_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory_reservations
    ADD CONSTRAINT inventory_reservations_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE RESTRICT;


--
-- TOC entry 5292 (class 2606 OID 20617)
-- Name: inventory_reservations inventory_reservations_quote_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory_reservations
    ADD CONSTRAINT inventory_reservations_quote_id_fkey FOREIGN KEY (quote_id) REFERENCES public.quotes(id) ON DELETE RESTRICT;


--
-- TOC entry 5293 (class 2606 OID 20632)
-- Name: inventory_reservations inventory_reservations_released_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory_reservations
    ADD CONSTRAINT inventory_reservations_released_by_user_id_fkey FOREIGN KEY (released_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- TOC entry 5253 (class 2606 OID 20086)
-- Name: logistics_records logistics_records_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.logistics_records
    ADD CONSTRAINT logistics_records_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(id) ON DELETE CASCADE;


--
-- TOC entry 5244 (class 2606 OID 20047)
-- Name: payments payments_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- TOC entry 5245 (class 2606 OID 20042)
-- Name: payments payments_quote_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_quote_id_fkey FOREIGN KEY (quote_id) REFERENCES public.quotes(id) ON DELETE SET NULL;


--
-- TOC entry 5246 (class 2606 OID 20037)
-- Name: payments payments_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(id) ON DELETE CASCADE;


--
-- TOC entry 5228 (class 2606 OID 19943)
-- Name: purchase_order_items purchase_order_items_purchase_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_purchase_order_id_fkey FOREIGN KEY (purchase_order_id) REFERENCES public.purchase_orders(id) ON DELETE CASCADE;


--
-- TOC entry 5229 (class 2606 OID 19948)
-- Name: purchase_order_items purchase_order_items_spare_part_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.purchase_order_items
    ADD CONSTRAINT purchase_order_items_spare_part_id_fkey FOREIGN KEY (spare_part_id) REFERENCES public.spare_parts(id) ON DELETE SET NULL;


--
-- TOC entry 5227 (class 2606 OID 19932)
-- Name: purchase_orders purchase_orders_supplier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.purchase_orders
    ADD CONSTRAINT purchase_orders_supplier_id_fkey FOREIGN KEY (supplier_id) REFERENCES public.suppliers(id) ON DELETE RESTRICT;


--
-- TOC entry 5276 (class 2606 OID 20423)
-- Name: purchase_receipt_items purchase_receipt_items_purchase_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.purchase_receipt_items
    ADD CONSTRAINT purchase_receipt_items_purchase_item_id_fkey FOREIGN KEY (purchase_item_id) REFERENCES public.supplier_purchase_items(id) ON DELETE RESTRICT;


--
-- TOC entry 5277 (class 2606 OID 20418)
-- Name: purchase_receipt_items purchase_receipt_items_receipt_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.purchase_receipt_items
    ADD CONSTRAINT purchase_receipt_items_receipt_id_fkey FOREIGN KEY (receipt_id) REFERENCES public.purchase_receipts(id) ON DELETE RESTRICT;


--
-- TOC entry 5274 (class 2606 OID 20403)
-- Name: purchase_receipts purchase_receipts_actor_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.purchase_receipts
    ADD CONSTRAINT purchase_receipts_actor_user_id_fkey FOREIGN KEY (actor_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- TOC entry 5275 (class 2606 OID 20398)
-- Name: purchase_receipts purchase_receipts_purchase_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.purchase_receipts
    ADD CONSTRAINT purchase_receipts_purchase_id_fkey FOREIGN KEY (purchase_id) REFERENCES public.supplier_purchases(id) ON DELETE RESTRICT;


--
-- TOC entry 5304 (class 2606 OID 20781)
-- Name: quote_audit_events quote_audit_events_actor_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.quote_audit_events
    ADD CONSTRAINT quote_audit_events_actor_user_id_fkey FOREIGN KEY (actor_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- TOC entry 5305 (class 2606 OID 20776)
-- Name: quote_audit_events quote_audit_events_quote_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.quote_audit_events
    ADD CONSTRAINT quote_audit_events_quote_id_fkey FOREIGN KEY (quote_id) REFERENCES public.quotes(id) ON DELETE RESTRICT;


--
-- TOC entry 5239 (class 2606 OID 20013)
-- Name: quote_details quote_details_quote_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.quote_details
    ADD CONSTRAINT quote_details_quote_id_fkey FOREIGN KEY (quote_id) REFERENCES public.quotes(id) ON DELETE CASCADE;


--
-- TOC entry 5240 (class 2606 OID 20018)
-- Name: quote_details quote_details_spare_part_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.quote_details
    ADD CONSTRAINT quote_details_spare_part_id_fkey FOREIGN KEY (spare_part_id) REFERENCES public.spare_parts(id) ON DELETE RESTRICT;


--
-- TOC entry 5238 (class 2606 OID 19999)
-- Name: quotes quotes_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.quotes
    ADD CONSTRAINT quotes_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(id) ON DELETE CASCADE;


--
-- TOC entry 5226 (class 2606 OID 19890)
-- Name: recovery_tokens recovery_tokens_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.recovery_tokens
    ADD CONSTRAINT recovery_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- TOC entry 5248 (class 2606 OID 20064)
-- Name: refunds refunds_payment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.refunds
    ADD CONSTRAINT refunds_payment_id_fkey FOREIGN KEY (payment_id) REFERENCES public.payments(id) ON DELETE CASCADE;


--
-- TOC entry 5249 (class 2606 OID 20069)
-- Name: refunds refunds_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.refunds
    ADD CONSTRAINT refunds_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(id) ON DELETE CASCADE;


--
-- TOC entry 5301 (class 2606 OID 20720)
-- Name: sales_order_items sales_order_items_quote_detail_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sales_order_items
    ADD CONSTRAINT sales_order_items_quote_detail_id_fkey FOREIGN KEY (quote_detail_id) REFERENCES public.quote_details(id) ON DELETE RESTRICT;


--
-- TOC entry 5302 (class 2606 OID 20715)
-- Name: sales_order_items sales_order_items_sales_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sales_order_items
    ADD CONSTRAINT sales_order_items_sales_order_id_fkey FOREIGN KEY (sales_order_id) REFERENCES public.sales_orders(id) ON DELETE RESTRICT;


--
-- TOC entry 5303 (class 2606 OID 20725)
-- Name: sales_order_items sales_order_items_spare_part_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sales_order_items
    ADD CONSTRAINT sales_order_items_spare_part_id_fkey FOREIGN KEY (spare_part_id) REFERENCES public.spare_parts(id) ON DELETE SET NULL;


--
-- TOC entry 5297 (class 2606 OID 20698)
-- Name: sales_orders sales_orders_created_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sales_orders
    ADD CONSTRAINT sales_orders_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- TOC entry 5298 (class 2606 OID 20693)
-- Name: sales_orders sales_orders_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sales_orders
    ADD CONSTRAINT sales_orders_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE RESTRICT;


--
-- TOC entry 5299 (class 2606 OID 20688)
-- Name: sales_orders sales_orders_payment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sales_orders
    ADD CONSTRAINT sales_orders_payment_id_fkey FOREIGN KEY (payment_id) REFERENCES public.payments(id) ON DELETE RESTRICT;


--
-- TOC entry 5300 (class 2606 OID 20683)
-- Name: sales_orders sales_orders_quote_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sales_orders
    ADD CONSTRAINT sales_orders_quote_id_fkey FOREIGN KEY (quote_id) REFERENCES public.quotes(id) ON DELETE RESTRICT;


--
-- TOC entry 5282 (class 2606 OID 20473)
-- Name: supplier_purchase_audit_events supplier_purchase_audit_events_actor_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.supplier_purchase_audit_events
    ADD CONSTRAINT supplier_purchase_audit_events_actor_user_id_fkey FOREIGN KEY (actor_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- TOC entry 5283 (class 2606 OID 20468)
-- Name: supplier_purchase_audit_events supplier_purchase_audit_events_purchase_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.supplier_purchase_audit_events
    ADD CONSTRAINT supplier_purchase_audit_events_purchase_id_fkey FOREIGN KEY (purchase_id) REFERENCES public.supplier_purchases(id) ON DELETE RESTRICT;


--
-- TOC entry 5272 (class 2606 OID 20375)
-- Name: supplier_purchase_items supplier_purchase_items_purchase_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.supplier_purchase_items
    ADD CONSTRAINT supplier_purchase_items_purchase_id_fkey FOREIGN KEY (purchase_id) REFERENCES public.supplier_purchases(id) ON DELETE RESTRICT;


--
-- TOC entry 5273 (class 2606 OID 20380)
-- Name: supplier_purchase_items supplier_purchase_items_spare_part_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.supplier_purchase_items
    ADD CONSTRAINT supplier_purchase_items_spare_part_id_fkey FOREIGN KEY (spare_part_id) REFERENCES public.spare_parts(id) ON DELETE SET NULL;


--
-- TOC entry 5269 (class 2606 OID 20351)
-- Name: supplier_purchases supplier_purchases_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.supplier_purchases
    ADD CONSTRAINT supplier_purchases_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- TOC entry 5270 (class 2606 OID 20346)
-- Name: supplier_purchases supplier_purchases_purchase_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.supplier_purchases
    ADD CONSTRAINT supplier_purchases_purchase_order_id_fkey FOREIGN KEY (purchase_order_id) REFERENCES public.purchase_orders(id) ON DELETE RESTRICT;


--
-- TOC entry 5271 (class 2606 OID 20341)
-- Name: supplier_purchases supplier_purchases_supplier_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.supplier_purchases
    ADD CONSTRAINT supplier_purchases_supplier_id_fkey FOREIGN KEY (supplier_id) REFERENCES public.suppliers(id) ON DELETE RESTRICT;


--
-- TOC entry 5284 (class 2606 OID 20498)
-- Name: ticket_audit_events ticket_audit_events_actor_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ticket_audit_events
    ADD CONSTRAINT ticket_audit_events_actor_user_id_fkey FOREIGN KEY (actor_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- TOC entry 5285 (class 2606 OID 20493)
-- Name: ticket_audit_events ticket_audit_events_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ticket_audit_events
    ADD CONSTRAINT ticket_audit_events_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(id) ON DELETE RESTRICT;


--
-- TOC entry 5232 (class 2606 OID 19970)
-- Name: tickets tickets_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- TOC entry 5233 (class 2606 OID 19975)
-- Name: tickets tickets_technician_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tickets
    ADD CONSTRAINT tickets_technician_id_fkey FOREIGN KEY (technician_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- TOC entry 5257 (class 2606 OID 20117)
-- Name: warranties warranties_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.warranties
    ADD CONSTRAINT warranties_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- TOC entry 5258 (class 2606 OID 20112)
-- Name: warranties warranties_quote_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.warranties
    ADD CONSTRAINT warranties_quote_id_fkey FOREIGN KEY (quote_id) REFERENCES public.quotes(id) ON DELETE SET NULL;


--
-- TOC entry 5259 (class 2606 OID 20107)
-- Name: warranties warranties_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.warranties
    ADD CONSTRAINT warranties_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(id) ON DELETE CASCADE;


--
-- TOC entry 5260 (class 2606 OID 20140)
-- Name: warranty_claims warranty_claims_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.warranty_claims
    ADD CONSTRAINT warranty_claims_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(id) ON DELETE SET NULL;


--
-- TOC entry 5261 (class 2606 OID 20135)
-- Name: warranty_claims warranty_claims_warranty_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.warranty_claims
    ADD CONSTRAINT warranty_claims_warranty_id_fkey FOREIGN KEY (warranty_id) REFERENCES public.warranties(id) ON DELETE CASCADE;


-- Completed on 2026-11-04 00:18:17

--
-- PostgreSQL database dump complete
--

-- Bootstrap mirror of 012_accounting_catalog_schema.sql; use only for an empty database
-- Catálogo de cuentas, periodos y auditoría contable. Migración aditiva.
-- Requiere el esquema contable existente. No asigna cuentas a asientos históricos.

CREATE TABLE public.accounting_plans (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    code VARCHAR(80) NOT NULL,
    edition VARCHAR(80) NOT NULL,
    name VARCHAR(200) NOT NULL,
    jurisdiction VARCHAR(8) NOT NULL,
    source_name VARCHAR(200),
    source_url TEXT,
    effective_from DATE,
    effective_to DATE,
    status VARCHAR(8) NOT NULL DEFAULT 'ACTIVE',
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_by BIGINT NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT accounting_plans_identity_uq UNIQUE (code, edition),
    CONSTRAINT accounting_plans_status_ck CHECK (status IN ('ACTIVE', 'INACTIVE')),
    CONSTRAINT accounting_plans_dates_ck CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from),
    CONSTRAINT accounting_plans_default_active_ck CHECK (NOT is_default OR status = 'ACTIVE')
);
CREATE UNIQUE INDEX accounting_plans_one_active_default_uq
    ON public.accounting_plans ((is_default)) WHERE is_default IS TRUE AND status = 'ACTIVE';

CREATE TABLE public.accounting_accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    plan_id BIGINT NOT NULL REFERENCES public.accounting_plans(id) ON DELETE RESTRICT,
    code VARCHAR(40) NOT NULL,
    name VARCHAR(200) NOT NULL,
    parent_account_id BIGINT,
    account_group VARCHAR(40),
    normal_balance VARCHAR(6),
    is_postable BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(8) NOT NULL DEFAULT 'ACTIVE',
    effective_from DATE,
    effective_to DATE,
    created_by BIGINT NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT accounting_accounts_plan_code_uq UNIQUE (plan_id, code),
    CONSTRAINT accounting_accounts_plan_id_uq UNIQUE (plan_id, id),
    CONSTRAINT accounting_accounts_parent_same_plan_fk FOREIGN KEY (plan_id, parent_account_id)
        REFERENCES public.accounting_accounts(plan_id, id) ON DELETE RESTRICT,
    CONSTRAINT accounting_accounts_normal_balance_ck CHECK (normal_balance IS NULL OR normal_balance IN ('DEBIT', 'CREDIT')),
    CONSTRAINT accounting_accounts_postable_balance_ck CHECK (NOT is_postable OR normal_balance IS NOT NULL),
    CONSTRAINT accounting_accounts_status_ck CHECK (status IN ('ACTIVE', 'INACTIVE')),
    CONSTRAINT accounting_accounts_dates_ck CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from)
);
CREATE INDEX accounting_accounts_parent_idx ON public.accounting_accounts(plan_id, parent_account_id);
CREATE INDEX accounting_accounts_lookup_idx ON public.accounting_accounts(plan_id, status, is_postable, code);

CREATE TABLE public.accounting_periods (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    year SMALLINT NOT NULL,
    month SMALLINT NOT NULL,
    status VARCHAR(6) NOT NULL DEFAULT 'OPEN',
    closed_at TIMESTAMPTZ,
    closed_by BIGINT REFERENCES public.users(id) ON DELETE RESTRICT,
    reopened_at TIMESTAMPTZ,
    reopened_by BIGINT REFERENCES public.users(id) ON DELETE RESTRICT,
    reopen_reason VARCHAR(2000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT accounting_periods_year_month_uq UNIQUE (year, month),
    CONSTRAINT accounting_periods_month_ck CHECK (month BETWEEN 1 AND 12),
    CONSTRAINT accounting_periods_year_ck CHECK (year BETWEEN 2000 AND 9999),
    CONSTRAINT accounting_periods_status_ck CHECK (status IN ('OPEN', 'CLOSED')),
    CONSTRAINT accounting_periods_close_actor_ck CHECK ((status = 'OPEN') OR (closed_at IS NOT NULL AND closed_by IS NOT NULL)),
    CONSTRAINT accounting_periods_reopen_reason_ck CHECK (reopen_reason IS NULL OR length(btrim(reopen_reason)) > 0)
);
CREATE INDEX accounting_periods_status_idx ON public.accounting_periods(status, year, month);

CREATE TABLE public.accounting_configuration_events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    entity_type VARCHAR(40) NOT NULL,
    entity_id BIGINT NOT NULL,
    action VARCHAR(60) NOT NULL,
    actor_user_id BIGINT NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
    previous_state JSONB,
    new_state JSONB,
    reason VARCHAR(2000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX accounting_configuration_events_entity_idx
    ON public.accounting_configuration_events(entity_type, entity_id, created_at, id);
CREATE INDEX accounting_configuration_events_actor_idx
    ON public.accounting_configuration_events(actor_user_id, created_at DESC);

ALTER TABLE public.accounting_entries
    ADD COLUMN accounting_plan_id BIGINT,
    ADD CONSTRAINT accounting_entries_plan_fk FOREIGN KEY (accounting_plan_id)
        REFERENCES public.accounting_plans(id) ON DELETE RESTRICT;
ALTER TABLE public.accounting_entry_lines
    ADD COLUMN account_id BIGINT,
    ADD CONSTRAINT accounting_entry_lines_account_fk FOREIGN KEY (account_id)
        REFERENCES public.accounting_accounts(id) ON DELETE RESTRICT;
CREATE INDEX accounting_entries_plan_date_idx ON public.accounting_entries(accounting_plan_id, operation_date, entry_number);
CREATE INDEX accounting_entry_lines_account_entry_idx ON public.accounting_entry_lines(account_id, entry_id);

-- Extiende la protección inmutable para que el plan tampoco pueda cambiar tras crear el asiento.
CREATE OR REPLACE FUNCTION public.accounting_guard_entry_update() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Accounting entries cannot be deleted' USING ERRCODE = '55000';
    END IF;
    IF ROW(NEW.entry_number, NEW.operation_date, NEW.concept, NEW.detail, NEW.category_id,
           NEW.currency, NEW.debit_total, NEW.credit_total, NEW.responsible_user_id,
           NEW.idempotency_key, NEW.request_hash, NEW.reversal_of_entry_id,
           NEW.reversal_reason, NEW.created_at, NEW.accounting_plan_id)
       IS DISTINCT FROM
       ROW(OLD.entry_number, OLD.operation_date, OLD.concept, OLD.detail, OLD.category_id,
           OLD.currency, OLD.debit_total, OLD.credit_total, OLD.responsible_user_id,
           OLD.idempotency_key, OLD.request_hash, OLD.reversal_of_entry_id,
           OLD.reversal_reason, OLD.created_at, OLD.accounting_plan_id) THEN
        RAISE EXCEPTION 'Accounting entry fields are immutable' USING ERRCODE = '55000';
    END IF;
    IF OLD.status <> 'CONFIRMED' OR NEW.status <> 'REVERSED' OR OLD.reversed_at IS NOT NULL OR
       NEW.reversed_at IS NULL OR NEW.updated_at IS NULL OR NEW.updated_at < OLD.updated_at THEN
        RAISE EXCEPTION 'Invalid accounting status transition' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.accounting_validate_account_hierarchy() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE parent_is_postable BOOLEAN;
BEGIN
    IF NEW.parent_account_id IS NOT NULL THEN
        SELECT is_postable INTO parent_is_postable FROM public.accounting_accounts
         WHERE plan_id = NEW.plan_id AND id = NEW.parent_account_id;
        IF NOT FOUND THEN RAISE EXCEPTION 'Parent account must belong to the same plan' USING ERRCODE = '23503'; END IF;
        IF parent_is_postable THEN RAISE EXCEPTION 'Parent account with children cannot be postable' USING ERRCODE = '23514'; END IF;
        IF EXISTS (
            WITH RECURSIVE ancestors(id, parent_account_id) AS (
                SELECT id, parent_account_id FROM public.accounting_accounts WHERE id = NEW.parent_account_id
                UNION ALL
                SELECT a.id, a.parent_account_id FROM public.accounting_accounts a
                JOIN ancestors x ON a.id = x.parent_account_id WHERE a.plan_id = NEW.plan_id
            ) SELECT 1 FROM ancestors WHERE id = NEW.id
        ) THEN RAISE EXCEPTION 'Account hierarchy cannot contain cycles' USING ERRCODE = '23514'; END IF;
    END IF;
    IF NEW.is_postable AND EXISTS (SELECT 1 FROM public.accounting_accounts WHERE parent_account_id = NEW.id) THEN
        RAISE EXCEPTION 'Account with children cannot be postable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER accounting_accounts_hierarchy_guard
    BEFORE INSERT OR UPDATE OF plan_id, parent_account_id, is_postable ON public.accounting_accounts
    FOR EACH ROW EXECUTE FUNCTION public.accounting_validate_account_hierarchy();

CREATE OR REPLACE FUNCTION public.accounting_check_period_open() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE period_status VARCHAR(6); target_year SMALLINT; target_month SMALLINT;
BEGIN
    target_year := EXTRACT(YEAR FROM NEW.operation_date)::SMALLINT;
    target_month := EXTRACT(MONTH FROM NEW.operation_date)::SMALLINT;
    INSERT INTO public.accounting_periods(year, month, status)
    VALUES (target_year, target_month, 'OPEN') ON CONFLICT (year, month) DO NOTHING;
    SELECT status INTO period_status FROM public.accounting_periods
     WHERE year = target_year AND month = target_month FOR UPDATE;
    IF period_status <> 'OPEN' THEN
        RAISE EXCEPTION 'Accounting period is closed' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER accounting_entries_open_period_guard
    BEFORE INSERT ON public.accounting_entries
    FOR EACH ROW EXECUTE FUNCTION public.accounting_check_period_open();

CREATE OR REPLACE FUNCTION public.accounting_validate_entry_account_plan() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE entry_plan BIGINT; account_plan BIGINT; account_status VARCHAR(8); postable BOOLEAN;
BEGIN
    IF NEW.account_id IS NULL THEN RETURN NEW; END IF;
    SELECT accounting_plan_id INTO entry_plan FROM public.accounting_entries WHERE id = NEW.entry_id;
    SELECT plan_id, status, is_postable INTO account_plan, account_status, postable
      FROM public.accounting_accounts WHERE id = NEW.account_id;
    IF entry_plan IS NULL OR entry_plan <> account_plan THEN
        RAISE EXCEPTION 'Entry and account must use the same accounting plan' USING ERRCODE = '23514';
    END IF;
    IF account_status <> 'ACTIVE' OR NOT postable THEN
        RAISE EXCEPTION 'Account must be active and postable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER accounting_entry_lines_account_guard
    BEFORE INSERT OR UPDATE OF account_id, entry_id ON public.accounting_entry_lines
    FOR EACH ROW EXECUTE FUNCTION public.accounting_validate_entry_account_plan();

CREATE OR REPLACE FUNCTION public.accounting_reject_configuration_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Accounting configuration audit is append-only' USING ERRCODE = '55000'; END;
$$;
CREATE TRIGGER accounting_configuration_events_immutable
    BEFORE UPDATE OR DELETE ON public.accounting_configuration_events
    FOR EACH ROW EXECUTE FUNCTION public.accounting_reject_configuration_mutation();


-- Bootstrap mirror of 013_seed_pcge_modificado_2019.sql; use only for an empty database
-- PCGE Modificado 2019: códigos y denominaciones del catálogo oficial MEF.
-- Dataset de referencia: data/accounting/pcge_modificado_2019.csv (fuente y línea PDF por cuenta).
-- Las naturalezas normales son valores operativos iniciales inferidos por elemento; requieren validación contable.
DO $$
DECLARE admin_id BIGINT; target_plan_id BIGINT;
BEGIN
  SELECT id INTO admin_id FROM public.users WHERE role='ADMIN' ORDER BY id LIMIT 1;
  IF admin_id IS NULL THEN RAISE EXCEPTION 'An ADMIN user is required to seed the accounting plan'; END IF;
  INSERT INTO public.accounting_plans(code,edition,name,jurisdiction,source_name,source_url,effective_from,status,is_default,created_by)
  VALUES ('PCGE_PE','Modificado 2019','PCGE Perú','PE','Ministerio de Economía y Finanzas del Perú',
    'https://www.mef.gob.pe/contenidos/conta_publ/documentac/PCGE_2019.pdf',DATE '2019-01-01','ACTIVE',FALSE,admin_id)
  ON CONFLICT (code,edition) DO NOTHING;
  SELECT id INTO target_plan_id FROM public.accounting_plans WHERE code='PCGE_PE' AND edition='Modificado 2019';
  UPDATE public.accounting_plans SET is_default=FALSE,updated_at=CURRENT_TIMESTAMP
    WHERE is_default IS TRUE AND status='ACTIVE' AND id<>target_plan_id;
  UPDATE public.accounting_plans SET status='ACTIVE',is_default=TRUE,updated_at=CURRENT_TIMESTAMP WHERE id=target_plan_id;
  INSERT INTO public.accounting_configuration_events(entity_type,entity_id,action,actor_user_id,new_state,reason)
  VALUES ('PLAN',target_plan_id,'SEEDED',admin_id,jsonb_build_object('code','PCGE_PE','edition','Modificado 2019'),'Seed inicial MEF');
END $$;
CREATE TEMP TABLE _pcge_seed(code VARCHAR(40) PRIMARY KEY,name VARCHAR(200) NOT NULL,parent_code VARCHAR(40),
  account_group VARCHAR(40),normal_balance VARCHAR(6),is_postable BOOLEAN NOT NULL) ON COMMIT DROP;
INSERT INTO _pcge_seed(code,name,parent_code,account_group,normal_balance,is_postable) VALUES
    ('10', 'EFECTIVO Y EQUIVALENTES DE EFECTIVO', NULL, 'ASSET', 'DEBIT', FALSE),
    ('11', 'INVERSIONES FINANCIERAS', NULL, 'ASSET', 'DEBIT', FALSE),
    ('12', 'CUENTAS POR COBRAR COMERCIALES – TERCEROS', NULL, 'ASSET', 'DEBIT', FALSE),
    ('13', 'CUENTAS POR COBRAR COMERCIALES – RELACIONADAS', NULL, 'ASSET', 'DEBIT', FALSE),
    ('14', 'CUENTAS POR COBRAR AL PERSONAL, A LOS ACCIONISTAS (SOCIOS) y DIRECTORES', NULL, 'ASSET', 'DEBIT', FALSE),
    ('16', 'CUENTAS POR COBRAR DIVERSAS – TERCEROS', NULL, 'ASSET', 'DEBIT', FALSE),
    ('17', 'CUENTAS POR COBRAR DIVERSAS – RELACIONADAS', NULL, 'ASSET', 'DEBIT', FALSE),
    ('18', 'SERVICIOS Y OTROS CONTRATADOS POR ANTICIPADO', NULL, 'ASSET', 'DEBIT', FALSE),
    ('19', 'ESTIMACIÓN DE CUENTAS DE COBRANZA DUDOSA', NULL, 'ASSET', 'CREDIT', FALSE),
    ('20', 'MERCADERÍAS', NULL, 'ASSET', 'DEBIT', FALSE),
    ('21', 'PRODUCTOS TERMINADOS', NULL, 'ASSET', 'DEBIT', FALSE),
    ('22', 'SUBPRODUCTOS, DESECHOS Y DESPERDICIOS', NULL, 'ASSET', 'DEBIT', FALSE),
    ('23', 'PRODUCTOS EN PROCESO', NULL, 'ASSET', 'DEBIT', FALSE),
    ('24', 'MATERIAS PRIMAS', NULL, 'ASSET', 'DEBIT', FALSE),
    ('25', 'MATERIALES AUXILIARES, SUMINISTROS Y REPUESTOS', NULL, 'ASSET', 'DEBIT', FALSE),
    ('26', 'ENVASES Y EMBALAJES', NULL, 'ASSET', 'DEBIT', FALSE),
    ('27', 'ACTIVOS NO CORRIENTES MANTENIDOS PARA LA VENTA', NULL, 'ASSET', 'DEBIT', FALSE),
    ('28', 'INVENTARIOS POR RECIBIR', NULL, 'ASSET', 'DEBIT', FALSE),
    ('29', 'DESVALORIZACIÓN DE INVENTARIOS', NULL, 'ASSET', 'CREDIT', FALSE),
    ('31', 'PROPIEDADES DE INVERSIÓN', NULL, 'ASSET', 'DEBIT', FALSE),
    ('32', 'ACTIVOS POR DERECHO DE USO', NULL, 'ASSET', 'DEBIT', FALSE),
    ('33', 'PROPIEDAD, PLANTA Y EQUIPO', NULL, 'ASSET', 'DEBIT', FALSE),
    ('34', 'INTANGIBLES', NULL, 'ASSET', 'DEBIT', FALSE),
    ('35', 'ACTIVOS BIOLÓGICOS', NULL, 'ASSET', 'DEBIT', FALSE),
    ('36', 'DESVALORIZACIÓN DE ACTIVO INMOVILIZADO', NULL, 'ASSET', 'CREDIT', FALSE),
    ('37', 'ACTIVO DIFERIDO', NULL, 'ASSET', 'DEBIT', FALSE),
    ('38', 'OTROS ACTIVOS', NULL, 'ASSET', 'DEBIT', FALSE),
    ('39', 'DEPRECIACIÓN y AMORTIZACIÓN ACUMULADOS', NULL, 'ASSET', 'CREDIT', FALSE),
    ('40', 'TRIBUTOS, CONTRAPRESTACIONES Y APORTES AL SISTEMA PÚBLICO DE PENSIONES Y DE SALUD POR PAGAR', NULL, 'LIABILITY', 'CREDIT', FALSE),
    ('41', 'REMUNERACIONES Y PARTICIPACIONES POR PAGAR', NULL, 'LIABILITY', 'CREDIT', FALSE),
    ('42', 'CUENTAS POR PAGAR COMERCIALES TERCEROS', NULL, 'LIABILITY', 'CREDIT', FALSE),
    ('43', 'CUENTAS POR PAGAR COMERCIALES RELACIONADAS', NULL, 'LIABILITY', 'CREDIT', FALSE),
    ('44', 'CUENTAS POR PAGAR A LOS ACCIONISTAS (SOCIOS, PARTÍCIPES) Y DIRECTORES', NULL, 'LIABILITY', 'CREDIT', FALSE),
    ('45', 'OBLIGACIONES FINANCIERAS', NULL, 'LIABILITY', 'CREDIT', FALSE),
    ('51', 'ACCIONES DE INVERSIÓN', NULL, 'EQUITY', 'CREDIT', FALSE),
    ('52', 'CAPITAL ADICIONAL', NULL, 'EQUITY', 'CREDIT', FALSE),
    ('56', 'RESULTADOS NO REALIZADOS', NULL, 'EQUITY', 'CREDIT', FALSE),
    ('57', 'EXCEDENTE DE REVALUACIÓN', NULL, 'EQUITY', 'CREDIT', FALSE),
    ('58', 'RESERVAS', NULL, 'EQUITY', 'CREDIT', FALSE),
    ('59', 'RESULTADOS ACUMULADOS', NULL, 'EQUITY', 'CREDIT', FALSE),
    ('60', 'COMPRAS', NULL, 'EXPENSE', 'DEBIT', FALSE),
    ('61', 'VARIACIÓN DE INVENTARIOS', NULL, 'EXPENSE', 'DEBIT', FALSE),
    ('62', 'GASTOS DE PERSONAL Y DIRECTORES', NULL, 'EXPENSE', 'DEBIT', FALSE),
    ('63', 'GASTOS DE SERVICIOS PRESTADOS POR TERCEROS', NULL, 'EXPENSE', 'DEBIT', FALSE),
    ('64', 'GASTOS POR TRIBUTOS', NULL, 'EXPENSE', 'DEBIT', FALSE),
    ('65', 'OTROS GASTOS DE GESTION', NULL, 'EXPENSE', 'DEBIT', FALSE),
    ('66', 'PÉRDIDA POR MEDICIÓN DE ACTIVOS NO FINANCIEROS AL VALOR RAZONABLE', NULL, 'EXPENSE', 'DEBIT', FALSE),
    ('67', 'GASTOS FINANCIEROS', NULL, 'EXPENSE', 'DEBIT', FALSE),
    ('69', 'COSTO DE VENTAS', NULL, 'EXPENSE', 'DEBIT', FALSE),
    ('73', 'DESCUENTOS, REBAJAS Y BONIFICACIONES OBTENIDOS', NULL, 'INCOME', 'CREDIT', FALSE),
    ('74', 'DESCUENTOS, REBAJAS y BONIFICACIONES CONCEDIDOS', NULL, 'INCOME', 'DEBIT', FALSE),
    ('75', 'OTROS INGRESOS DE GESTIÓN', NULL, 'INCOME', 'CREDIT', FALSE),
    ('76', 'GANANCIA POR MEDICIÓN DE ACTIVOS NO FINANCIEROS AL VALOR RAZONABLE', NULL, 'INCOME', 'CREDIT', FALSE),
    ('77', 'INGRESOS FINANCIEROS', NULL, 'INCOME', 'CREDIT', FALSE),
    ('78', 'CARGAS CUBIERTAS POR PROVISIONES', NULL, 'INCOME', 'CREDIT', FALSE),
    ('79', 'CARGAS IMPUTABLES A CUENTAS DE COSTOS Y GASTOS', NULL, 'INCOME', 'CREDIT', FALSE),
    ('80', 'MARGEN COMERCIAL', NULL, 'RESULT', 'CREDIT', FALSE),
    ('81', 'PRODUCCIÓN DEL EJERCICIO', NULL, 'RESULT', 'CREDIT', FALSE),
    ('82', 'VALOR AGREGADO', NULL, 'RESULT', 'CREDIT', FALSE),
    ('83', 'EXCEDENTE BRUTO (INSUFICIENCIA BRUTA) DE EXPLOTACIÓN', NULL, 'RESULT', 'CREDIT', FALSE),
    ('84', 'RESULTADO DE EXPLOTACIÓN', NULL, 'RESULT', 'CREDIT', FALSE),
    ('85', 'RESULTADO ANTES DE PARTICIPACIONES E IMPUESTOS', NULL, 'RESULT', 'CREDIT', FALSE),
    ('88', 'IMPUESTO A LA RENTA', NULL, 'RESULT', 'DEBIT', FALSE),
    ('89', 'DETERMINACIÓN DEL RESULTADO DEL EJERCICIO', NULL, 'RESULT', NULL, FALSE),
    ('101', 'Caja', '10', 'ASSET', 'DEBIT', TRUE),
    ('102', 'Fondos fijos', '10', 'ASSET', 'DEBIT', TRUE),
    ('103', 'Efectivo y cheques en tránsito', '10', 'ASSET', 'DEBIT', TRUE),
    ('104', 'Cuentas corrientes en instituciones financieras', '10', 'ASSET', 'DEBIT', TRUE),
    ('105', 'Otros equivalentes de efectivo', '10', 'ASSET', 'DEBIT', TRUE),
    ('106', 'Depósitos en instituciones financieras', '10', 'ASSET', 'DEBIT', TRUE),
    ('107', 'Fondos sujetos a restricción', '10', 'ASSET', 'DEBIT', TRUE),
    ('111', 'Inversiones mantenidas para negociación', '11', 'ASSET', 'DEBIT', TRUE),
    ('112', 'Otras inversiones financieras', '11', 'ASSET', 'DEBIT', FALSE),
    ('113', 'Activos financieros – Acuerdo de compra', '11', 'ASSET', 'DEBIT', FALSE),
    ('121', 'Facturas, boletas y otros comprobantes por cobrar', '12', 'ASSET', 'DEBIT', FALSE),
    ('122', 'Anticipos de clientes', '12', 'ASSET', 'DEBIT', TRUE),
    ('123', 'Letras por cobrar', '12', 'ASSET', 'DEBIT', FALSE),
    ('131', 'Facturas, boletas y otros comprobantes por cobrar', '13', 'ASSET', 'DEBIT', FALSE),
    ('132', 'Anticipos recibidos', '13', 'ASSET', 'DEBIT', FALSE),
    ('133', 'Letras por cobrar', '13', 'ASSET', 'DEBIT', FALSE),
    ('141', 'Personal', '14', 'ASSET', 'DEBIT', FALSE),
    ('142', 'Accionistas (o socios)', '14', 'ASSET', 'DEBIT', FALSE),
    ('143', 'Directores', '14', 'ASSET', 'DEBIT', FALSE),
    ('149', 'Diversas', '14', 'ASSET', 'DEBIT', TRUE),
    ('161', 'Préstamos', '16', 'ASSET', 'DEBIT', FALSE),
    ('162', 'Reclamaciones a terceros', '16', 'ASSET', 'DEBIT', FALSE),
    ('163', 'Intereses, regalías y dividendos', '16', 'ASSET', 'DEBIT', FALSE),
    ('164', 'Depósitos otorgados en garantía', '16', 'ASSET', 'DEBIT', FALSE),
    ('165', 'Venta de activo inmovilizado', '16', 'ASSET', 'DEBIT', FALSE),
    ('166', 'Activos por instrumentos financieros', '16', 'ASSET', 'DEBIT', FALSE),
    ('167', 'Tributos por acreditar', '16', 'ASSET', 'DEBIT', FALSE),
    ('169', 'Otras cuentas por cobrar diversas', '16', 'ASSET', 'DEBIT', FALSE),
    ('171', 'Préstamos', '17', 'ASSET', 'DEBIT', TRUE),
    ('173', 'Intereses, regalías y dividendos', '17', 'ASSET', 'DEBIT', TRUE),
    ('174', 'Depósitos otorgados en garantía', '17', 'ASSET', 'DEBIT', TRUE),
    ('175', 'Venta de activo inmovilizado', '17', 'ASSET', 'DEBIT', TRUE),
    ('176', 'Activos por instrumentos financieros', '17', 'ASSET', 'DEBIT', TRUE),
    ('179', 'Otras cuentas por cobrar diversas', '17', 'ASSET', 'DEBIT', TRUE),
    ('181', 'Costos financieros', '18', 'ASSET', 'DEBIT', TRUE),
    ('182', 'Seguros', '18', 'ASSET', 'DEBIT', TRUE),
    ('183', 'Alquileres', '18', 'ASSET', 'DEBIT', TRUE),
    ('184', 'Primas pagadas por opciones', '18', 'ASSET', 'DEBIT', TRUE),
    ('185', 'Mantenimiento de activos inmovilizados', '18', 'ASSET', 'DEBIT', TRUE),
    ('189', 'Otros gastos contratados por anticipado', '18', 'ASSET', 'DEBIT', TRUE),
    ('191', 'Cuentas por cobrar comerciales – Terceros', '19', 'ASSET', 'CREDIT', TRUE),
    ('192', 'Cuentas por cobrar comerciales – Relacionadas', '19', 'ASSET', 'CREDIT', TRUE),
    ('193', 'Cuentas por cobrar al personal, a los accionistas (socios) y directores', '19', 'ASSET', 'CREDIT', FALSE),
    ('194', 'Cuentas por cobrar diversas – Terceros', '19', 'ASSET', 'CREDIT', FALSE),
    ('195', 'Cuentas por cobrar diversas – Relacionadas', '19', 'ASSET', 'CREDIT', FALSE),
    ('201', 'Mercaderías', '20', 'ASSET', 'DEBIT', FALSE),
    ('211', 'Productos terminados', '21', 'ASSET', 'DEBIT', FALSE),
    ('215', 'Inventario de servicios terminados', '21', 'ASSET', 'DEBIT', FALSE),
    ('221', 'Subproductos', '22', 'ASSET', 'DEBIT', TRUE),
    ('222', 'Desechos y desperdicios', '22', 'ASSET', 'DEBIT', TRUE),
    ('231', 'Productos en proceso', '23', 'ASSET', 'DEBIT', FALSE),
    ('241', 'Materias primas', '24', 'ASSET', 'DEBIT', FALSE),
    ('251', 'Materiales auxiliares', '25', 'ASSET', 'DEBIT', TRUE),
    ('252', 'Suministros', '25', 'ASSET', 'DEBIT', FALSE),
    ('253', 'Repuestos', '25', 'ASSET', 'DEBIT', TRUE),
    ('261', 'Envases', '26', 'ASSET', 'DEBIT', TRUE),
    ('262', 'Embalajes', '26', 'ASSET', 'DEBIT', TRUE),
    ('271', 'Propiedades de inversión', '27', 'ASSET', 'DEBIT', FALSE),
    ('272', 'Propiedad, planta y equipo', '27', 'ASSET', 'DEBIT', FALSE),
    ('273', 'Intangibles', '27', 'ASSET', 'DEBIT', FALSE),
    ('274', 'Activos biológicos', '27', 'ASSET', 'DEBIT', FALSE),
    ('275', 'Depreciación acumulada – Propiedades de inversión', '27', 'ASSET', 'DEBIT', FALSE),
    ('276', 'Depreciación acumulada – Propiedad, planta y equipo', '27', 'ASSET', 'DEBIT', FALSE),
    ('277', 'Amortización acumulada – Intangibles', '27', 'ASSET', 'DEBIT', FALSE),
    ('278', 'Depreciación acumulada – Activos biológicos', '27', 'ASSET', 'DEBIT', FALSE),
    ('279', 'Desvalorización acumulada', '27', 'ASSET', 'DEBIT', FALSE),
    ('281', 'Mercaderías', '28', 'ASSET', 'DEBIT', TRUE),
    ('284', 'Materias primas', '28', 'ASSET', 'DEBIT', TRUE),
    ('285', 'Materiales auxiliares, suministros y repuestos', '28', 'ASSET', 'DEBIT', TRUE),
    ('286', 'Envases y embalajes', '28', 'ASSET', 'DEBIT', TRUE),
    ('291', 'Mercaderías', '29', 'ASSET', 'CREDIT', FALSE),
    ('292', 'Productos terminados', '29', 'ASSET', 'CREDIT', FALSE),
    ('293', 'Subproductos, desechos y desperdicios', '29', 'ASSET', 'CREDIT', FALSE),
    ('294', 'Productos en proceso', '29', 'ASSET', 'CREDIT', FALSE),
    ('295', 'Materias primas', '29', 'ASSET', 'CREDIT', FALSE),
    ('296', 'Materiales auxiliares, suministros y repuestos', '29', 'ASSET', 'CREDIT', FALSE),
    ('297', 'Envases y embalajes', '29', 'ASSET', 'CREDIT', FALSE),
    ('298', 'Existencias por recibir', '29', 'ASSET', 'CREDIT', FALSE),
    ('301', 'Inversiones a ser mantenidas hasta el vencimiento', NULL, 'ASSET', 'DEBIT', TRUE),
    ('302', 'Instrumentos financieros representativos de derecho patrimonial', NULL, 'ASSET', 'DEBIT', TRUE),
    ('303', 'Certificados de participación en fondos - Cuotas', NULL, 'ASSET', 'DEBIT', TRUE),
    ('304', 'Participaciones en acuerdos conjuntos', NULL, 'ASSET', 'DEBIT', TRUE),
    ('308', 'Inversiones mobiliarias – Acuerdos de compra', NULL, 'ASSET', 'DEBIT', FALSE),
    ('311', 'Terrenos', '31', 'ASSET', 'DEBIT', FALSE),
    ('312', 'Edificaciones', '31', 'ASSET', 'DEBIT', FALSE),
    ('313', 'Construcciones en curso', '31', 'ASSET', 'DEBIT', FALSE),
    ('321', 'Propiedades de inversión - Arrendamiento financiero', '32', 'ASSET', 'DEBIT', FALSE),
    ('322', 'Propiedad, planta y equipo - Arrendamiento financiero', '32', 'ASSET', 'DEBIT', FALSE),
    ('323', 'Propiedad, planta y equipo - Arrendamiento operativo', '32', 'ASSET', 'DEBIT', FALSE),
    ('330', 'Planta productora', '33', 'ASSET', 'DEBIT', FALSE),
    ('331', 'Terrenos', '33', 'ASSET', 'DEBIT', FALSE),
    ('332', 'Edificaciones', '33', 'ASSET', 'DEBIT', FALSE),
    ('333', 'Maquinaria y equipo de explotación', '33', 'ASSET', 'DEBIT', FALSE),
    ('334', 'Unidades de transporte', '33', 'ASSET', 'DEBIT', FALSE),
    ('335', 'Muebles y enseres', '33', 'ASSET', 'DEBIT', FALSE),
    ('336', 'Equipos diversos', '33', 'ASSET', 'DEBIT', TRUE),
    ('337', 'Herramientas y unidades de reemplazo', '33', 'ASSET', 'DEBIT', TRUE),
    ('338', 'Unidades por recibir', '33', 'ASSET', 'DEBIT', TRUE),
    ('339', 'Obras en curso', '33', 'ASSET', 'DEBIT', TRUE),
    ('342', 'Patentes y propiedad industrial', '34', 'ASSET', 'DEBIT', TRUE),
    ('343', 'Programas de computadora (software)', '34', 'ASSET', 'DEBIT', TRUE),
    ('344', 'Costos de exploración y desarrollo', '34', 'ASSET', 'DEBIT', TRUE),
    ('345', 'Fórmulas, diseños y prototipos', '34', 'ASSET', 'DEBIT', TRUE),
    ('347', 'Plusvalía mercantil', '34', 'ASSET', 'DEBIT', TRUE),
    ('349', 'Otros activos intangibles', '34', 'ASSET', 'DEBIT', TRUE),
    ('352', 'Activos biológicos en desarrollo', '35', 'ASSET', 'DEBIT', FALSE),
    ('361', 'Desvalorización de propiedades de inversión', '36', 'ASSET', 'CREDIT', FALSE),
    ('362', 'Desvalorización de propiedades de inversión - Arrendamiento financiero', '36', 'ASSET', 'CREDIT', FALSE),
    ('363', 'Desvalorización de propiedad, planta y equipo - Arrendamiento financiero', '36', 'ASSET', 'CREDIT', FALSE),
    ('364', 'Desvalorización de propiedad, planta y equipo', '36', 'ASSET', 'CREDIT', FALSE),
    ('365', 'Desvalorización de intangibles', '36', 'ASSET', 'CREDIT', FALSE),
    ('366', 'Desvalorización de activos biológicos', '36', 'ASSET', 'CREDIT', FALSE),
    ('367', 'Desvalorización de inversiones mobiliarias', '36', 'ASSET', 'CREDIT', FALSE),
    ('371', 'Impuesto a la renta diferido', '37', 'ASSET', 'DEBIT', FALSE),
    ('372', 'Participaciones de los trabajadores diferidas', '37', 'ASSET', 'DEBIT', FALSE),
    ('373', 'Intereses diferidos', '37', 'ASSET', 'DEBIT', FALSE),
    ('381', 'Bienes de arte y cultura', '38', 'ASSET', 'DEBIT', FALSE),
    ('382', 'Diversos', '38', 'ASSET', 'DEBIT', FALSE),
    ('391', 'Depreciación acumulada propiedades de inversión', '39', 'ASSET', 'CREDIT', FALSE),
    ('392', 'Depreciación acumulada propiedades de inversión - Arrendamiento financiero', '39', 'ASSET', 'CREDIT', FALSE),
    ('393', 'Depreciación acumulada propiedad, planta y equipo - Arrendamiento financiero', '39', 'ASSET', 'CREDIT', FALSE),
    ('394', 'Depreciación acumulada - Arrendamiento operativo', '39', 'ASSET', 'CREDIT', TRUE),
    ('395', 'Depreciación acumulada de propiedad, planta y equipo', '39', 'ASSET', 'CREDIT', TRUE),
    ('396', 'Amortización acumulada', '39', 'ASSET', 'CREDIT', FALSE),
    ('398', 'Depreciación acumulada - Activos biológicos en producción', '39', 'ASSET', 'CREDIT', FALSE),
    ('401', 'Gobierno nacional', '40', 'LIABILITY', 'CREDIT', FALSE),
    ('402', 'Certificados tributarios', '40', 'LIABILITY', 'CREDIT', TRUE),
    ('403', 'Instituciones públicas', '40', 'LIABILITY', 'CREDIT', TRUE),
    ('405', 'Gobiernos regionales', '40', 'LIABILITY', 'CREDIT', TRUE),
    ('406', 'Gobiernos locales', '40', 'LIABILITY', 'CREDIT', TRUE),
    ('409', 'Otros costos administrativos e intereses', '40', 'LIABILITY', 'CREDIT', TRUE),
    ('421', 'Facturas, boletas y otros comprobantes por pagar', '42', 'LIABILITY', 'CREDIT', TRUE),
    ('422', 'Anticipos a proveedores', '42', 'LIABILITY', 'CREDIT', TRUE),
    ('423', 'Letras por pagar', '42', 'LIABILITY', 'CREDIT', TRUE),
    ('424', 'Honorarios por pagar', '42', 'LIABILITY', 'CREDIT', TRUE),
    ('431', 'Facturas, boletas y otros comprobantes por pagar', '43', 'LIABILITY', 'CREDIT', TRUE),
    ('432', 'Anticipos otorgados', '43', 'LIABILITY', 'CREDIT', TRUE),
    ('433', 'Letras por pagar', '43', 'LIABILITY', 'CREDIT', TRUE),
    ('434', 'Honorarios por pagar', '43', 'LIABILITY', 'CREDIT', TRUE),
    ('441', 'Accionistas ( socios, partícipes)', '44', 'LIABILITY', 'CREDIT', TRUE),
    ('442', 'Directores', '44', 'LIABILITY', 'CREDIT', TRUE),
    ('451', 'Préstamos de instituciones financieras y otras entidades', '45', 'LIABILITY', 'CREDIT', TRUE),
    ('452', 'Contratos de arrendamiento financiero', '45', 'LIABILITY', 'CREDIT', TRUE),
    ('453', 'Obligaciones emitidas', '45', 'LIABILITY', 'CREDIT', TRUE),
    ('454', 'Otros Instrumentos financieros por pagar', '45', 'LIABILITY', 'CREDIT', TRUE),
    ('475', 'Dividendos', NULL, 'LIABILITY', 'CREDIT', TRUE),
    ('476', 'Depósitos recibidos en garantía', NULL, 'LIABILITY', 'CREDIT', TRUE),
    ('477', 'Pasivo por compra de activo inmovilizado', NULL, 'LIABILITY', 'CREDIT', TRUE),
    ('479', 'Otras cuentas por pagar diversas', NULL, 'LIABILITY', 'CREDIT', TRUE),
    ('481', 'Provisión para litigios', NULL, 'LIABILITY', 'CREDIT', TRUE),
    ('482', 'Provisión por desmantelamiento, retiro o rehabilitación del inmovilizado', NULL, 'LIABILITY', 'CREDIT', TRUE),
    ('483', 'Provisión para reestructuraciones', NULL, 'LIABILITY', 'CREDIT', TRUE),
    ('484', 'Provisión para protección y remediación del medio ambiente', NULL, 'LIABILITY', 'CREDIT', TRUE),
    ('485', 'Provisión para gastos de responsabilidad social', NULL, 'LIABILITY', 'CREDIT', TRUE),
    ('486', 'Provisión para garantías', NULL, 'LIABILITY', 'CREDIT', TRUE),
    ('487', 'Provisión por activos por derecho de uso', NULL, 'LIABILITY', 'CREDIT', TRUE),
    ('489', 'Otras provisiones', NULL, 'LIABILITY', 'CREDIT', TRUE),
    ('491', 'Impuesto a la renta diferido', NULL, 'LIABILITY', 'CREDIT', TRUE),
    ('492', 'Participaciones de los trabajadores diferidas', NULL, 'LIABILITY', 'CREDIT', TRUE),
    ('493', 'Intereses diferidos', NULL, 'LIABILITY', 'CREDIT', TRUE),
    ('494', 'Ganancia en venta con arrendamiento financiero paralelo', NULL, 'LIABILITY', 'CREDIT', TRUE),
    ('495', 'Subsidios recibidos diferidos', NULL, 'LIABILITY', 'CREDIT', TRUE),
    ('496', 'Ingresos diferidos', NULL, 'LIABILITY', 'CREDIT', TRUE),
    ('497', 'Costos diferidos', NULL, 'LIABILITY', 'CREDIT', TRUE),
    ('501', 'Capital social', NULL, 'EQUITY', 'CREDIT', TRUE),
    ('502', 'Acciones en tesorería', NULL, 'EQUITY', 'CREDIT', TRUE),
    ('511', 'Acciones de inversión', '51', 'EQUITY', 'CREDIT', TRUE),
    ('512', 'Acciones de inversión en tesorería', '51', 'EQUITY', 'CREDIT', TRUE),
    ('521', 'Primas (descuento) de acciones', '52', 'EQUITY', 'CREDIT', TRUE),
    ('522', 'Capitalizaciones en trámite', '52', 'EQUITY', 'CREDIT', TRUE),
    ('523', 'Reducciones de capital pendientes de formalización', '52', 'EQUITY', 'CREDIT', TRUE),
    ('561', 'Diferencia en cambio de inversiones permanentes en entidades extranjeras', '56', 'EQUITY', 'CREDIT', TRUE),
    ('562', 'Instrumentos financieros – Coberturas', '56', 'EQUITY', 'CREDIT', TRUE),
    ('571', 'Excedente de revaluación', '57', 'EQUITY', 'CREDIT', TRUE),
    ('572', 'Excedente de revaluación – Acciones liberadas recibidas', '57', 'EQUITY', 'CREDIT', TRUE),
    ('573', 'Participación en excedente de revaluación – Inversiones en entidades relacionadas', '57', 'EQUITY', 'CREDIT', TRUE),
    ('581', 'Reinv ersión', '58', 'EQUITY', 'CREDIT', TRUE),
    ('582', 'Legal', '58', 'EQUITY', 'CREDIT', TRUE),
    ('583', 'Contractuales', '58', 'EQUITY', 'CREDIT', TRUE),
    ('584', 'Estatutarias', '58', 'EQUITY', 'CREDIT', TRUE),
    ('585', 'Facultativas', '58', 'EQUITY', 'CREDIT', TRUE),
    ('589', 'Otras reservas', '58', 'EQUITY', 'CREDIT', TRUE),
    ('591', 'Utilidades no distribuidas', '59', 'EQUITY', 'CREDIT', TRUE),
    ('592', 'Pérdidas acumuladas', '59', 'EQUITY', 'CREDIT', TRUE),
    ('611', 'Mercaderías', '61', 'EXPENSE', 'DEBIT', FALSE),
    ('612', 'Materias primas', '61', 'EXPENSE', 'DEBIT', FALSE),
    ('613', 'Materiales auxiliares, suministros y repuestos', '61', 'EXPENSE', 'DEBIT', FALSE),
    ('614', 'Envases y embalajes', '61', 'EXPENSE', 'DEBIT', FALSE),
    ('621', 'Remuneraciones', '62', 'EXPENSE', 'DEBIT', FALSE),
    ('622', 'Otras remuneraciones', '62', 'EXPENSE', 'DEBIT', TRUE),
    ('623', 'Indemnizaciones al personal', '62', 'EXPENSE', 'DEBIT', TRUE),
    ('624', 'Capacitación', '62', 'EXPENSE', 'DEBIT', TRUE),
    ('625', 'Atención al personal', '62', 'EXPENSE', 'DEBIT', TRUE),
    ('627', 'Seguridad, previsión social y otras contribuciones', '62', 'EXPENSE', 'DEBIT', FALSE),
    ('628', 'Retribuciones al directorio', '62', 'EXPENSE', 'DEBIT', TRUE),
    ('629', 'Beneficios sociales de los trabajadores', '62', 'EXPENSE', 'DEBIT', FALSE),
    ('631', 'Transporte, correos y gastos de viaje', '63', 'EXPENSE', 'DEBIT', TRUE),
    ('632', 'Asesoría y consultoría', '63', 'EXPENSE', 'DEBIT', TRUE),
    ('633', 'Producción encargada a terceros', '63', 'EXPENSE', 'DEBIT', TRUE),
    ('634', 'Mantenimiento y reparaciones', '63', 'EXPENSE', 'DEBIT', TRUE),
    ('635', 'Alquileres', '63', 'EXPENSE', 'DEBIT', TRUE),
    ('636', 'Servicios básicos', '63', 'EXPENSE', 'DEBIT', FALSE),
    ('637', 'Publicidad, publicaciones, relaciones públicas', '63', 'EXPENSE', 'DEBIT', FALSE),
    ('638', 'Servicios de contratistas', '63', 'EXPENSE', 'DEBIT', TRUE),
    ('639', 'Otros servicios prestados por terceros', '63', 'EXPENSE', 'DEBIT', FALSE),
    ('641', 'Gobierno nacional', '64', 'EXPENSE', 'DEBIT', FALSE),
    ('642', 'Gobierno regional', '64', 'EXPENSE', 'DEBIT', TRUE),
    ('643', 'Gobierno local', '64', 'EXPENSE', 'DEBIT', FALSE),
    ('644', 'Otros gastos por tributos', '64', 'EXPENSE', 'DEBIT', FALSE),
    ('645', 'Gastos en deuda tributaria', '64', 'EXPENSE', 'DEBIT', FALSE),
    ('651', 'Seguros', '65', 'EXPENSE', 'DEBIT', TRUE),
    ('652', 'Regalías', '65', 'EXPENSE', 'DEBIT', TRUE),
    ('653', 'Suscripciones', '65', 'EXPENSE', 'DEBIT', TRUE),
    ('654', 'Licencias y derechos de vigencia', '65', 'EXPENSE', 'DEBIT', TRUE),
    ('655', 'Costo neto de enajenación de activos inmovilizados y operaciones discontinuadas', '65', 'EXPENSE', 'DEBIT', FALSE),
    ('656', 'Suministros', '65', 'EXPENSE', 'DEBIT', TRUE),
    ('658', 'Gestión medioambiental', '65', 'EXPENSE', 'DEBIT', TRUE),
    ('659', 'Otros gastos de gestión', '65', 'EXPENSE', 'DEBIT', FALSE),
    ('661', 'Activo realizable', '66', 'EXPENSE', 'DEBIT', FALSE),
    ('662', 'Activo inmovilizado', '66', 'EXPENSE', 'DEBIT', FALSE),
    ('671', 'Gastos en operaciones de endeudamiento y otros', '67', 'EXPENSE', 'DEBIT', FALSE),
    ('672', 'Pérdida por instrumentos financieros derivados', '67', 'EXPENSE', 'DEBIT', TRUE),
    ('673', 'Intereses por préstamos y otras obligaciones', '67', 'EXPENSE', 'DEBIT', FALSE),
    ('674', 'Gastos en operaciones de factoraje (factoring)', '67', 'EXPENSE', 'DEBIT', FALSE),
    ('675', 'Descuentos concedidos por pronto pago', '67', 'EXPENSE', 'DEBIT', TRUE),
    ('676', 'Diferencia de cambio', '67', 'EXPENSE', 'DEBIT', TRUE),
    ('677', 'Pérdida por medición de activos y pasivos financieros al valor razonable', '67', 'EXPENSE', 'DEBIT', FALSE),
    ('678', 'Participación en resultados de entidades relacionadas', '67', 'EXPENSE', 'DEBIT', FALSE),
    ('679', 'Otros gastos financieros', '67', 'EXPENSE', 'DEBIT', FALSE),
    ('681', 'Depreciación de propiedades de inversión', NULL, 'EXPENSE', 'DEBIT', FALSE),
    ('682', 'Depreciación de activos por derecho de uso - arrendamiento financiero', NULL, 'EXPENSE', 'DEBIT', FALSE),
    ('683', 'Depreciación de activos por derecho de uso - arrendamiento operativo', NULL, 'EXPENSE', 'DEBIT', FALSE),
    ('684', 'Depreciación de propiedad, planta y equipo', NULL, 'EXPENSE', 'DEBIT', FALSE),
    ('685', 'Depreciación de activos biológicos en producción', NULL, 'EXPENSE', 'DEBIT', FALSE),
    ('686', 'Amortización de intangibles', NULL, 'EXPENSE', 'DEBIT', FALSE),
    ('687', 'Valuación de activos', NULL, 'EXPENSE', 'DEBIT', FALSE),
    ('688', 'Deterioro del valor de los activos', NULL, 'EXPENSE', 'DEBIT', FALSE),
    ('689', 'Provisiones', NULL, 'EXPENSE', 'DEBIT', FALSE),
    ('691', 'Mercaderías', '69', 'EXPENSE', 'DEBIT', FALSE),
    ('692', 'Productos terminados', '69', 'EXPENSE', 'DEBIT', FALSE),
    ('693', 'Servicios terminados', '69', 'EXPENSE', 'DEBIT', FALSE),
    ('694', 'Subproductos, desechos y desperdicios', '69', 'EXPENSE', 'DEBIT', FALSE),
    ('695', 'Gastos por desvalorización de inventarios al costo', '69', 'EXPENSE', 'DEBIT', FALSE),
    ('701', 'Mercaderías', NULL, 'INCOME', 'CREDIT', FALSE),
    ('702', 'Productos terminados', NULL, 'INCOME', 'CREDIT', FALSE),
    ('703', 'Servicios terminados', NULL, 'INCOME', 'CREDIT', FALSE),
    ('704', 'Subproductos, desechos y desperdicios', NULL, 'INCOME', 'CREDIT', FALSE),
    ('709', 'Devoluciones sobre ventas', NULL, 'INCOME', 'CREDIT', FALSE),
    ('711', 'Variación de productos terminados', NULL, 'INCOME', 'CREDIT', TRUE),
    ('712', 'Variación de subproductos, desechos y desperdicios', NULL, 'INCOME', 'CREDIT', TRUE),
    ('713', 'Variación de productos en proceso', NULL, 'INCOME', 'CREDIT', TRUE),
    ('714', 'Variación de envases y embalajes', NULL, 'INCOME', 'CREDIT', TRUE),
    ('715', 'Variación de inventarios de servicios', NULL, 'INCOME', 'CREDIT', TRUE),
    ('721', 'Propiedades de inversión', NULL, 'INCOME', 'CREDIT', TRUE),
    ('722', 'Propiedad, planta y equipo', NULL, 'INCOME', 'CREDIT', TRUE),
    ('723', 'Intangibles', NULL, 'INCOME', 'CREDIT', TRUE),
    ('724', 'Activos biológicos', NULL, 'INCOME', 'CREDIT', TRUE),
    ('725', 'Costos de financiación capitalizados', NULL, 'INCOME', 'CREDIT', FALSE),
    ('731', 'Descuentos, rebajas y bonificaciones obtenidos', '73', 'INCOME', 'CREDIT', TRUE),
    ('741', 'Descuentos, rebajas y bonificaciones concedidos', '74', 'INCOME', 'DEBIT', TRUE),
    ('751', 'Servicios en beneficio del personal', '75', 'INCOME', 'CREDIT', TRUE),
    ('752', 'Comisiones y corretajes', '75', 'INCOME', 'CREDIT', TRUE),
    ('753', 'Regalías', '75', 'INCOME', 'CREDIT', TRUE),
    ('754', 'Alquileres', '75', 'INCOME', 'CREDIT', TRUE),
    ('755', 'Recuperación de cuentas de valuación', '75', 'INCOME', 'CREDIT', TRUE),
    ('756', 'Enajenación de activos inmovilizados', '75', 'INCOME', 'CREDIT', TRUE),
    ('757', 'Recuperación de deterioro de cuentas de activos inmovilizados', '75', 'INCOME', 'CREDIT', TRUE),
    ('759', 'Otros ingresos de gestión', '75', 'INCOME', 'CREDIT', TRUE),
    ('761', 'Activo realizable', '76', 'INCOME', 'CREDIT', TRUE),
    ('762', 'Activo inmovilizado', '76', 'INCOME', 'CREDIT', TRUE),
    ('771', 'Ganancia por instrumento financiero derivado', '77', 'INCOME', 'CREDIT', TRUE),
    ('772', 'Rendimientos ganados', '77', 'INCOME', 'CREDIT', TRUE),
    ('773', 'Dividendos', '77', 'INCOME', 'CREDIT', TRUE),
    ('774', 'Ingresos en operaciones de factoraje (factoring)', '77', 'INCOME', 'CREDIT', TRUE),
    ('775', 'Descuentos obtenidos por pronto pago', '77', 'INCOME', 'CREDIT', TRUE),
    ('776', 'Diferencia en cambio', '77', 'INCOME', 'CREDIT', TRUE),
    ('777', 'Ganancia por medición de activos y pasivos financieros al valor razonable', '77', 'INCOME', 'CREDIT', TRUE),
    ('778', 'Participación en resultados de entidades relacionadas', '77', 'INCOME', 'CREDIT', TRUE),
    ('779', 'Otros ingresos financieros', '77', 'INCOME', 'CREDIT', TRUE),
    ('781', 'Cargas cubiertas por provisiones', '78', 'INCOME', 'CREDIT', TRUE),
    ('791', 'Cargas imputables a cuentas de costos y gastos', '79', 'INCOME', 'CREDIT', TRUE),
    ('792', 'Gastos financieros imputables a cuentas de inventarios', '79', 'INCOME', 'CREDIT', TRUE),
    ('801', 'Margen comercial', '80', 'RESULT', 'CREDIT', TRUE),
    ('811', 'Producción de bienes', '81', 'RESULT', 'CREDIT', TRUE),
    ('812', 'Producción de servicios', '81', 'RESULT', 'CREDIT', TRUE),
    ('813', 'Producción de activo inmovilizado', '81', 'RESULT', 'CREDIT', TRUE),
    ('821', 'Valor agregado', '82', 'RESULT', 'CREDIT', TRUE),
    ('831', 'Excedente bruto (insuficiencia bruta) de explotación', '83', 'RESULT', 'CREDIT', TRUE),
    ('841', 'Resultado de explotación', '84', 'RESULT', 'CREDIT', TRUE),
    ('851', 'Resultado antes del impuesto a las ganancias', '85', 'RESULT', 'CREDIT', TRUE),
    ('881', 'Impuesto a las ganancias – Corriente', '88', 'RESULT', 'DEBIT', TRUE),
    ('882', 'Impuesto a las ganancias – Diferido', '88', 'RESULT', 'DEBIT', TRUE),
    ('891', 'Utilidad', '89', 'RESULT', NULL, FALSE),
    ('892', 'Pérdida', '89', 'RESULT', NULL, FALSE),
    ('1121', 'Otras inversiones financieras', '112', 'ASSET', 'DEBIT', FALSE),
    ('1131', 'Inversiones mantenidas para negociación – Acuerdo de compra', '113', 'ASSET', 'DEBIT', FALSE),
    ('1132', 'Otras inversiones financieras', '113', 'ASSET', 'DEBIT', FALSE),
    ('1211', 'No emitidas', '121', 'ASSET', 'DEBIT', TRUE),
    ('1212', 'Emitidas en cartera', '121', 'ASSET', 'DEBIT', TRUE),
    ('1213', 'En cobranza', '121', 'ASSET', 'DEBIT', TRUE),
    ('1214', 'En descuento', '121', 'ASSET', 'DEBIT', TRUE),
    ('1232', 'En cartera', '123', 'ASSET', 'DEBIT', TRUE),
    ('1233', 'En cobranza', '123', 'ASSET', 'DEBIT', TRUE),
    ('1234', 'En descuento', '123', 'ASSET', 'DEBIT', TRUE),
    ('1311', 'No emitidas', '131', 'ASSET', 'DEBIT', TRUE),
    ('1312', 'En cartera', '131', 'ASSET', 'DEBIT', TRUE),
    ('1313', 'En cobranza', '131', 'ASSET', 'DEBIT', TRUE),
    ('1314', 'En descuento', '131', 'ASSET', 'DEBIT', TRUE),
    ('1321', 'Anticipos recibidos', '132', 'ASSET', 'DEBIT', TRUE),
    ('1331', 'En cartera', '133', 'ASSET', 'DEBIT', TRUE),
    ('1332', 'En cobranza', '133', 'ASSET', 'DEBIT', TRUE),
    ('1333', 'En descuento', '133', 'ASSET', 'DEBIT', TRUE),
    ('1411', 'Préstamos', '141', 'ASSET', 'DEBIT', TRUE),
    ('1412', 'Adelanto de remuneraciones', '141', 'ASSET', 'DEBIT', TRUE),
    ('1413', 'Entregas a rendir cuenta', '141', 'ASSET', 'DEBIT', TRUE),
    ('1419', 'Otras cuentas por cobrar al personal', '141', 'ASSET', 'DEBIT', TRUE),
    ('1421', 'Suscripciones por cobrar a socios o accionistas', '142', 'ASSET', 'DEBIT', TRUE),
    ('1422', 'Préstamos', '142', 'ASSET', 'DEBIT', TRUE),
    ('1431', 'Préstamos', '143', 'ASSET', 'DEBIT', TRUE),
    ('1432', 'Adelanto de dietas', '143', 'ASSET', 'DEBIT', TRUE),
    ('1433', 'Entregas a rendir cuenta', '143', 'ASSET', 'DEBIT', TRUE),
    ('1611', 'Con garantía', '161', 'ASSET', 'DEBIT', TRUE),
    ('1612', 'Sin garantía', '161', 'ASSET', 'DEBIT', TRUE),
    ('1621', 'Compañías aseguradoras', '162', 'ASSET', 'DEBIT', TRUE),
    ('1622', 'Transportadoras', '162', 'ASSET', 'DEBIT', TRUE),
    ('1623', 'Servicios públicos', '162', 'ASSET', 'DEBIT', TRUE),
    ('1624', 'Tributos', '162', 'ASSET', 'DEBIT', TRUE),
    ('1629', 'Otras', '162', 'ASSET', 'DEBIT', TRUE),
    ('1631', 'Intereses', '163', 'ASSET', 'DEBIT', TRUE),
    ('1632', 'Regalías', '163', 'ASSET', 'DEBIT', TRUE),
    ('1633', 'Dividendos', '163', 'ASSET', 'DEBIT', TRUE),
    ('1641', 'Préstamos de instituciones financieras', '164', 'ASSET', 'DEBIT', TRUE),
    ('1642', 'Préstamos de instituciones no financieras', '164', 'ASSET', 'DEBIT', TRUE),
    ('1643', 'Depósitos en garantía por alquileres', '164', 'ASSET', 'DEBIT', TRUE),
    ('1649', 'Otros depósitos en garantía', '164', 'ASSET', 'DEBIT', TRUE),
    ('1651', 'Inversión mobiliaria', '165', 'ASSET', 'DEBIT', TRUE),
    ('1652', 'Propiedades de inversión', '165', 'ASSET', 'DEBIT', TRUE),
    ('1653', 'Propiedad, planta y equipo', '165', 'ASSET', 'DEBIT', TRUE),
    ('1654', 'Intangibles', '165', 'ASSET', 'DEBIT', TRUE),
    ('1655', 'Activos biológicos', '165', 'ASSET', 'DEBIT', TRUE),
    ('1659', 'Otros activos inmovilizados', '165', 'ASSET', 'DEBIT', TRUE),
    ('1661', 'Instrumentos financieros primarios', '166', 'ASSET', 'DEBIT', FALSE),
    ('1662', 'Instrumentos financieros derivados', '166', 'ASSET', 'DEBIT', FALSE),
    ('1671', 'Pagos a cuenta del impuesto a la renta', '167', 'ASSET', 'DEBIT', TRUE),
    ('1672', 'Pagos a cuenta de ITAN', '167', 'ASSET', 'DEBIT', TRUE),
    ('1673', 'IGV por acreditar en compras', '167', 'ASSET', 'DEBIT', TRUE),
    ('1674', 'IGV por acreditar no domiciliados', '167', 'ASSET', 'DEBIT', TRUE),
    ('1675', 'Obras por impuestos', '167', 'ASSET', 'DEBIT', TRUE),
    ('1691', 'Entregas a rendir cuenta a terceros', '169', 'ASSET', 'DEBIT', TRUE),
    ('1699', 'Otras cuentas por cobrar diversas', '169', 'ASSET', 'DEBIT', TRUE),
    ('1931', 'Personal', '193', 'ASSET', 'CREDIT', TRUE),
    ('1932', 'Accionistas (o socios)', '193', 'ASSET', 'CREDIT', TRUE),
    ('1933', 'Directores', '193', 'ASSET', 'CREDIT', TRUE),
    ('1939', 'Diversas', '193', 'ASSET', 'CREDIT', TRUE),
    ('1941', 'Préstamos', '194', 'ASSET', 'CREDIT', TRUE),
    ('1942', 'Reclamaciones a terceros', '194', 'ASSET', 'CREDIT', TRUE),
    ('1943', 'Intereses, regalías y dividendos', '194', 'ASSET', 'CREDIT', TRUE),
    ('1944', 'Depósitos otorgados en garantía', '194', 'ASSET', 'CREDIT', TRUE),
    ('1945', 'Venta de activo inmovilizado', '194', 'ASSET', 'CREDIT', TRUE),
    ('1946', 'Activos por instrumentos financieros', '194', 'ASSET', 'CREDIT', TRUE),
    ('1949', 'Otras cuentas por cobrar diversas', '194', 'ASSET', 'CREDIT', TRUE),
    ('1951', 'Préstamos', '195', 'ASSET', 'CREDIT', TRUE),
    ('1953', 'Intereses, regalías y dividendos', '195', 'ASSET', 'CREDIT', TRUE),
    ('1954', 'Depósitos otorgados en garantía', '195', 'ASSET', 'CREDIT', TRUE),
    ('1955', 'Venta de activo inmovilizado', '195', 'ASSET', 'CREDIT', TRUE),
    ('1956', 'Activos por instrumentos financieros', '195', 'ASSET', 'CREDIT', TRUE),
    ('1959', 'Otras cuentas por cobrar diversas', '195', 'ASSET', 'CREDIT', TRUE),
    ('2011', 'Mercaderías', '201', 'ASSET', 'DEBIT', FALSE),
    ('2111', 'Productos terminados', '211', 'ASSET', 'DEBIT', FALSE),
    ('2151', 'Servicios terminados', '215', 'ASSET', 'DEBIT', FALSE),
    ('2311', 'Productos en proceso', '231', 'ASSET', 'DEBIT', TRUE),
    ('2351', 'Servicios en proceso', '23', 'ASSET', 'DEBIT', FALSE),
    ('2411', 'Materias primas', '241', 'ASSET', 'DEBIT', FALSE),
    ('2521', 'Combustibles', '252', 'ASSET', 'DEBIT', TRUE),
    ('2522', 'Lubricantes', '252', 'ASSET', 'DEBIT', TRUE),
    ('2523', 'Energía', '252', 'ASSET', 'DEBIT', TRUE),
    ('2524', 'Otros suministros', '252', 'ASSET', 'DEBIT', TRUE),
    ('2711', 'Terrenos', '271', 'ASSET', 'DEBIT', FALSE),
    ('2712', 'Edificaciones', '271', 'ASSET', 'DEBIT', FALSE),
    ('2720', 'Planta productora en producción', '272', 'ASSET', 'DEBIT', FALSE),
    ('2721', 'Planta productora en desarrollo', '272', 'ASSET', 'DEBIT', FALSE),
    ('2722', 'Terrenos', '272', 'ASSET', 'DEBIT', FALSE),
    ('2723', 'Edificaciones', '272', 'ASSET', 'DEBIT', FALSE),
    ('2724', 'Maquinarias y equipos de explotación', '272', 'ASSET', 'DEBIT', FALSE),
    ('2725', 'Unidades de transporte', '272', 'ASSET', 'DEBIT', FALSE),
    ('2726', 'Muebles y enseres', '272', 'ASSET', 'DEBIT', FALSE),
    ('2727', 'Equipos diversos', '272', 'ASSET', 'DEBIT', FALSE),
    ('2728', 'Herramientas y unidades de reemplazo', '272', 'ASSET', 'DEBIT', FALSE),
    ('2729', 'Obras en curso', '272', 'ASSET', 'DEBIT', FALSE),
    ('2731', 'Concesiones, licencias y derechos', '273', 'ASSET', 'DEBIT', FALSE),
    ('2732', 'Patentes y propiedad industrial', '273', 'ASSET', 'DEBIT', FALSE),
    ('2733', 'Programas de computadora (software)', '273', 'ASSET', 'DEBIT', FALSE),
    ('2734', 'Costos de exploración y desarrollo', '273', 'ASSET', 'DEBIT', FALSE),
    ('2735', 'Fórmulas, diseños y prototipos', '273', 'ASSET', 'DEBIT', FALSE),
    ('2739', 'Otros activos intangibles', '273', 'ASSET', 'DEBIT', FALSE),
    ('2741', 'Activos biológicos en producción', '274', 'ASSET', 'DEBIT', FALSE),
    ('2742', 'Activos biológicos en desarrollo', '274', 'ASSET', 'DEBIT', FALSE),
    ('2752', 'Edificaciones', '275', 'ASSET', 'DEBIT', FALSE),
    ('2760', 'Planta productora en producción', '276', 'ASSET', 'DEBIT', FALSE),
    ('2762', 'Edificaciones', '276', 'ASSET', 'DEBIT', FALSE),
    ('2763', 'Maquinarias y equipo de explotación', '276', 'ASSET', 'DEBIT', FALSE),
    ('2764', 'Unidades de transporte', '276', 'ASSET', 'DEBIT', FALSE),
    ('2765', 'Muebles y enseres', '276', 'ASSET', 'DEBIT', FALSE),
    ('2766', 'Equipos diversos', '276', 'ASSET', 'DEBIT', FALSE),
    ('2767', 'Herramientas y unidades de reemplazo', '276', 'ASSET', 'DEBIT', FALSE),
    ('2771', 'Concesiones, licencias y derechos', '277', 'ASSET', 'DEBIT', FALSE),
    ('2772', 'Patentes y propiedad industrial', '277', 'ASSET', 'DEBIT', FALSE),
    ('2773', 'Programas de computadora (software)', '277', 'ASSET', 'DEBIT', FALSE),
    ('2774', 'Costos de exploración y desarrollo', '277', 'ASSET', 'DEBIT', FALSE),
    ('2775', 'Fórmulas, diseños y prototipos', '277', 'ASSET', 'DEBIT', FALSE),
    ('2779', 'Otros activos intangibles', '277', 'ASSET', 'DEBIT', FALSE),
    ('2781', 'Activos biológicos en producción', '278', 'ASSET', 'DEBIT', FALSE),
    ('2782', 'Activos biológicos en desarrollo', '278', 'ASSET', 'DEBIT', FALSE),
    ('2791', 'Propiedad de inversión', '279', 'ASSET', 'DEBIT', FALSE),
    ('2793', 'Propiedad, planta y equipo', '279', 'ASSET', 'DEBIT', FALSE),
    ('2794', 'Intangibles', '279', 'ASSET', 'DEBIT', FALSE),
    ('2795', 'Activos biológicos', '279', 'ASSET', 'DEBIT', FALSE),
    ('2911', 'Mercaderías', '291', 'ASSET', 'CREDIT', FALSE),
    ('2921', 'Productos terminados', '292', 'ASSET', 'CREDIT', FALSE),
    ('2925', 'Inventario de servicios terminados', '292', 'ASSET', 'CREDIT', FALSE),
    ('2931', 'Subproductos', '293', 'ASSET', 'CREDIT', TRUE),
    ('2932', 'Desechos y desperdicios', '293', 'ASSET', 'CREDIT', TRUE),
    ('2941', 'Productos en proceso', '294', 'ASSET', 'CREDIT', FALSE),
    ('2945', 'Inventario de servicios en proceso', '294', 'ASSET', 'CREDIT', TRUE),
    ('2951', 'Materias primas', '295', 'ASSET', 'CREDIT', FALSE),
    ('2961', 'Materiales auxiliares', '296', 'ASSET', 'CREDIT', TRUE),
    ('2962', 'Suministros', '296', 'ASSET', 'CREDIT', TRUE),
    ('2963', 'Repuestos', '296', 'ASSET', 'CREDIT', TRUE),
    ('2971', 'Envases', '297', 'ASSET', 'CREDIT', TRUE),
    ('2972', 'Embalajes', '297', 'ASSET', 'CREDIT', TRUE),
    ('2981', 'Mercaderías', '298', 'ASSET', 'CREDIT', TRUE),
    ('2982', 'Materias primas', '298', 'ASSET', 'CREDIT', TRUE),
    ('2983', 'Materiales auxiliares, suministros y repuestos', '298', 'ASSET', 'CREDIT', TRUE),
    ('2984', 'Envases y embalajes', '298', 'ASSET', 'CREDIT', TRUE),
    ('3082', 'Instrumentos financieros representativos de derecho patrimonial – Acuerdo de compra', '308', 'ASSET', 'DEBIT', FALSE),
    ('3111', 'Urbanos', '311', 'ASSET', 'DEBIT', FALSE),
    ('3112', 'Rurales', '311', 'ASSET', 'DEBIT', FALSE),
    ('3121', 'Edificaciones', '312', 'ASSET', 'DEBIT', FALSE),
    ('3131', 'Edificaciones', '313', 'ASSET', 'DEBIT', FALSE),
    ('3211', 'Terrenos', '321', 'ASSET', 'DEBIT', FALSE),
    ('3212', 'Edificaciones', '321', 'ASSET', 'DEBIT', FALSE),
    ('3220', 'Planta productora en producción', '322', 'ASSET', 'DEBIT', FALSE),
    ('3221', 'Planta productora en desarrollo', '322', 'ASSET', 'DEBIT', FALSE),
    ('3222', 'Terrenos', '322', 'ASSET', 'DEBIT', FALSE),
    ('3223', 'Edificaciones', '322', 'ASSET', 'DEBIT', FALSE),
    ('3224', 'Maquinaria y equipo de explotación', '322', 'ASSET', 'DEBIT', FALSE),
    ('3225', 'Unidades de transporte', '322', 'ASSET', 'DEBIT', FALSE),
    ('3226', 'Muebles y enseres', '322', 'ASSET', 'DEBIT', FALSE),
    ('3227', 'Equipos diversos', '322', 'ASSET', 'DEBIT', FALSE),
    ('3228', 'Herramientas y unidades de reemplazo', '322', 'ASSET', 'DEBIT', FALSE),
    ('3230', 'Planta productora en producción', '323', 'ASSET', 'DEBIT', FALSE),
    ('3232', 'Terrenos', '323', 'ASSET', 'DEBIT', FALSE),
    ('3233', 'Edificaciones', '323', 'ASSET', 'DEBIT', FALSE),
    ('3234', 'Maquinaria y equipo de explotación', '323', 'ASSET', 'DEBIT', FALSE),
    ('3235', 'Unidades de transporte', '323', 'ASSET', 'DEBIT', FALSE),
    ('3236', 'Equipos diversos', '323', 'ASSET', 'DEBIT', FALSE),
    ('3301', 'Planta productora en producción', '330', 'ASSET', 'DEBIT', FALSE),
    ('3302', 'Planta productora en desarrollo', '330', 'ASSET', 'DEBIT', FALSE),
    ('3311', 'Terrenos', '331', 'ASSET', 'DEBIT', FALSE),
    ('3321', 'Edificaciones', '332', 'ASSET', 'DEBIT', FALSE),
    ('3324', 'Instalaciones', '332', 'ASSET', 'DEBIT', FALSE),
    ('3325', 'Mejoras en locales arrendados.', '332', 'ASSET', 'DEBIT', FALSE),
    ('3331', 'Maquinaria y equipo de explotación', '333', 'ASSET', 'DEBIT', FALSE),
    ('3341', 'Vehículos motorizados', '334', 'ASSET', 'DEBIT', FALSE),
    ('3342', 'Vehículos no motorizados', '334', 'ASSET', 'DEBIT', FALSE),
    ('3351', 'Muebles', '335', 'ASSET', 'DEBIT', TRUE),
    ('3352', 'Enseres', '335', 'ASSET', 'DEBIT', TRUE),
    ('3411', 'Derechos por concesiones', '34', 'ASSET', 'DEBIT', TRUE),
    ('3412', 'Licencias', '34', 'ASSET', 'DEBIT', TRUE),
    ('3419', 'Otros derechos', '34', 'ASSET', 'DEBIT', TRUE),
    ('3512', 'De origen vegetal', '35', 'ASSET', 'DEBIT', FALSE),
    ('3521', 'De origen animal', '352', 'ASSET', 'DEBIT', FALSE),
    ('3522', 'De origen vegetal', '352', 'ASSET', 'DEBIT', FALSE),
    ('3611', 'Terrenos', '361', 'ASSET', 'CREDIT', FALSE),
    ('3612', 'Edificaciones', '361', 'ASSET', 'CREDIT', FALSE),
    ('3613', 'Construcciones en curso - edificaciones', '361', 'ASSET', 'CREDIT', FALSE),
    ('3621', 'Terrenos', '362', 'ASSET', 'CREDIT', FALSE),
    ('3622', 'Edificaciones', '362', 'ASSET', 'CREDIT', FALSE),
    ('3631', 'Terrenos', '363', 'ASSET', 'CREDIT', FALSE),
    ('3632', 'Edificaciones', '363', 'ASSET', 'CREDIT', FALSE),
    ('3633', 'Maquinaria y equipo de explotación', '363', 'ASSET', 'CREDIT', TRUE),
    ('3634', 'Unidades de transporte', '363', 'ASSET', 'CREDIT', TRUE),
    ('3635', 'Muebles y enseres', '363', 'ASSET', 'CREDIT', TRUE),
    ('3636', 'Equipos diversos', '363', 'ASSET', 'CREDIT', TRUE),
    ('3646', 'Equipos diversos', '364', 'ASSET', 'CREDIT', FALSE),
    ('3647', 'Herramientas y unidades de reemplazo', '364', 'ASSET', 'CREDIT', FALSE),
    ('3649', 'Obras en curso', '364', 'ASSET', 'CREDIT', FALSE),
    ('3651', 'Concesiones, licencias y otros derechos', '365', 'ASSET', 'CREDIT', FALSE),
    ('3652', 'Patentes y propiedad industrial', '365', 'ASSET', 'CREDIT', FALSE),
    ('3653', 'Programas de computadora (software)', '365', 'ASSET', 'CREDIT', FALSE),
    ('3654', 'Costos de exploración y desarrollo', '365', 'ASSET', 'CREDIT', FALSE),
    ('3655', 'Fórmulas, diseños y prototipos', '365', 'ASSET', 'CREDIT', FALSE),
    ('3657', 'Plusvalía mercantil', '365', 'ASSET', 'CREDIT', TRUE),
    ('3659', 'Otros activos intangibles', '365', 'ASSET', 'CREDIT', FALSE),
    ('3661', 'Activos biológicos en producción', '366', 'ASSET', 'CREDIT', FALSE),
    ('3662', 'Activos biológicos en desarrollo', '366', 'ASSET', 'CREDIT', FALSE),
    ('3671', 'Inversiones a ser mantenidas hasta el vencimiento', '367', 'ASSET', 'CREDIT', FALSE),
    ('3672', 'Inversiones financieras representativas de derecho patrimonial', '367', 'ASSET', 'CREDIT', FALSE),
    ('3673', 'Otras inversiones financieras', '367', 'ASSET', 'CREDIT', FALSE),
    ('3711', 'Impuesto a la renta diferido – Patrimonio', '371', 'ASSET', 'DEBIT', TRUE),
    ('3712', 'Impuesto a la renta diferido – Resultados', '371', 'ASSET', 'DEBIT', TRUE),
    ('3721', 'Participaciones de los trabajadores diferidas – Patrimonio', '372', 'ASSET', 'DEBIT', TRUE),
    ('3722', 'Participaciones de los trabajadores diferidas – Resultados', '372', 'ASSET', 'DEBIT', TRUE),
    ('3731', 'Intereses no devengados en transacciones con terceros', '373', 'ASSET', 'DEBIT', TRUE),
    ('3732', 'Intereses no devengados en medición a valor descontado', '373', 'ASSET', 'DEBIT', TRUE),
    ('3811', 'Obras de arte', '381', 'ASSET', 'DEBIT', TRUE),
    ('3812', 'Biblioteca', '381', 'ASSET', 'DEBIT', TRUE),
    ('3813', 'Otros', '381', 'ASSET', 'DEBIT', TRUE),
    ('3821', 'Monedas y joyas', '382', 'ASSET', 'DEBIT', TRUE),
    ('3822', 'Bienes entregados en comodato', '382', 'ASSET', 'DEBIT', TRUE),
    ('3823', 'Bienes recibidos en pago (adjudicados y realizables)', '382', 'ASSET', 'DEBIT', TRUE),
    ('3829', 'Otros', '382', 'ASSET', 'DEBIT', TRUE),
    ('3911', 'Edificaciones', '391', 'ASSET', 'CREDIT', FALSE),
    ('3921', 'Edificaciones', '392', 'ASSET', 'CREDIT', FALSE),
    ('3932', 'Edificaciones', '393', 'ASSET', 'CREDIT', FALSE),
    ('3933', 'Maquinarias y equipos de explotación', '393', 'ASSET', 'CREDIT', FALSE),
    ('3934', 'Unidades de transporte', '393', 'ASSET', 'CREDIT', TRUE),
    ('3935', 'Muebles y enseres', '393', 'ASSET', 'CREDIT', TRUE),
    ('3936', 'Equipos diversos', '393', 'ASSET', 'CREDIT', TRUE),
    ('3961', 'Intangibles – Costo', '396', 'ASSET', 'CREDIT', FALSE),
    ('3962', 'Intangibles – Revaluación', '396', 'ASSET', 'CREDIT', FALSE),
    ('3963', 'Intangibles – Costos de financiación', '396', 'ASSET', 'CREDIT', FALSE),
    ('3981', 'Activos biológicos en producción - Costo', '398', 'ASSET', 'CREDIT', FALSE),
    ('4011', 'Impuesto general a las ventas', '401', 'LIABILITY', 'CREDIT', FALSE),
    ('4012', 'Impuesto selectivo al consumo', '401', 'LIABILITY', 'CREDIT', TRUE),
    ('4015', 'Derechos aduaneros', '401', 'LIABILITY', 'CREDIT', FALSE),
    ('4017', 'Impuesto a la renta', '401', 'LIABILITY', 'CREDIT', FALSE),
    ('4018', 'Otros impuestos y contraprestaciones', '401', 'LIABILITY', 'CREDIT', FALSE),
    ('6094', 'Costos vinculados con las compras de envases y embalajes', '60', 'EXPENSE', 'DEBIT', FALSE),
    ('6111', 'Mercaderías', '611', 'EXPENSE', 'DEBIT', TRUE),
    ('6121', 'Materias primas', '612', 'EXPENSE', 'DEBIT', TRUE),
    ('6131', 'Materiales auxiliares', '613', 'EXPENSE', 'DEBIT', TRUE),
    ('6132', 'Suministros', '613', 'EXPENSE', 'DEBIT', TRUE),
    ('6133', 'Repuestos', '613', 'EXPENSE', 'DEBIT', TRUE),
    ('6141', 'Envases', '614', 'EXPENSE', 'DEBIT', TRUE),
    ('6142', 'Embalajes', '614', 'EXPENSE', 'DEBIT', TRUE),
    ('6211', 'Sueldos y salarios', '621', 'EXPENSE', 'DEBIT', TRUE),
    ('6212', 'Comisiones', '621', 'EXPENSE', 'DEBIT', TRUE),
    ('6213', 'Remuneraciones en especie', '621', 'EXPENSE', 'DEBIT', TRUE),
    ('6214', 'Gratificaciones', '621', 'EXPENSE', 'DEBIT', TRUE),
    ('6215', 'Vacaciones', '621', 'EXPENSE', 'DEBIT', TRUE),
    ('6271', 'Régimen de prestaciones de salud', '627', 'EXPENSE', 'DEBIT', TRUE),
    ('6272', 'Régimen de pensiones - Aporte de empresa', '627', 'EXPENSE', 'DEBIT', TRUE),
    ('6273', 'Seguro complementario de trabajo de riesgo, accidentes de trabajo y enfermedades profesionales', '627', 'EXPENSE', 'DEBIT', TRUE),
    ('6274', 'Seguro de vida', '627', 'EXPENSE', 'DEBIT', TRUE),
    ('6275', 'Seguros particulares de prestaciones de salud – EPS y otros particulares', '627', 'EXPENSE', 'DEBIT', TRUE),
    ('6276', 'Caja de beneficios de seguridad social del pescador', '627', 'EXPENSE', 'DEBIT', TRUE),
    ('6277', 'Contribuciones al SENATI', '627', 'EXPENSE', 'DEBIT', TRUE),
    ('6291', 'Compensación por tiempo de servicio', '629', 'EXPENSE', 'DEBIT', TRUE),
    ('6292', 'Pensiones y jubilaciones', '629', 'EXPENSE', 'DEBIT', TRUE),
    ('6293', 'Otros beneficios post-empleo', '629', 'EXPENSE', 'DEBIT', TRUE),
    ('6294', 'Participación en las utilidades', '629', 'EXPENSE', 'DEBIT', TRUE),
    ('6367', 'Cable', '636', 'EXPENSE', 'DEBIT', TRUE),
    ('6371', 'Publicidad', '637', 'EXPENSE', 'DEBIT', TRUE),
    ('6372', 'Publicaciones', '637', 'EXPENSE', 'DEBIT', TRUE),
    ('6373', 'Relaciones públicas', '637', 'EXPENSE', 'DEBIT', TRUE),
    ('6391', 'Gastos bancarios', '639', 'EXPENSE', 'DEBIT', TRUE),
    ('6392', 'Gastos de laboratorio', '639', 'EXPENSE', 'DEBIT', TRUE),
    ('6411', 'Impuesto general a las ventas y selectivo al consumo', '641', 'EXPENSE', 'DEBIT', TRUE),
    ('6412', 'Impuesto a las transacciones financieras', '641', 'EXPENSE', 'DEBIT', TRUE),
    ('6413', 'Impuesto temporal a los activos netos', '641', 'EXPENSE', 'DEBIT', TRUE),
    ('6414', 'Impuesto a los juegos de casino y máquinas tragamonedas', '641', 'EXPENSE', 'DEBIT', TRUE),
    ('6415', 'Regalías mineras', '641', 'EXPENSE', 'DEBIT', TRUE),
    ('6416', 'Cánones', '641', 'EXPENSE', 'DEBIT', TRUE),
    ('6419', 'Otros', '641', 'EXPENSE', 'DEBIT', TRUE),
    ('6431', 'Impuesto predial', '643', 'EXPENSE', 'DEBIT', TRUE),
    ('6432', 'Arbitrios municipales y seguridad ciudadana', '643', 'EXPENSE', 'DEBIT', TRUE),
    ('6433', 'Impuesto al patrimonio vehicular', '643', 'EXPENSE', 'DEBIT', TRUE),
    ('6434', 'Licencia de funcionamiento', '643', 'EXPENSE', 'DEBIT', TRUE),
    ('6439', 'Otros', '643', 'EXPENSE', 'DEBIT', TRUE),
    ('6442', 'Contribución al SENCICO', '644', 'EXPENSE', 'DEBIT', TRUE),
    ('6443', 'Otros', '644', 'EXPENSE', 'DEBIT', TRUE),
    ('6451', 'Intereses', '645', 'EXPENSE', 'DEBIT', TRUE),
    ('6452', 'intereses - fraccionamiento', '645', 'EXPENSE', 'DEBIT', TRUE),
    ('6453', 'Multas', '645', 'EXPENSE', 'DEBIT', TRUE),
    ('6454', 'Costas y otros', '645', 'EXPENSE', 'DEBIT', TRUE),
    ('6551', 'Costo neto de enajenación de activos inmovilizados', '655', 'EXPENSE', 'DEBIT', FALSE),
    ('6552', 'Operaciones discontinuadas – Abandono de activos', '655', 'EXPENSE', 'DEBIT', FALSE),
    ('6591', 'Donaciones', '659', 'EXPENSE', 'DEBIT', TRUE),
    ('6592', 'Sanciones administrativas', '659', 'EXPENSE', 'DEBIT', TRUE),
    ('6611', 'Mercaderías', '661', 'EXPENSE', 'DEBIT', TRUE),
    ('6612', 'Productos terminados', '661', 'EXPENSE', 'DEBIT', TRUE),
    ('6613', 'Activos no corrientes mantenidos para la venta', '661', 'EXPENSE', 'DEBIT', FALSE),
    ('6621', 'Propiedades de inversión', '662', 'EXPENSE', 'DEBIT', TRUE),
    ('6622', 'Activos biológicos', '662', 'EXPENSE', 'DEBIT', TRUE),
    ('6711', 'Préstamos de instituciones financieras y otras entidades', '671', 'EXPENSE', 'DEBIT', TRUE),
    ('6712', 'Contratos de arrendamiento financiero', '671', 'EXPENSE', 'DEBIT', TRUE),
    ('6713', 'Emisión y colocación de instrumentos representativos de deuda y patrimonio', '671', 'EXPENSE', 'DEBIT', TRUE),
    ('6714', 'Documentos vendidos o descontados', '671', 'EXPENSE', 'DEBIT', TRUE),
    ('6731', 'Préstamos de instituciones financieras y otras entidades', '673', 'EXPENSE', 'DEBIT', FALSE),
    ('6732', 'Contratos de arrendamiento financiero', '673', 'EXPENSE', 'DEBIT', TRUE),
    ('6733', 'Otros instrumentos financieros por pagar', '673', 'EXPENSE', 'DEBIT', TRUE),
    ('6734', 'Documentos vendidos o descontados', '673', 'EXPENSE', 'DEBIT', TRUE),
    ('6735', 'Obligaciones emitidas', '673', 'EXPENSE', 'DEBIT', TRUE),
    ('6736', 'Obligaciones comerciales', '673', 'EXPENSE', 'DEBIT', TRUE),
    ('6741', 'Pérdida en instrumentos vendidos', '674', 'EXPENSE', 'DEBIT', TRUE),
    ('6771', 'Inversiones mantenidas para negociación', '677', 'EXPENSE', 'DEBIT', TRUE),
    ('6772', 'Otras inversiones financieras', '677', 'EXPENSE', 'DEBIT', TRUE),
    ('6773', 'Otros', '677', 'EXPENSE', 'DEBIT', TRUE),
    ('6781', 'Participación en los resultados de subsidiarias y asociadas bajo el método del valor patrimonial', '678', 'EXPENSE', 'DEBIT', TRUE),
    ('6782', 'Participaciones en negocios conjuntos', '678', 'EXPENSE', 'DEBIT', TRUE),
    ('6791', 'Primas por opciones', '679', 'EXPENSE', 'DEBIT', TRUE),
    ('6792', 'Gastos financieros en medición a valor descontado', '679', 'EXPENSE', 'DEBIT', TRUE),
    ('6793', 'Gastos financieros en actualización de activos por derecho de uso', '679', 'EXPENSE', 'DEBIT', TRUE),
    ('6811', 'Edificaciones', '681', 'EXPENSE', 'DEBIT', FALSE),
    ('6821', 'Propiedades de inversión', '682', 'EXPENSE', 'DEBIT', FALSE),
    ('6822', 'Propiedad, planta y equipo', '682', 'EXPENSE', 'DEBIT', FALSE),
    ('6831', 'Depreciación de activos por derecho de uso - arrendamiento operativo', '683', 'EXPENSE', 'DEBIT', FALSE),
    ('6841', 'Depreciación de propiedad, planta y equipo - Costo', '684', 'EXPENSE', 'DEBIT', FALSE),
    ('6842', 'Depreciación de propiedad, planta y equipo - Revaluación', '684', 'EXPENSE', 'DEBIT', FALSE),
    ('6843', 'Depreciación de propiedad, planta y equipo - Costos de financiación', '684', 'EXPENSE', 'DEBIT', FALSE),
    ('6851', 'Depreciación de activos biológicos en producción - costo', '685', 'EXPENSE', 'DEBIT', FALSE),
    ('6852', 'Depreciación de activos biológicos en producción - costo de financiación', '685', 'EXPENSE', 'DEBIT', FALSE),
    ('6861', 'Amortización de intangibles – Costo', '686', 'EXPENSE', 'DEBIT', FALSE),
    ('6862', 'Amortización de intangibles – Revaluación', '686', 'EXPENSE', 'DEBIT', FALSE),
    ('6871', 'Estimación de cuentas de cobranza dudosa', '687', 'EXPENSE', 'DEBIT', FALSE),
    ('6873', 'Desvalorización de inversiones mobiliarias', '687', 'EXPENSE', 'DEBIT', FALSE),
    ('6882', 'Desvalorización de propiedad de inversión', '688', 'EXPENSE', 'DEBIT', FALSE),
    ('6883', 'Desvalorización de propiedad, planta y equipo', '688', 'EXPENSE', 'DEBIT', FALSE),
    ('6884', 'Desvalorización de intangibles', '688', 'EXPENSE', 'DEBIT', FALSE),
    ('6889', 'Desvalorización de activos biológicos en producción', '688', 'EXPENSE', 'DEBIT', FALSE),
    ('6891', 'Provisión para litigios', '689', 'EXPENSE', 'DEBIT', FALSE),
    ('6892', 'Provisión por desmantelamiento, retiro o rehabilitación del inmovilizado', '689', 'EXPENSE', 'DEBIT', FALSE),
    ('6893', 'Provisión para reestructuraciones', '689', 'EXPENSE', 'DEBIT', TRUE),
    ('6894', 'Provisión para protección y remediación del medio ambiente', '689', 'EXPENSE', 'DEBIT', FALSE),
    ('6896', 'Provisión para garantías', '689', 'EXPENSE', 'DEBIT', FALSE),
    ('6897', 'Provisión por activos por derecho de uso', '689', 'EXPENSE', 'DEBIT', FALSE),
    ('6899', 'Otras provisiones', '689', 'EXPENSE', 'DEBIT', TRUE),
    ('6911', 'Mercaderías - exportación', '691', 'EXPENSE', 'DEBIT', TRUE),
    ('6912', 'Mercaderías - venta local', '691', 'EXPENSE', 'DEBIT', TRUE),
    ('6921', 'Productos terminados - Exportación', '692', 'EXPENSE', 'DEBIT', TRUE),
    ('6922', 'Productos terminados - Venta local', '692', 'EXPENSE', 'DEBIT', TRUE),
    ('6923', 'Costos de financiación – Productos terminados', '692', 'EXPENSE', 'DEBIT', TRUE),
    ('6924', 'Costos de producción no absorbido – Productos terminados', '692', 'EXPENSE', 'DEBIT', TRUE),
    ('6925', 'Costo de ineficiencia – Productos terminados', '692', 'EXPENSE', 'DEBIT', TRUE),
    ('6931', 'Servicios – Exportación', '693', 'EXPENSE', 'DEBIT', TRUE),
    ('6932', 'Servicios – local', '693', 'EXPENSE', 'DEBIT', TRUE),
    ('6941', 'Subproductos', '694', 'EXPENSE', 'DEBIT', TRUE),
    ('6942', 'Desechos y desperdicios', '694', 'EXPENSE', 'DEBIT', TRUE),
    ('6951', 'Mercaderías', '695', 'EXPENSE', 'DEBIT', TRUE),
    ('6952', 'Productos terminados', '695', 'EXPENSE', 'DEBIT', TRUE),
    ('6953', 'Subproductos, desechos y desperdicios', '695', 'EXPENSE', 'DEBIT', TRUE),
    ('6954', 'Productos en proceso', '695', 'EXPENSE', 'DEBIT', TRUE),
    ('6955', 'Materias primas', '695', 'EXPENSE', 'DEBIT', TRUE),
    ('6956', 'Materiales auxiliares, suministros y repuestos', '695', 'EXPENSE', 'DEBIT', TRUE),
    ('6957', 'Envases y embalajes', '695', 'EXPENSE', 'DEBIT', TRUE),
    ('6958', 'Inventarios por recibir', '695', 'EXPENSE', 'DEBIT', TRUE),
    ('7011', 'Mercaderías - venta de exportación', '701', 'INCOME', 'CREDIT', FALSE),
    ('7012', 'Mercaderías - venta local', '701', 'INCOME', 'CREDIT', TRUE),
    ('7021', 'Productos terminados - venta de exportación', '702', 'INCOME', 'CREDIT', FALSE),
    ('7022', 'Productos terminados - venta local', '702', 'INCOME', 'CREDIT', FALSE),
    ('7031', 'Servicios – exportación', '703', 'INCOME', 'CREDIT', FALSE),
    ('7032', 'Servicios – local', '703', 'INCOME', 'CREDIT', FALSE),
    ('7041', 'Subproductos', '704', 'INCOME', 'CREDIT', FALSE),
    ('7042', 'Desechos y desperdicios', '704', 'INCOME', 'CREDIT', FALSE),
    ('7091', 'Mercaderías - Venta de exportación', '709', 'INCOME', 'CREDIT', FALSE),
    ('7092', 'Mercaderías - Venta local', '709', 'INCOME', 'CREDIT', FALSE),
    ('7093', 'Productos terminados - Venta de exportación', '709', 'INCOME', 'CREDIT', FALSE),
    ('7094', 'Productos terminados - Venta local', '709', 'INCOME', 'CREDIT', FALSE),
    ('7095', 'Inventarios de servicios rechazados', '709', 'INCOME', 'CREDIT', FALSE),
    ('7096', 'Subproductos, desechos y desperdicios', '709', 'INCOME', 'CREDIT', FALSE),
    ('11211', 'Costo', '1121', 'ASSET', 'DEBIT', TRUE),
    ('11212', 'Valor Razonable', '1121', 'ASSET', 'DEBIT', TRUE),
    ('11311', 'Costo', '1131', 'ASSET', 'DEBIT', TRUE),
    ('11312', 'Valor Razonable', '1131', 'ASSET', 'DEBIT', TRUE),
    ('11321', 'Costo', '1132', 'ASSET', 'DEBIT', TRUE),
    ('11322', 'Valor Razonable', '1132', 'ASSET', 'DEBIT', TRUE),
    ('16611', 'Costo', '1661', 'ASSET', 'DEBIT', TRUE),
    ('16612', 'Valor razonable', '1661', 'ASSET', 'DEBIT', TRUE),
    ('16621', 'Costo', '1662', 'ASSET', 'DEBIT', TRUE),
    ('16622', 'Valor razonable', '1662', 'ASSET', 'DEBIT', TRUE),
    ('20111', 'Costo', '2011', 'ASSET', 'DEBIT', TRUE),
    ('20114', 'Valor razonable', '2011', 'ASSET', 'DEBIT', TRUE),
    ('21111', 'Costo', '2111', 'ASSET', 'DEBIT', TRUE),
    ('21113', 'Costo de financiación', '2111', 'ASSET', 'DEBIT', TRUE),
    ('21114', 'Valor razonable', '2111', 'ASSET', 'DEBIT', TRUE),
    ('21511', 'Costo', '2151', 'ASSET', 'DEBIT', TRUE),
    ('23511', 'Costo', '2351', 'ASSET', 'DEBIT', TRUE),
    ('24111', 'Costo', '2411', 'ASSET', 'DEBIT', TRUE),
    ('24114', 'Valor razonable', '2411', 'ASSET', 'DEBIT', TRUE),
    ('27111', 'Costo', '2711', 'ASSET', 'DEBIT', TRUE),
    ('27112', 'Revaluación', '2711', 'ASSET', 'DEBIT', TRUE),
    ('27114', 'Valor razonable', '2711', 'ASSET', 'DEBIT', TRUE),
    ('27121', 'Costo', '2712', 'ASSET', 'DEBIT', TRUE),
    ('27122', 'Revaluación', '2712', 'ASSET', 'DEBIT', TRUE),
    ('27123', 'Costos de financiación', '2712', 'ASSET', 'DEBIT', TRUE),
    ('27124', 'Valor razonable', '2712', 'ASSET', 'DEBIT', TRUE),
    ('27201', 'Costo', '2720', 'ASSET', 'DEBIT', TRUE),
    ('27202', 'Revaluación', '2720', 'ASSET', 'DEBIT', TRUE),
    ('27203', 'Costo de financiación', '2720', 'ASSET', 'DEBIT', TRUE),
    ('27204', 'Valor razonable', '2720', 'ASSET', 'DEBIT', TRUE),
    ('27211', 'Costo', '2721', 'ASSET', 'DEBIT', TRUE),
    ('27212', 'Revaluación', '2721', 'ASSET', 'DEBIT', TRUE),
    ('27213', 'Costo de financiación', '2721', 'ASSET', 'DEBIT', TRUE),
    ('27214', 'Valor razonable', '2721', 'ASSET', 'DEBIT', TRUE),
    ('27221', 'Costo', '2722', 'ASSET', 'DEBIT', TRUE),
    ('27222', 'Revaluación', '2722', 'ASSET', 'DEBIT', TRUE),
    ('27231', 'Costo', '2723', 'ASSET', 'DEBIT', TRUE),
    ('27232', 'Revaluación', '2723', 'ASSET', 'DEBIT', TRUE),
    ('27233', 'Costo de financiación', '2723', 'ASSET', 'DEBIT', TRUE),
    ('27241', 'Costo', '2724', 'ASSET', 'DEBIT', TRUE),
    ('27242', 'Revaluación', '2724', 'ASSET', 'DEBIT', TRUE),
    ('27251', 'Costo', '2725', 'ASSET', 'DEBIT', TRUE),
    ('27252', 'Revaluación', '2725', 'ASSET', 'DEBIT', TRUE),
    ('27261', 'Costo', '2726', 'ASSET', 'DEBIT', TRUE),
    ('27262', 'Revaluación', '2726', 'ASSET', 'DEBIT', TRUE),
    ('27271', 'Costo', '2727', 'ASSET', 'DEBIT', TRUE),
    ('27272', 'Revaluación', '2727', 'ASSET', 'DEBIT', TRUE),
    ('27281', 'Costo', '2728', 'ASSET', 'DEBIT', TRUE),
    ('27282', 'Revaluación', '2728', 'ASSET', 'DEBIT', TRUE),
    ('27291', 'Costo', '2729', 'ASSET', 'DEBIT', TRUE),
    ('27292', 'Revaluación', '2729', 'ASSET', 'DEBIT', TRUE),
    ('27311', 'Costo', '2731', 'ASSET', 'DEBIT', TRUE),
    ('27312', 'Revaluación', '2731', 'ASSET', 'DEBIT', TRUE),
    ('27321', 'Costo', '2732', 'ASSET', 'DEBIT', TRUE),
    ('27322', 'Revaluación', '2732', 'ASSET', 'DEBIT', TRUE),
    ('27331', 'Costo', '2733', 'ASSET', 'DEBIT', TRUE),
    ('27332', 'Revaluación', '2733', 'ASSET', 'DEBIT', TRUE),
    ('27341', 'Costo', '2734', 'ASSET', 'DEBIT', TRUE),
    ('27342', 'Revaluación', '2734', 'ASSET', 'DEBIT', TRUE),
    ('27351', 'Costo', '2735', 'ASSET', 'DEBIT', TRUE),
    ('27352', 'Revaluación', '2735', 'ASSET', 'DEBIT', TRUE),
    ('27391', 'Costo', '2739', 'ASSET', 'DEBIT', TRUE),
    ('27392', 'Revaluación', '2739', 'ASSET', 'DEBIT', TRUE),
    ('27411', 'Costo', '2741', 'ASSET', 'DEBIT', TRUE),
    ('27413', 'Costos de financiación', '2741', 'ASSET', 'DEBIT', TRUE),
    ('27414', 'Valor razonable', '2741', 'ASSET', 'DEBIT', TRUE),
    ('27421', 'Costo', '2742', 'ASSET', 'DEBIT', TRUE),
    ('27423', 'Costos de financiación', '2742', 'ASSET', 'DEBIT', TRUE),
    ('27424', 'Valor razonable', '2742', 'ASSET', 'DEBIT', TRUE),
    ('27521', 'Costo', '2752', 'ASSET', 'DEBIT', TRUE),
    ('27522', 'Revaluación', '2752', 'ASSET', 'DEBIT', TRUE),
    ('27523', 'Costo de financiación', '2752', 'ASSET', 'DEBIT', TRUE),
    ('27601', 'Costo', '2760', 'ASSET', 'DEBIT', TRUE),
    ('27602', 'Revaluación', '2760', 'ASSET', 'DEBIT', TRUE),
    ('27603', 'Costo de financiación', '2760', 'ASSET', 'DEBIT', TRUE),
    ('27604', 'Valor razonable', '2760', 'ASSET', 'DEBIT', TRUE),
    ('27621', 'Costo', '2762', 'ASSET', 'DEBIT', TRUE),
    ('27622', 'Revaluación', '2762', 'ASSET', 'DEBIT', TRUE),
    ('27623', 'Costo de financiación', '2762', 'ASSET', 'DEBIT', TRUE),
    ('27631', 'Costo', '2763', 'ASSET', 'DEBIT', TRUE),
    ('27632', 'Revaluación', '2763', 'ASSET', 'DEBIT', TRUE),
    ('27633', 'Costo de financiación', '2763', 'ASSET', 'DEBIT', TRUE),
    ('27641', 'Costo', '2764', 'ASSET', 'DEBIT', TRUE),
    ('27642', 'Revaluación', '2764', 'ASSET', 'DEBIT', TRUE),
    ('27651', 'Costo', '2765', 'ASSET', 'DEBIT', TRUE),
    ('27652', 'Revaluación', '2765', 'ASSET', 'DEBIT', TRUE),
    ('27661', 'Costo', '2766', 'ASSET', 'DEBIT', TRUE),
    ('27662', 'Revaluación', '2766', 'ASSET', 'DEBIT', TRUE),
    ('27671', 'Costo', '2767', 'ASSET', 'DEBIT', TRUE),
    ('27672', 'Revaluación', '2767', 'ASSET', 'DEBIT', TRUE),
    ('27711', 'Costo', '2771', 'ASSET', 'DEBIT', TRUE),
    ('27712', 'Revaluación', '2771', 'ASSET', 'DEBIT', TRUE),
    ('27721', 'Costo', '2772', 'ASSET', 'DEBIT', TRUE),
    ('27722', 'Revaluación', '2772', 'ASSET', 'DEBIT', TRUE),
    ('27731', 'Costo', '2773', 'ASSET', 'DEBIT', TRUE),
    ('27732', 'Revaluación', '2773', 'ASSET', 'DEBIT', TRUE),
    ('27741', 'Costo', '2774', 'ASSET', 'DEBIT', TRUE),
    ('27742', 'Revaluación', '2774', 'ASSET', 'DEBIT', TRUE),
    ('27751', 'Costo', '2775', 'ASSET', 'DEBIT', TRUE),
    ('27752', 'Revaluación', '2775', 'ASSET', 'DEBIT', TRUE),
    ('27791', 'Costo', '2779', 'ASSET', 'DEBIT', TRUE),
    ('27792', 'Revaluación', '2779', 'ASSET', 'DEBIT', TRUE),
    ('27811', 'Costo', '2781', 'ASSET', 'DEBIT', TRUE),
    ('27813', 'Costo de financiación', '2781', 'ASSET', 'DEBIT', TRUE),
    ('27821', 'Costo', '2782', 'ASSET', 'DEBIT', TRUE),
    ('27823', 'Costo de financiación', '2782', 'ASSET', 'DEBIT', TRUE),
    ('27910', 'Planta productora en producción', '2791', 'ASSET', 'DEBIT', TRUE),
    ('27911', 'Planta productora en desarrollo', '2791', 'ASSET', 'DEBIT', TRUE),
    ('27912', 'Terrenos', '2791', 'ASSET', 'DEBIT', TRUE),
    ('27913', 'Edificaciones', '2791', 'ASSET', 'DEBIT', TRUE),
    ('27930', 'Plantas productoras en producción', '2793', 'ASSET', 'DEBIT', TRUE),
    ('27931', 'Planta productora en desarrollo', '2793', 'ASSET', 'DEBIT', TRUE),
    ('27932', 'Terrenos', '2793', 'ASSET', 'DEBIT', TRUE),
    ('27933', 'Edificaciones', '2793', 'ASSET', 'DEBIT', TRUE),
    ('27934', 'Maquinarias y equipos de explotación', '2793', 'ASSET', 'DEBIT', TRUE),
    ('27935', 'Unidades de transporte', '2793', 'ASSET', 'DEBIT', TRUE),
    ('27936', 'Muebles y enseres', '2793', 'ASSET', 'DEBIT', TRUE),
    ('27937', 'Equipos diversos', '2793', 'ASSET', 'DEBIT', TRUE),
    ('27938', 'Herramientas y unidades de reemplazo', '2793', 'ASSET', 'DEBIT', TRUE),
    ('27941', 'Concesiones, licencias y otros derechos', '2794', 'ASSET', 'DEBIT', TRUE),
    ('27942', 'Patentes y propiedad industrial', '2794', 'ASSET', 'DEBIT', TRUE),
    ('27943', 'Programas de computadora (software)', '2794', 'ASSET', 'DEBIT', TRUE),
    ('27944', 'Costos de exploración y desarrollo', '2794', 'ASSET', 'DEBIT', TRUE),
    ('27945', 'Fórmulas, diseños y prototipos', '2794', 'ASSET', 'DEBIT', TRUE),
    ('27949', 'Otros activos intangibles', '2794', 'ASSET', 'DEBIT', TRUE),
    ('27951', 'Activos biológicos en producción', '2795', 'ASSET', 'DEBIT', TRUE),
    ('27952', 'Activos biológicos en desarrollo', '2795', 'ASSET', 'DEBIT', TRUE),
    ('29111', 'Costo', '2911', 'ASSET', 'CREDIT', TRUE),
    ('29211', 'Costo', '2921', 'ASSET', 'CREDIT', TRUE),
    ('29213', 'Costo de financiación', '2921', 'ASSET', 'CREDIT', TRUE),
    ('29251', 'Costo', '2925', 'ASSET', 'CREDIT', TRUE),
    ('29411', 'Costo', '2941', 'ASSET', 'CREDIT', TRUE),
    ('29413', 'Costo de financiación', '2941', 'ASSET', 'CREDIT', TRUE),
    ('29511', 'Costo', '2951', 'ASSET', 'CREDIT', TRUE),
    ('30811', 'Costo', '308', 'ASSET', 'DEBIT', TRUE),
    ('30814', 'Valor razonable', '308', 'ASSET', 'DEBIT', TRUE),
    ('30821', 'Costo', '3082', 'ASSET', 'DEBIT', TRUE),
    ('30824', 'Valor razonable', '3082', 'ASSET', 'DEBIT', TRUE),
    ('31111', 'Costo', '3111', 'ASSET', 'DEBIT', TRUE),
    ('31112', 'Revaluación', '3111', 'ASSET', 'DEBIT', TRUE),
    ('31114', 'Valor razonable', '3111', 'ASSET', 'DEBIT', TRUE),
    ('31121', 'Costo', '3112', 'ASSET', 'DEBIT', TRUE),
    ('31122', 'Revaluación', '3112', 'ASSET', 'DEBIT', TRUE),
    ('31124', 'Valor razonable', '3112', 'ASSET', 'DEBIT', TRUE),
    ('31211', 'Costo', '3121', 'ASSET', 'DEBIT', TRUE),
    ('31212', 'Revaluación', '3121', 'ASSET', 'DEBIT', TRUE),
    ('31213', 'Costos de financiación', '3121', 'ASSET', 'DEBIT', TRUE),
    ('31214', 'Valor razonable', '3121', 'ASSET', 'DEBIT', TRUE),
    ('31311', 'Costo', '3131', 'ASSET', 'DEBIT', TRUE),
    ('31312', 'Revaluación', '3131', 'ASSET', 'DEBIT', TRUE),
    ('31313', 'Costos de financiación', '3131', 'ASSET', 'DEBIT', TRUE),
    ('31314', 'Valor razonable', '3131', 'ASSET', 'DEBIT', TRUE),
    ('32111', 'Costo', '3211', 'ASSET', 'DEBIT', TRUE),
    ('32112', 'Revaluación', '3211', 'ASSET', 'DEBIT', TRUE),
    ('32114', 'Valor razonable', '3211', 'ASSET', 'DEBIT', TRUE),
    ('32121', 'Costo', '3212', 'ASSET', 'DEBIT', TRUE),
    ('32122', 'Revaluación', '3212', 'ASSET', 'DEBIT', TRUE),
    ('32123', 'Costo de financiación', '3212', 'ASSET', 'DEBIT', TRUE),
    ('32124', 'Valor razonable', '3212', 'ASSET', 'DEBIT', TRUE),
    ('32201', 'Costo', '3220', 'ASSET', 'DEBIT', TRUE),
    ('32202', 'Revaluación', '3220', 'ASSET', 'DEBIT', TRUE),
    ('32203', 'Costo de financiación', '3220', 'ASSET', 'DEBIT', TRUE),
    ('32211', 'Costo', '3221', 'ASSET', 'DEBIT', TRUE),
    ('32212', 'Revaluación', '3221', 'ASSET', 'DEBIT', TRUE),
    ('32213', 'Costo de financiación', '3221', 'ASSET', 'DEBIT', TRUE),
    ('32221', 'Costo', '3222', 'ASSET', 'DEBIT', TRUE),
    ('32222', 'Revaluación', '3222', 'ASSET', 'DEBIT', TRUE),
    ('32231', 'Costo', '3223', 'ASSET', 'DEBIT', TRUE),
    ('32232', 'Revaluación', '3223', 'ASSET', 'DEBIT', TRUE),
    ('32233', 'Costo de financiación', '3223', 'ASSET', 'DEBIT', TRUE),
    ('32241', 'Costo', '3224', 'ASSET', 'DEBIT', TRUE),
    ('32242', 'Revaluación', '3224', 'ASSET', 'DEBIT', TRUE),
    ('32243', 'Costo de financiación', '3224', 'ASSET', 'DEBIT', TRUE),
    ('32251', 'Costo', '3225', 'ASSET', 'DEBIT', TRUE),
    ('32252', 'Revaluación', '3225', 'ASSET', 'DEBIT', TRUE),
    ('32261', 'Costo', '3226', 'ASSET', 'DEBIT', TRUE),
    ('32262', 'Revaluación', '3226', 'ASSET', 'DEBIT', TRUE),
    ('32271', 'Costo', '3227', 'ASSET', 'DEBIT', TRUE),
    ('32272', 'Revaluación', '3227', 'ASSET', 'DEBIT', TRUE),
    ('32281', 'Costo', '3228', 'ASSET', 'DEBIT', TRUE),
    ('32282', 'Revaluación', '3228', 'ASSET', 'DEBIT', TRUE),
    ('32301', 'Costo', '3230', 'ASSET', 'DEBIT', TRUE),
    ('32302', 'Revaluación', '3230', 'ASSET', 'DEBIT', TRUE),
    ('32321', 'Costo', '3232', 'ASSET', 'DEBIT', TRUE),
    ('32331', 'Costo', '3233', 'ASSET', 'DEBIT', TRUE),
    ('32332', 'Revaluación', '3233', 'ASSET', 'DEBIT', TRUE),
    ('32341', 'Costo', '3234', 'ASSET', 'DEBIT', TRUE),
    ('32342', 'Revaluación', '3234', 'ASSET', 'DEBIT', TRUE),
    ('32351', 'Costo', '3235', 'ASSET', 'DEBIT', TRUE),
    ('32352', 'Revaluación', '3235', 'ASSET', 'DEBIT', TRUE),
    ('32361', 'Costo', '3236', 'ASSET', 'DEBIT', TRUE),
    ('32362', 'Revaluación', '3236', 'ASSET', 'DEBIT', TRUE),
    ('33011', 'Costo', '3301', 'ASSET', 'DEBIT', TRUE),
    ('33012', 'Revaluación', '3301', 'ASSET', 'DEBIT', TRUE),
    ('33013', 'Costo de financiación', '3301', 'ASSET', 'DEBIT', TRUE),
    ('33014', 'Valor razonable', '3301', 'ASSET', 'DEBIT', TRUE),
    ('33021', 'Costo', '3302', 'ASSET', 'DEBIT', TRUE),
    ('33022', 'Revaluación', '3302', 'ASSET', 'DEBIT', TRUE),
    ('33023', 'Costo de financiación', '3302', 'ASSET', 'DEBIT', TRUE),
    ('33024', 'Valor razonable', '3302', 'ASSET', 'DEBIT', TRUE),
    ('33111', 'Costo', '3311', 'ASSET', 'DEBIT', TRUE),
    ('33112', 'Revaluación', '3311', 'ASSET', 'DEBIT', TRUE),
    ('33211', 'Costo', '3321', 'ASSET', 'DEBIT', TRUE),
    ('33212', 'Revaluación', '3321', 'ASSET', 'DEBIT', TRUE),
    ('33213', 'Costo de financiación', '3321', 'ASSET', 'DEBIT', TRUE),
    ('33241', 'Costo', '3324', 'ASSET', 'DEBIT', TRUE),
    ('33242', 'Revaluación', '3324', 'ASSET', 'DEBIT', TRUE),
    ('33243', 'Costo de financiación', '3324', 'ASSET', 'DEBIT', TRUE),
    ('33251', 'Costo', '3325', 'ASSET', 'DEBIT', TRUE),
    ('33252', 'Revaluación', '3325', 'ASSET', 'DEBIT', TRUE),
    ('33253', 'Costo de Financiación', '3325', 'ASSET', 'DEBIT', TRUE),
    ('33311', 'Costo', '3331', 'ASSET', 'DEBIT', TRUE),
    ('33312', 'Revaluación', '3331', 'ASSET', 'DEBIT', TRUE),
    ('33313', 'Costo de financiación', '3331', 'ASSET', 'DEBIT', TRUE),
    ('33411', 'Costo', '3341', 'ASSET', 'DEBIT', TRUE),
    ('33412', 'Revaluación', '3341', 'ASSET', 'DEBIT', TRUE),
    ('33421', 'Costo', '3342', 'ASSET', 'DEBIT', TRUE),
    ('33422', 'Revaluación', '3342', 'ASSET', 'DEBIT', TRUE),
    ('35111', 'Costo', '35', 'ASSET', 'DEBIT', TRUE),
    ('35113', 'Costo de financiación', '35', 'ASSET', 'DEBIT', TRUE),
    ('35114', 'Valor razonable', '35', 'ASSET', 'DEBIT', TRUE),
    ('35121', 'Costo', '3512', 'ASSET', 'DEBIT', TRUE),
    ('35123', 'Costo de financiación', '3512', 'ASSET', 'DEBIT', TRUE),
    ('35124', 'Valor razonable', '3512', 'ASSET', 'DEBIT', TRUE),
    ('35211', 'Costo', '3521', 'ASSET', 'DEBIT', TRUE),
    ('35213', 'Costo de financiación', '3521', 'ASSET', 'DEBIT', TRUE),
    ('35214', 'Valor razonable', '3521', 'ASSET', 'DEBIT', TRUE),
    ('35221', 'Costo', '3522', 'ASSET', 'DEBIT', TRUE),
    ('35223', 'Costo de financiación', '3522', 'ASSET', 'DEBIT', TRUE),
    ('35224', 'Valor razonable', '3522', 'ASSET', 'DEBIT', TRUE),
    ('36111', 'Costo', '3611', 'ASSET', 'CREDIT', TRUE),
    ('36112', 'Revaluación', '3611', 'ASSET', 'CREDIT', TRUE),
    ('36121', 'Costo', '3612', 'ASSET', 'CREDIT', TRUE),
    ('36122', 'Revaluación', '3612', 'ASSET', 'CREDIT', TRUE),
    ('36123', 'Costo de financiación', '3612', 'ASSET', 'CREDIT', TRUE),
    ('36131', 'Costo', '3613', 'ASSET', 'CREDIT', TRUE),
    ('36132', 'Revaluación', '3613', 'ASSET', 'CREDIT', TRUE),
    ('36133', 'Costo de financiación', '3613', 'ASSET', 'CREDIT', TRUE),
    ('36211', 'Costo', '3621', 'ASSET', 'CREDIT', TRUE),
    ('36212', 'Revaluación', '3621', 'ASSET', 'CREDIT', TRUE),
    ('36221', 'Costo', '3622', 'ASSET', 'CREDIT', TRUE),
    ('36222', 'Revaluación', '3622', 'ASSET', 'CREDIT', TRUE),
    ('36223', 'Costo de financiación', '3622', 'ASSET', 'CREDIT', TRUE),
    ('36311', 'Costo', '3631', 'ASSET', 'CREDIT', TRUE),
    ('36312', 'Revaluación', '3631', 'ASSET', 'CREDIT', TRUE),
    ('36321', 'Costo', '3632', 'ASSET', 'CREDIT', TRUE),
    ('36322', 'Revaluación', '3632', 'ASSET', 'CREDIT', TRUE),
    ('36323', 'Costo de financiación', '3632', 'ASSET', 'CREDIT', TRUE),
    ('36452', 'Revaluación', '364', 'ASSET', 'CREDIT', TRUE),
    ('36461', 'Costo', '3646', 'ASSET', 'CREDIT', TRUE),
    ('36462', 'Revaluación', '3646', 'ASSET', 'CREDIT', TRUE),
    ('36471', 'Herramientas - Costo', '3647', 'ASSET', 'CREDIT', TRUE),
    ('36472', 'Herramientas - Revaluación', '3647', 'ASSET', 'CREDIT', TRUE),
    ('36473', 'Unidades de reemplazo - costo', '3647', 'ASSET', 'CREDIT', TRUE),
    ('36474', 'Unidades de reemplazo - Revaluación', '3647', 'ASSET', 'CREDIT', TRUE),
    ('36491', 'Costo', '3649', 'ASSET', 'CREDIT', TRUE),
    ('36492', 'Revaluación', '3649', 'ASSET', 'CREDIT', TRUE),
    ('36511', 'Costo', '3651', 'ASSET', 'CREDIT', TRUE),
    ('36512', 'Revaluación', '3651', 'ASSET', 'CREDIT', TRUE),
    ('36521', 'Costo', '3652', 'ASSET', 'CREDIT', TRUE),
    ('36522', 'Revaluación', '3652', 'ASSET', 'CREDIT', TRUE),
    ('36531', 'Costo', '3653', 'ASSET', 'CREDIT', TRUE),
    ('36532', 'Revaluación', '3653', 'ASSET', 'CREDIT', TRUE),
    ('36541', 'Costo', '3654', 'ASSET', 'CREDIT', TRUE),
    ('36542', 'Revaluación', '3654', 'ASSET', 'CREDIT', TRUE),
    ('36543', 'Costo de financiación', '3654', 'ASSET', 'CREDIT', TRUE),
    ('36551', 'Costo', '3655', 'ASSET', 'CREDIT', TRUE),
    ('36552', 'Revaluación', '3655', 'ASSET', 'CREDIT', TRUE),
    ('36591', 'Costo', '3659', 'ASSET', 'CREDIT', TRUE),
    ('36592', 'Revaluación', '3659', 'ASSET', 'CREDIT', TRUE),
    ('36611', 'Costo', '3661', 'ASSET', 'CREDIT', TRUE),
    ('36613', 'Costo de financiación', '3661', 'ASSET', 'CREDIT', TRUE),
    ('36621', 'Costo', '3662', 'ASSET', 'CREDIT', TRUE),
    ('36622', 'Costo de financiación', '3662', 'ASSET', 'CREDIT', TRUE),
    ('36711', 'Costo', '3671', 'ASSET', 'CREDIT', TRUE),
    ('36721', 'Costo', '3672', 'ASSET', 'CREDIT', TRUE),
    ('36731', 'Costo', '3673', 'ASSET', 'CREDIT', TRUE),
    ('39111', 'Costo', '3911', 'ASSET', 'CREDIT', TRUE),
    ('39112', 'Revaluación', '3911', 'ASSET', 'CREDIT', TRUE),
    ('39113', 'Costo de financiación', '3911', 'ASSET', 'CREDIT', TRUE),
    ('39211', 'Costo', '3921', 'ASSET', 'CREDIT', TRUE),
    ('39212', 'Revaluación', '3921', 'ASSET', 'CREDIT', TRUE),
    ('39213', 'Costo de financiación', '3921', 'ASSET', 'CREDIT', TRUE),
    ('39321', 'Costo', '3932', 'ASSET', 'CREDIT', TRUE),
    ('39322', 'Revaluación', '3932', 'ASSET', 'CREDIT', TRUE),
    ('39323', 'Costo de financiación', '3932', 'ASSET', 'CREDIT', TRUE),
    ('39331', 'Costo', '3933', 'ASSET', 'CREDIT', TRUE),
    ('39332', 'Revaluación', '3933', 'ASSET', 'CREDIT', TRUE),
    ('39333', 'Costo de financiación', '3933', 'ASSET', 'CREDIT', TRUE),
    ('39611', 'Concesiones, licencias y otros derechos', '3961', 'ASSET', 'CREDIT', TRUE),
    ('39612', 'Patentes y propiedad industrial', '3961', 'ASSET', 'CREDIT', TRUE),
    ('39613', 'Programas de computadora (software)', '3961', 'ASSET', 'CREDIT', TRUE),
    ('39614', 'Costos de exploración y desarrollo', '3961', 'ASSET', 'CREDIT', TRUE),
    ('39615', 'Fórmulas, diseños y prototipos', '3961', 'ASSET', 'CREDIT', TRUE),
    ('39619', 'Otros activos intangibles', '3961', 'ASSET', 'CREDIT', TRUE),
    ('39621', 'Concesiones, licencias y otros derechos', '3962', 'ASSET', 'CREDIT', TRUE),
    ('39622', 'Patentes y propiedad industrial', '3962', 'ASSET', 'CREDIT', TRUE),
    ('39623', 'Programas de computadora (software)', '3962', 'ASSET', 'CREDIT', TRUE),
    ('39624', 'Costos de exploración y desarrollo', '3962', 'ASSET', 'CREDIT', TRUE),
    ('39625', 'Fórmulas, diseños y prototipos', '3962', 'ASSET', 'CREDIT', TRUE),
    ('39629', 'Otros activos intangibles', '3962', 'ASSET', 'CREDIT', TRUE),
    ('39633', 'Programas de computadora', '3963', 'ASSET', 'CREDIT', TRUE),
    ('39634', 'Costos de exploración', '3963', 'ASSET', 'CREDIT', TRUE),
    ('39635', 'Costos de desarrollo', '3963', 'ASSET', 'CREDIT', TRUE),
    ('39811', 'Activos biológicos en producción', '3981', 'ASSET', 'CREDIT', TRUE),
    ('40111', 'IGV – Cuenta propia', '4011', 'LIABILITY', 'CREDIT', TRUE),
    ('40112', 'IGV – Servicios prestados por no domiciliados', '4011', 'LIABILITY', 'CREDIT', TRUE),
    ('40113', 'IGV – Régimen de percepciones', '4011', 'LIABILITY', 'CREDIT', TRUE),
    ('40114', 'IGV – Régimen de retenciones', '4011', 'LIABILITY', 'CREDIT', TRUE),
    ('40115', 'IGV – Importaciones', '4011', 'LIABILITY', 'CREDIT', TRUE),
    ('40116', 'IGV – Destinado a operaciones gravadas', '4011', 'LIABILITY', 'CREDIT', TRUE),
    ('40117', 'IGV - Destinado a operaciones comunes', '4011', 'LIABILITY', 'CREDIT', TRUE),
    ('40151', 'Derechos arancelarios', '4015', 'LIABILITY', 'CREDIT', TRUE),
    ('40152', 'Otros derechos arancelarios', '4015', 'LIABILITY', 'CREDIT', TRUE),
    ('40171', 'Renta de tercera categoría', '4017', 'LIABILITY', 'CREDIT', TRUE),
    ('40172', 'Renta de cuarta categoría', '4017', 'LIABILITY', 'CREDIT', TRUE),
    ('40173', 'Renta de quinta categoría', '4017', 'LIABILITY', 'CREDIT', TRUE),
    ('40174', 'Renta de no domiciliados', '4017', 'LIABILITY', 'CREDIT', TRUE),
    ('40175', 'Otras retenciones', '4017', 'LIABILITY', 'CREDIT', TRUE),
    ('40181', 'Impuesto a las transacciones financieras', '4018', 'LIABILITY', 'CREDIT', TRUE),
    ('40182', 'Impuesto a los juegos de casino y tragamonedas', '4018', 'LIABILITY', 'CREDIT', TRUE),
    ('40183', 'Tasas por la prestación de servicios públicos', '4018', 'LIABILITY', 'CREDIT', TRUE),
    ('40184', 'Regalías', '4018', 'LIABILITY', 'CREDIT', TRUE),
    ('40185', 'Impuesto a los dividendos', '4018', 'LIABILITY', 'CREDIT', TRUE),
    ('40186', 'Impuesto temporal a los activos netos', '4018', 'LIABILITY', 'CREDIT', TRUE),
    ('40189', 'Otros impuestos', '4018', 'LIABILITY', 'CREDIT', TRUE),
    ('60935', 'Otros costos', '60', 'EXPENSE', 'DEBIT', TRUE),
    ('60941', 'Transporte', '6094', 'EXPENSE', 'DEBIT', TRUE),
    ('60942', 'Seguros', '6094', 'EXPENSE', 'DEBIT', TRUE),
    ('60943', 'Derechos aduaneros', '6094', 'EXPENSE', 'DEBIT', TRUE),
    ('60944', 'Comisiones', '6094', 'EXPENSE', 'DEBIT', TRUE),
    ('60945', 'Otros costos', '6094', 'EXPENSE', 'DEBIT', TRUE),
    ('65511', 'Inversiones mobiliarias', '6551', 'EXPENSE', 'DEBIT', TRUE),
    ('65512', 'Propiedades de inversión', '6551', 'EXPENSE', 'DEBIT', TRUE),
    ('65513', 'Activos por derecho de uso - arrendamiento financiero', '6551', 'EXPENSE', 'DEBIT', TRUE),
    ('65514', 'Propiedad, planta y equipo', '6551', 'EXPENSE', 'DEBIT', TRUE),
    ('65515', 'Intangibles', '6551', 'EXPENSE', 'DEBIT', TRUE),
    ('65516', 'Activos biológicos', '6551', 'EXPENSE', 'DEBIT', TRUE),
    ('65521', 'Propiedades de inversión', '6552', 'EXPENSE', 'DEBIT', TRUE),
    ('65522', 'Activos por derecho de uso - Arrendamiento financiero', '6552', 'EXPENSE', 'DEBIT', TRUE),
    ('65523', 'Propiedad, planta y equipo', '6552', 'EXPENSE', 'DEBIT', TRUE),
    ('65524', 'Intangibles', '6552', 'EXPENSE', 'DEBIT', TRUE),
    ('65525', 'Activos biológicos', '6552', 'EXPENSE', 'DEBIT', TRUE),
    ('66131', 'Propiedades de inversión', '6613', 'EXPENSE', 'DEBIT', TRUE),
    ('66132', 'Propiedad, planta y equipo', '6613', 'EXPENSE', 'DEBIT', TRUE),
    ('66133', 'Intangibles', '6613', 'EXPENSE', 'DEBIT', TRUE),
    ('66134', 'Activos biológicos', '6613', 'EXPENSE', 'DEBIT', TRUE),
    ('67311', 'Instituciones financieras', '6731', 'EXPENSE', 'DEBIT', TRUE),
    ('67312', 'Otras entidades', '6731', 'EXPENSE', 'DEBIT', TRUE),
    ('68111', 'Costo', '6811', 'EXPENSE', 'DEBIT', TRUE),
    ('68112', 'Revaluación', '6811', 'EXPENSE', 'DEBIT', TRUE),
    ('68113', 'Costo de financiación', '6811', 'EXPENSE', 'DEBIT', TRUE),
    ('68211', 'Edificaciones', '6821', 'EXPENSE', 'DEBIT', TRUE),
    ('68221', 'Edificaciones', '6822', 'EXPENSE', 'DEBIT', TRUE),
    ('68222', 'Maquinarias y equipos de explotación', '6822', 'EXPENSE', 'DEBIT', TRUE),
    ('68223', 'Unidades de transporte', '6822', 'EXPENSE', 'DEBIT', TRUE),
    ('68225', 'Equipos diversos', '6822', 'EXPENSE', 'DEBIT', TRUE),
    ('68311', 'Edificaciones', '6831', 'EXPENSE', 'DEBIT', TRUE),
    ('68312', 'Maquinarias y equipos de explotación', '6831', 'EXPENSE', 'DEBIT', TRUE),
    ('68313', 'Unidades de transporte', '6831', 'EXPENSE', 'DEBIT', TRUE),
    ('68315', 'Equipos diversos', '6831', 'EXPENSE', 'DEBIT', TRUE),
    ('68410', 'Plantas productoras', '6841', 'EXPENSE', 'DEBIT', TRUE),
    ('68411', 'Edificaciones', '6841', 'EXPENSE', 'DEBIT', TRUE),
    ('68412', 'Maquinarias y equipos de explotación', '6841', 'EXPENSE', 'DEBIT', TRUE),
    ('68413', 'Unidades de transporte', '6841', 'EXPENSE', 'DEBIT', TRUE),
    ('68414', 'Muebles y enseres', '6841', 'EXPENSE', 'DEBIT', TRUE),
    ('68415', 'Equipos diversos', '6841', 'EXPENSE', 'DEBIT', TRUE),
    ('68416', 'Herramientas y unidades de reemplazo', '6841', 'EXPENSE', 'DEBIT', TRUE),
    ('68420', 'Plantas productoras', '6842', 'EXPENSE', 'DEBIT', TRUE),
    ('68421', 'Edificaciones', '6842', 'EXPENSE', 'DEBIT', TRUE),
    ('68422', 'Maquinarias y equipos de explotación', '6842', 'EXPENSE', 'DEBIT', TRUE),
    ('68423', 'Unidades de transporte', '6842', 'EXPENSE', 'DEBIT', TRUE),
    ('68424', 'Muebles y enseres', '6842', 'EXPENSE', 'DEBIT', TRUE),
    ('68425', 'Equipos diversos', '6842', 'EXPENSE', 'DEBIT', TRUE),
    ('68426', 'Herramientas y unidades de reemplazo', '6842', 'EXPENSE', 'DEBIT', TRUE),
    ('68430', 'Plantas productoras', '6843', 'EXPENSE', 'DEBIT', TRUE),
    ('68431', 'Edificaciones', '6843', 'EXPENSE', 'DEBIT', TRUE),
    ('68432', 'Maquinarias y equipos de explotación', '6843', 'EXPENSE', 'DEBIT', TRUE),
    ('68511', 'Activos biológicos de origen animal', '6851', 'EXPENSE', 'DEBIT', TRUE),
    ('68512', 'Activos biológicos de origen vegetal', '6851', 'EXPENSE', 'DEBIT', TRUE),
    ('68521', 'Activos biológicos de origen animal', '6852', 'EXPENSE', 'DEBIT', TRUE),
    ('68522', 'Activos biológicos de origen vegetal', '6852', 'EXPENSE', 'DEBIT', TRUE),
    ('68611', 'Concesiones, licencias y otros derechos', '6861', 'EXPENSE', 'DEBIT', TRUE),
    ('68612', 'Patentes y propiedad industrial', '6861', 'EXPENSE', 'DEBIT', TRUE),
    ('68613', 'Programas de computadora (software)', '6861', 'EXPENSE', 'DEBIT', TRUE),
    ('68614', 'Costos de exploración y desarrollo', '6861', 'EXPENSE', 'DEBIT', TRUE),
    ('68615', 'Fórmulas, diseños y prototipos', '6861', 'EXPENSE', 'DEBIT', TRUE),
    ('68619', 'Otros activos intangibles', '6861', 'EXPENSE', 'DEBIT', TRUE),
    ('68621', 'Concesiones, licencias y otros derechos', '6862', 'EXPENSE', 'DEBIT', TRUE),
    ('68622', 'Patentes y propiedad industrial', '6862', 'EXPENSE', 'DEBIT', TRUE),
    ('68623', 'Programas de computadora (software)', '6862', 'EXPENSE', 'DEBIT', TRUE),
    ('68624', 'Costos de exploración y desarrollo', '6862', 'EXPENSE', 'DEBIT', TRUE),
    ('68625', 'Fórmulas, diseños y prototipos', '6862', 'EXPENSE', 'DEBIT', TRUE),
    ('68629', 'Otros activos intangibles', '6862', 'EXPENSE', 'DEBIT', TRUE),
    ('68711', 'Cuentas por cobrar comerciales – Terceros', '6871', 'EXPENSE', 'DEBIT', TRUE),
    ('68712', 'Cuentas por cobrar comerciales – Relacionadas', '6871', 'EXPENSE', 'DEBIT', TRUE),
    ('68713', 'Cuentas por cobrar al personal, a los accionistas (socios) y directores', '6871', 'EXPENSE', 'DEBIT', TRUE),
    ('68714', 'Cuentas por cobrar diversas – Terceros', '6871', 'EXPENSE', 'DEBIT', TRUE),
    ('68715', 'Cuentas por cobrar diversas – Relacionadas', '6871', 'EXPENSE', 'DEBIT', TRUE),
    ('68731', 'Inversiones a ser mantenidas hasta el vencimiento', '6873', 'EXPENSE', 'DEBIT', TRUE),
    ('68732', 'Instrumentos financieros representativos de derecho patrimonial', '6873', 'EXPENSE', 'DEBIT', TRUE),
    ('68812', 'Edificaciones', '688', 'EXPENSE', 'DEBIT', TRUE),
    ('68813', 'Construcciones en curso', '688', 'EXPENSE', 'DEBIT', TRUE),
    ('68820', 'Planta productora en producción', '6882', 'EXPENSE', 'DEBIT', TRUE),
    ('68821', 'Planta productora en desarrollo', '6882', 'EXPENSE', 'DEBIT', TRUE),
    ('68822', 'Terrenos', '6882', 'EXPENSE', 'DEBIT', TRUE),
    ('68823', 'Edificaciones', '6882', 'EXPENSE', 'DEBIT', TRUE),
    ('68824', 'Maquinarias y equipos de explotación', '6882', 'EXPENSE', 'DEBIT', TRUE),
    ('68825', 'Unidades de transporte', '6882', 'EXPENSE', 'DEBIT', TRUE),
    ('68826', 'Muebles y enseres', '6882', 'EXPENSE', 'DEBIT', TRUE),
    ('68827', 'Equipos diversos', '6882', 'EXPENSE', 'DEBIT', TRUE),
    ('68828', 'Herramientas y unidades de reemplazo', '6882', 'EXPENSE', 'DEBIT', TRUE),
    ('68830', 'Planta productora en producción', '6883', 'EXPENSE', 'DEBIT', TRUE),
    ('68831', 'Planta productora en desarrollo', '6883', 'EXPENSE', 'DEBIT', TRUE),
    ('68832', 'Terrenos', '6883', 'EXPENSE', 'DEBIT', TRUE),
    ('68833', 'Edificaciones', '6883', 'EXPENSE', 'DEBIT', TRUE),
    ('68834', 'Maquinarias y equipos de explotación', '6883', 'EXPENSE', 'DEBIT', TRUE),
    ('68835', 'Unidades de transporte', '6883', 'EXPENSE', 'DEBIT', TRUE),
    ('68836', 'Muebles y enseres', '6883', 'EXPENSE', 'DEBIT', TRUE),
    ('68837', 'Equipos diversos', '6883', 'EXPENSE', 'DEBIT', TRUE),
    ('68838', 'Herramientas y unidades de reemplazo', '6883', 'EXPENSE', 'DEBIT', TRUE),
    ('68841', 'Concesiones, licencias y otros derechos', '6884', 'EXPENSE', 'DEBIT', TRUE),
    ('68842', 'Patentes y propiedad industrial', '6884', 'EXPENSE', 'DEBIT', TRUE),
    ('68843', 'Programas de computadora (software)', '6884', 'EXPENSE', 'DEBIT', TRUE),
    ('68844', 'Costos de exploración y desarrollo', '6884', 'EXPENSE', 'DEBIT', TRUE),
    ('68845', 'Fórmulas, diseños y prototipos', '6884', 'EXPENSE', 'DEBIT', TRUE),
    ('68846', 'Otros activos intangibles', '6884', 'EXPENSE', 'DEBIT', TRUE),
    ('68847', 'Plusvalía mercantil', '6884', 'EXPENSE', 'DEBIT', TRUE),
    ('68891', 'Activos biológicos de origen animal', '6889', 'EXPENSE', 'DEBIT', TRUE),
    ('68892', 'Activos biológicos de origen vegetal', '6889', 'EXPENSE', 'DEBIT', TRUE),
    ('68911', 'Provisión para litigios – Costo', '6891', 'EXPENSE', 'DEBIT', TRUE),
    ('68912', 'Provisión para litigios – Actualización financiera', '6891', 'EXPENSE', 'DEBIT', TRUE),
    ('68921', 'Provisión por desmantelamiento, retiro o rehabilitación del inmovilizado – Costo', '6892', 'EXPENSE', 'DEBIT', TRUE),
    ('68922', 'Provisión por desmantelamiento, retiro o rehabilitación del inmovilizado – Actualización financiera', '6892', 'EXPENSE', 'DEBIT', TRUE),
    ('68941', 'Provisión para protección y remediación del medio ambiente – Costo', '6894', 'EXPENSE', 'DEBIT', TRUE),
    ('68942', 'Provisión para protección y remediación del medio ambiente – Actualización financiera', '6894', 'EXPENSE', 'DEBIT', TRUE),
    ('68961', 'Provisión para garantías – Costo', '6896', 'EXPENSE', 'DEBIT', TRUE),
    ('68962', 'Provisión para garantías – Actualización financiera', '6896', 'EXPENSE', 'DEBIT', TRUE),
    ('68971', 'Provisión por activos por derecho de uso arrendamiento operativo', '6897', 'EXPENSE', 'DEBIT', TRUE),
    ('68972', 'Provisión por activos por derecho de uso arrendamiento operativo - actualización financiera', '6897', 'EXPENSE', 'DEBIT', TRUE),
    ('70111', 'Terceros', '7011', 'INCOME', 'CREDIT', TRUE),
    ('70112', 'Relacionadas', '7011', 'INCOME', 'CREDIT', TRUE),
    ('70211', 'Terceros', '7021', 'INCOME', 'CREDIT', TRUE),
    ('70212', 'Relacionadas', '7021', 'INCOME', 'CREDIT', TRUE),
    ('70221', 'Terceros', '7022', 'INCOME', 'CREDIT', TRUE),
    ('70222', 'Relacionadas', '7022', 'INCOME', 'CREDIT', TRUE),
    ('70311', 'Terceros', '7031', 'INCOME', 'CREDIT', TRUE),
    ('70312', 'Relacionadas', '7031', 'INCOME', 'CREDIT', TRUE),
    ('70321', 'Terceros', '7032', 'INCOME', 'CREDIT', TRUE),
    ('70322', 'Relacionadas', '7032', 'INCOME', 'CREDIT', TRUE),
    ('70411', 'Terceros', '7041', 'INCOME', 'CREDIT', TRUE),
    ('70412', 'Relacionadas', '7041', 'INCOME', 'CREDIT', TRUE),
    ('70421', 'Terceros', '7042', 'INCOME', 'CREDIT', TRUE),
    ('70422', 'Relacionadas', '7042', 'INCOME', 'CREDIT', TRUE),
    ('70911', 'Terceros', '7091', 'INCOME', 'CREDIT', TRUE),
    ('70912', 'Relacionadas', '7091', 'INCOME', 'CREDIT', TRUE),
    ('70921', 'Terceros', '7092', 'INCOME', 'CREDIT', TRUE),
    ('70922', 'Relacionadas', '7092', 'INCOME', 'CREDIT', TRUE),
    ('70931', 'Terceros', '7093', 'INCOME', 'CREDIT', TRUE),
    ('70932', 'Relacionadas', '7093', 'INCOME', 'CREDIT', TRUE),
    ('70941', 'Terceros', '7094', 'INCOME', 'CREDIT', TRUE),
    ('70942', 'Relacionadas', '7094', 'INCOME', 'CREDIT', TRUE),
    ('70951', 'Terceros', '7095', 'INCOME', 'CREDIT', TRUE),
    ('70952', 'Relacionadas', '7095', 'INCOME', 'CREDIT', TRUE),
    ('70961', 'Terceros', '7096', 'INCOME', 'CREDIT', TRUE),
    ('70962', 'Relacionadas', '7096', 'INCOME', 'CREDIT', TRUE),
    ('72542', 'Activos biológicos de origen vegetal', '725', 'INCOME', 'CREDIT', TRUE);
DO $$
DECLARE target_plan_id BIGINT;admin_id BIGINT;code_len INTEGER;
BEGIN
  SELECT id INTO target_plan_id FROM public.accounting_plans WHERE code='PCGE_PE' AND edition='Modificado 2019';
  SELECT id INTO admin_id FROM public.users WHERE role='ADMIN' ORDER BY id LIMIT 1;
  IF (SELECT count(*) FROM _pcge_seed)<>1192 THEN RAISE EXCEPTION 'PCGE seed row count is invalid'; END IF;
  IF EXISTS(SELECT 1 FROM _pcge_seed s LEFT JOIN _pcge_seed p ON p.code=s.parent_code WHERE s.parent_code IS NOT NULL AND p.code IS NULL)
    THEN RAISE EXCEPTION 'PCGE seed has missing parent references'; END IF;
  FOR code_len IN 2..5 LOOP
    INSERT INTO public.accounting_accounts(plan_id,code,name,parent_account_id,account_group,normal_balance,is_postable,status,effective_from,created_by)
    SELECT target_plan_id,s.code,s.name,p.id,s.account_group,s.normal_balance,s.is_postable,'ACTIVE',DATE '2019-01-01',admin_id
      FROM _pcge_seed s LEFT JOIN public.accounting_accounts p ON p.plan_id=target_plan_id AND p.code=s.parent_code
     WHERE length(s.code)=code_len ORDER BY s.code
    ON CONFLICT(plan_id,code) DO NOTHING;
  END LOOP;
  IF (SELECT count(*) FROM public.accounting_accounts WHERE plan_id=target_plan_id)<1192
    THEN RAISE EXCEPTION 'PCGE seed did not load every account'; END IF;
END $$;

COMMIT;
