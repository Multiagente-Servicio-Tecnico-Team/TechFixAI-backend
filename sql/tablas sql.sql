--
-- PostgreSQL database dump
--

-- Dumped from database version 17.4
-- Dumped by pg_dump version 17.4

-- Started on 2026-11-04 00:18:17

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
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


ALTER TYPE public.diagnosis_type_enum OWNER TO postgres;

--
-- TOC entry 942 (class 1247 OID 19812)
-- Name: logistics_mode_enum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.logistics_mode_enum AS ENUM (
    'PHYSICAL_STORE',
    'COURIER_SHIPMENT'
);


ALTER TYPE public.logistics_mode_enum OWNER TO postgres;

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


ALTER TYPE public.logistics_status_enum OWNER TO postgres;

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


ALTER TYPE public.notification_type_enum OWNER TO postgres;

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


ALTER TYPE public.payment_method_enum OWNER TO postgres;

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


ALTER TYPE public.payment_status_enum OWNER TO postgres;

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


ALTER TYPE public.quote_status_enum OWNER TO postgres;

--
-- TOC entry 927 (class 1247 OID 19760)
-- Name: quote_type_enum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.quote_type_enum AS ENUM (
    'REPAIR',
    'DIRECT_SALE',
    'PC_BUILD'
);


ALTER TYPE public.quote_type_enum OWNER TO postgres;

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


ALTER TYPE public.refund_status_enum OWNER TO postgres;

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


ALTER TYPE public.request_type_enum OWNER TO postgres;

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


ALTER TYPE public.ticket_status_enum OWNER TO postgres;

--
-- TOC entry 915 (class 1247 OID 19709)
-- Name: user_role_enum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.user_role_enum AS ENUM (
    'CUSTOMER',
    'TECHNICIAN',
    'ADMIN'
);


ALTER TYPE public.user_role_enum OWNER TO postgres;

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


ALTER TYPE public.warranty_claim_status_enum OWNER TO postgres;

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


ALTER TYPE public.warranty_status_enum OWNER TO postgres;

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


ALTER FUNCTION public.accounting_check_entry_balance() OWNER TO postgres;

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


ALTER FUNCTION public.accounting_guard_entry_update() OWNER TO postgres;

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


ALTER FUNCTION public.accounting_reject_mutation() OWNER TO postgres;

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


ALTER FUNCTION public.update_updated_at_column() OWNER TO postgres;

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


ALTER TABLE public.accounting_audit_events OWNER TO postgres;

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


ALTER TABLE public.accounting_categories OWNER TO postgres;

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


ALTER TABLE public.accounting_entries OWNER TO postgres;

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


ALTER TABLE public.accounting_entry_lines OWNER TO postgres;

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


ALTER TABLE public.customer_audit_events OWNER TO postgres;

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


ALTER TABLE public.customers OWNER TO postgres;

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
    movement_type character varying(20) NOT NULL,
    code_snapshot character varying(50) NOT NULL,
    name_snapshot character varying(150) NOT NULL,
    quantity_delta integer NOT NULL,
    stock_before integer NOT NULL,
    stock_after integer NOT NULL,
    actor_user_id bigint NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    sales_order_item_id bigint,
    CONSTRAINT chk_inventory_movements_nonzero_delta CHECK ((quantity_delta <> 0)),
    CONSTRAINT chk_inventory_movements_origin_xor CHECK (((purchase_receipt_item_id IS NOT NULL) <> (sales_order_item_id IS NOT NULL))),
    CONSTRAINT chk_inventory_movements_stock_after CHECK (((stock_after = (stock_before + quantity_delta)) AND (stock_after >= 0))),
    CONSTRAINT chk_inventory_movements_type_origin CHECK (((((movement_type)::text = 'PURCHASE_RECEIPT'::text) AND (purchase_receipt_item_id IS NOT NULL) AND (quantity_delta > 0)) OR (((movement_type)::text = 'SALE'::text) AND (sales_order_item_id IS NOT NULL) AND (quantity_delta < 0)))),
    CONSTRAINT inventory_movements_check CHECK ((stock_after = (stock_before + quantity_delta))),
    CONSTRAINT inventory_movements_stock_before_check CHECK ((stock_before >= 0))
);


ALTER TABLE public.inventory_movements OWNER TO postgres;

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


ALTER TABLE public.inventory_reservation_items OWNER TO postgres;

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


ALTER TABLE public.inventory_reservations OWNER TO postgres;

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


ALTER TABLE public.logistics_records OWNER TO postgres;

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


ALTER TABLE public.payments OWNER TO postgres;

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


ALTER TABLE public.purchase_order_items OWNER TO postgres;

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


ALTER TABLE public.purchase_orders OWNER TO postgres;

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


ALTER TABLE public.purchase_receipt_items OWNER TO postgres;

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


ALTER TABLE public.purchase_receipts OWNER TO postgres;

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


ALTER TABLE public.quote_audit_events OWNER TO postgres;

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


ALTER TABLE public.quote_details OWNER TO postgres;

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
    CONSTRAINT chk_quotes_ticket_kind CHECK ((((quote_type = 'DIRECT_SALE'::public.quote_type_enum) AND (ticket_id IS NULL)) OR ((quote_type <> 'DIRECT_SALE'::public.quote_type_enum) AND (ticket_id IS NOT NULL))))
);


ALTER TABLE public.quotes OWNER TO postgres;

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


ALTER TABLE public.recovery_tokens OWNER TO postgres;

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


ALTER TABLE public.refunds OWNER TO postgres;

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


ALTER TABLE public.sales_order_items OWNER TO postgres;

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


ALTER TABLE public.sales_orders OWNER TO postgres;

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


ALTER TABLE public.schema_migrations OWNER TO postgres;

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


ALTER TABLE public.spare_parts OWNER TO postgres;

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


ALTER TABLE public.supplier_purchase_audit_events OWNER TO postgres;

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


ALTER TABLE public.supplier_purchase_items OWNER TO postgres;

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


ALTER TABLE public.supplier_purchases OWNER TO postgres;

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


ALTER TABLE public.suppliers OWNER TO postgres;

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


ALTER TABLE public.ticket_audit_events OWNER TO postgres;

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


ALTER TABLE public.tickets OWNER TO postgres;

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


ALTER TABLE public.users OWNER TO postgres;

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


ALTER TABLE public.warranties OWNER TO postgres;

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


ALTER TABLE public.warranty_claims OWNER TO postgres;

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

