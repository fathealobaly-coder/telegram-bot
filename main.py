import os
import json
import hmac
import hashlib
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)


# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

PUBLIC_BASE_URL = os.environ["PUBLIC_BASE_URL"].rstrip("/")

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

NOWPAYMENTS_API_KEY = os.environ["NOWPAYMENTS_API_KEY"]
NOWPAYMENTS_IPN_SECRET = os.environ.get(
    "NOWPAYMENTS_IPN_SECRET",
    "",
)

# Bucket used for digital products
SUPABASE_STORAGE_BUCKET = os.environ.get(
    "SUPABASE_STORAGE_BUCKET",
    "digital-products",
)


# ============================================================
# TELEGRAM APPLICATION
# ============================================================

telegram_app = (
    Application.builder()
    .token(BOT_TOKEN)
    .updater(None)
    .build()
)


# ============================================================
# SUPABASE
# ============================================================

def supabase_headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


async def supabase_get(
    table: str,
    params: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    url = f"{SUPABASE_URL}/rest/v1/{table}"

    query_params = dict(params or {})

    if not query_params.get("select"):
        query_params["select"] = "*"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                url,
                headers=supabase_headers(),
                params=query_params,
            )

        print(
            f"SUPABASE GET "
            f"table={table} "
            f"status={response.status_code}"
        )

        if response.is_error:
            print(
                "SUPABASE ERROR RESPONSE:",
                response.text
            )
            raise RuntimeError(
                f"Supabase GET failed: "
                f"HTTP {response.status_code}: "
                f"{response.text}"
            )

        try:
            data = response.json()
        except Exception as exc:
            print("SUPABASE JSON ERROR:", repr(exc))
            print("SUPABASE RAW RESPONSE:", response.text)
            raise

        if not isinstance(data, list):
            print("SUPABASE UNEXPECTED RESPONSE:", repr(data))
            raise RuntimeError("Supabase response is not a JSON list.")

        return data

    except httpx.HTTPError as exc:
        print("SUPABASE HTTPX ERROR:", repr(exc))
        raise


async def supabase_patch(
    table: str,
    params: dict[str, str],
    data: dict[str, Any],
) -> list[dict[str, Any]]:
    url = f"{SUPABASE_URL}/rest/v1/{table}"

    headers = supabase_headers()
    headers["Prefer"] = "return=representation"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.patch(
                url,
                headers=headers,
                params=params,
                json=data,
            )

        print(
            f"SUPABASE PATCH "
            f"table={table} "
            f"status={response.status_code}"
        )

        if response.is_error:
            print(
                "SUPABASE PATCH ERROR:",
                response.text
            )
            raise RuntimeError(
                f"Supabase PATCH failed: "
                f"HTTP {response.status_code}: "
                f"{response.text}"
            )

        result = response.json()

        if not isinstance(result, list):
            return []

        return result

    except httpx.HTTPError as exc:
        print("SUPABASE PATCH HTTPX ERROR:", repr(exc))
        raise


# ============================================================
# TELEGRAM /start
# ============================================================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.effective_message:
        return

    await update.effective_message.reply_text(
        "مرحباً بك.\n\n"
        "البوت يعمل بنجاح.\n\n"
        "/products - عرض المنتجات\n"
        "/status - حالة البوت"
    )


# ============================================================
# TELEGRAM /status
# ============================================================

async def status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.effective_message:
        return

    await update.effective_message.reply_text(
        "البوت يعمل بنجاح عبر FastAPI و Telegram Webhook."
    )


# ============================================================
# TELEGRAM /products
# ============================================================

async def products_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.effective_message:
        return

    try:
        # المحاولة الأولى: مع فلتر active=true
        try:
            products = await supabase_get(
                "products",
                {
                    "select": "*",
                    "active": "eq.true",
                    "order": "created_at.asc",
                },
            )
        except Exception as first_error:
            print("PRODUCTS FILTERED QUERY FAILED:", repr(first_error))
            print("Retrying products query without active filter...")
            
            # المحاولة الثانية: استعلام مرن بدون فلتر active
            products = await supabase_get(
                "products",
                {
                    "select": "*",
                },
            )

        if not products:
            await update.effective_message.reply_text(
                "لا توجد منتجات متاحة حالياً."
            )
            print("PRODUCTS: query succeeded but returned 0 rows.")
            return

        lines = ["المنتجات المتاحة:\n"]

        for product in products:
            name = (
                product.get("name")
                or product.get("title")
                or product.get("product_name")
                or "منتج بدون اسم"
            )

            price = (
                product.get("price_usd")
                or product.get("price")
                or product.get("amount")
                or "غير محدد"
            )

            currency = (
                product.get("pay_currency")
                or product.get("currency")
                or "USD"
            )

            description = product.get("description") or ""

            line = f"• {name}\nالسعر: {price} {currency}"
            if description:
                line += f"\n{description}"

            lines.append(line)

        await update.effective_message.reply_text("\n\n".join(lines))
        print(f"PRODUCTS SUCCESS: {len(products)} product(s) returned.")

    except Exception as exc:
        print("PRODUCTS ERROR:", repr(exc))
        await update.effective_message.reply_text(
            "حدث خطأ أثناء قراءة المنتجات.\n"
            "تم تسجيل تفاصيل الخطأ في Railway Logs."
        )


# ============================================================
# REGISTER TELEGRAM HANDLERS
# ============================================================

telegram_app.add_handler(CommandHandler("start", start_command))
telegram_app.add_handler(CommandHandler("products", products_command))
telegram_app.add_handler(CommandHandler("status", status_command))


# ============================================================
# DIGITAL PRODUCT DELIVERY
# ============================================================

async def deliver_order(order: dict[str, Any]) -> None:
    order_id = order.get("id")
    telegram_user_id = order.get("telegram_user_id")
    product_id = order.get("product_id")

    if not telegram_user_id:
        raise ValueError("Order has no telegram_user_id.")

    if not product_id:
        raise ValueError("Order has no product_id.")

    products = await supabase_get(
        "products",
        {
            "select": "*",
            "id": f"eq.{product_id}",
            "limit": "1",
        },
    )

    if not products:
        raise ValueError(f"Product not found: {product_id}")

    product = products[0]
    storage_path = product.get("storage_path")

    if not storage_path:
        raise ValueError(f"Product {product_id} has no storage_path.")

    storage_url = (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"{SUPABASE_STORAGE_BUCKET}/"
        f"{storage_path}"
    )

    print(f"Downloading product file: {storage_path}")

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.get(
            storage_url,
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            },
        )

    if response.is_error:
        print("STORAGE DOWNLOAD ERROR:", response.status_code, response.text)
        raise RuntimeError(f"Storage download failed: HTTP {response.status_code}")

    filename = storage_path.split("/")[-1]

    await telegram_app.bot.send_document(
        chat_id=int(telegram_user_id),
        document=response.content,
        filename=filename,
        caption=(
            "تم تأكيد الدفع بنجاح.\n"
            "إليك المنتج المطلوب."
        ),
    )

    print(f"DELIVERY SUCCESS: order={order_id}, telegram={telegram_user_id}, file={storage_path}")


# ============================================================
# NOWPAYMENTS SIGNATURE
# ============================================================

def verify_nowpayments_signature(
    raw_body: bytes,
    received_signature: str | None,
) -> bool:
    if not NOWPAYMENTS_IPN_SECRET:
        print("WARNING: NOWPAYMENTS_IPN_SECRET is not configured.")
        return False

    if not received_signature:
        print("NOWPAYMENTS: Missing x-nowpayments-sig header.")
        return False

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        print("NOWPAYMENTS JSON ERROR:", repr(exc))
        return False

    signed_payload = json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
    )

    expected_signature = hmac.new(
        NOWPAYMENTS_IPN_SECRET.encode("utf-8"),
        signed_payload.encode("utf-8"),
        hashlib.sha512,
    ).hexdigest()

    valid = hmac.compare_digest(expected_signature, received_signature)
    if not valid:
        print("NOWPAYMENTS: INVALID SIGNATURE")

    return valid


# ============================================================
# NOWPAYMENTS IPN PROCESSOR
# ============================================================

async def process_nowpayments_ipn(payload: dict[str, Any]) -> None:
    print("NOWPAYMENTS IPN RECEIVED:", json.dumps(payload, ensure_ascii=False))

    status = str(payload.get("payment_status", "")).lower()
    payment_id = payload.get("payment_id") or payload.get("id")

    if not payment_id:
        print("NOWPAYMENTS IPN ignored: payment_id missing.")
        return

    if status not in {"finished", "confirmed"}:
        print(f"NOWPAYMENTS status={status}; no delivery.")
        return

    orders = await supabase_get(
        "orders",
        {
            "select": "*",
            "invoice_id": f"eq.{payment_id}",
            "limit": "1",
        },
    )

    if not orders:
        print(f"No order found for payment_id={payment_id}")
        return

    order = orders[0]

    if order.get("payment_status") == "CONFIRMED":
        print(f"Order {order.get('id')} is already CONFIRMED.")
        return

    updated = await supabase_patch(
        "orders",
        {"id": f"eq.{order['id']}"},
        {"payment_status": "CONFIRMED"},
    )

    if not updated:
        raise RuntimeError("Failed to update order to CONFIRMED.")

    confirmed_order = updated[0]
    await deliver_order(confirmed_order)


# ============================================================
# FASTAPI LIFESPAN
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting Telegram application...")
    await telegram_app.initialize()
    await telegram_app.start()

    webhook_url = f"{PUBLIC_BASE_URL}/webhook"
    await telegram_app.bot.set_webhook(
        url=webhook_url,
        allowed_updates=Update.ALL_TYPES,
    )
    print(f"Telegram webhook configured: {webhook_url}")

    yield

    print("Stopping Telegram application...")
    try:
        await telegram_app.bot.delete_webhook()
    except Exception as exc:
        print("Webhook delete warning:", repr(exc))

    await telegram_app.stop()
    await telegram_app.shutdown()


# ============================================================
# FASTAPI APP
# ============================================================

app = FastAPI(
    title="Telegram Digital Store",
    lifespan=lifespan,
)


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "telegram-bot",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "telegram_webhook": "/webhook",
        "nowpayments_webhook": "/webhook/nowpayments",
    }


@app.post("/webhook")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        update = Update.de_json(data, bot=telegram_app.bot)
        await telegram_app.update_queue.put(update)
        return JSONResponse({"ok": True})
    except Exception as exc:
        print("TELEGRAM WEBHOOK ERROR:", repr(exc))
        raise HTTPException(
            status_code=400,
            detail="Invalid Telegram update",
        )


@app.post("/webhook/nowpayments")
async def nowpayments_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("x-nowpayments-sig")

    if not verify_nowpayments_signature(raw_body, signature):
        raise HTTPException(
            status_code=401,
            detail="Invalid NOWPayments signature",
        )

    try:
        payload = json.loads(raw_body.decode("utf-8"))
        await process_nowpayments_ipn(payload)
        return JSONResponse({"ok": True})
    except HTTPException:
        raise
    except Exception as exc:
        print("NOWPAYMENTS WEBHOOK ERROR:", repr(exc))
        raise HTTPException(
            status_code=500,
            detail="Webhook processing failed",
        )


# ============================================================
# RAILWAY ENTRYPOINT
# ============================================================

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
    )
