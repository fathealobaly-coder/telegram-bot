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
NOWPAYMENTS_IPN_SECRET = os.environ.get("NOWPAYMENTS_IPN_SECRET", "")

# Optional: keep this if already used by your Railway project
NOWPAYMENTS_API_URL = "https://api.nowpayments.io/v1"


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
# SUPABASE HELPERS
# ============================================================

def supabase_headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


async def supabase_get(
    table: str,
    params: dict[str, str],
) -> list[dict[str, Any]]:
    url = f"{SUPABASE_URL}/rest/v1/{table}"

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            url,
            headers=supabase_headers(),
            params=params,
        )

    response.raise_for_status()
    return response.json()


async def supabase_patch(
    table: str,
    params: dict[str, str],
    data: dict[str, Any],
) -> list[dict[str, Any]]:
    url = f"{SUPABASE_URL}/rest/v1/{table}"

    headers = supabase_headers()
    headers["Prefer"] = "return=representation"

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.patch(
            url,
            headers=headers,
            params=params,
            json=data,
        )

    response.raise_for_status()
    return response.json()


# ============================================================
# TELEGRAM COMMANDS
# ============================================================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    if not update.effective_message:
        return

    await update.effective_message.reply_text(
        "مرحباً بك.\n\n"
        "البوت يعمل بنجاح.\n"
        "/products - عرض المنتجات\n"
        "/status - فحص حالة البوت"
    )


async def products_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    if not update.effective_message:
        return

    try:
        products = await supabase_get(
            "products",
            {
                "select": "id,name,description,price_usd,pay_currency,active",
                "active": "eq.true",
                "order": "created_at.asc",
            },
        )

        if not products:
            await update.effective_message.reply_text(
                "لا توجد منتجات متاحة حالياً."
            )
            return

        lines = ["المنتجات المتاحة:\n"]

        for product in products:
            lines.append(
                f"• {product['name']}\n"
                f"السعر: ${product['price_usd']} "
                f"{product['pay_currency']}\n"
            )

        await update.effective_message.reply_text(
            "\n".join(lines)
        )

    except Exception as exc:
        print("PRODUCTS ERROR:", repr(exc))

        await update.effective_message.reply_text(
            "حدث خطأ أثناء قراءة المنتجات."
        )


async def status_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    if not update.effective_message:
        return

    await update.effective_message.reply_text(
        "البوت يعمل، وFastAPI وTelegram Webhook قيد التشغيل."
    )


# ============================================================
# REGISTER TELEGRAM HANDLERS
# ============================================================

telegram_app.add_handler(
    CommandHandler("start", start_command)
)

telegram_app.add_handler(
    CommandHandler("products", products_command)
)

telegram_app.add_handler(
    CommandHandler("status", status_command)
)


# ============================================================
# DIGITAL PRODUCT DELIVERY
# ============================================================

async def deliver_order(order: dict[str, Any]) -> None:

    order_id = order.get("id")
    telegram_user_id = order.get("telegram_user_id")
    product_id = order.get("product_id")

    if not telegram_user_id:
        raise ValueError("Order has no telegram_user_id")

    if not product_id:
        raise ValueError("Order has no product_id")

    # --------------------------------------------------------
    # Get product
    # --------------------------------------------------------

    products = await supabase_get(
        "products",
        {
            "select": "id,name,storage_path",
            "id": f"eq.{product_id}",
            "limit": "1",
        },
    )

    if not products:
        raise ValueError(
            f"Product not found: {product_id}"
        )

    product = products[0]

    storage_path = product.get("storage_path")

    if not storage_path:
        raise ValueError(
            f"Product {product_id} has no storage_path"
        )

    # --------------------------------------------------------
    # Download file from Supabase Storage
    # --------------------------------------------------------

    storage_url = (
        f"{SUPABASE_URL}/storage/v1/object/"
        f"digital-products/{storage_path}"
    )

    async with httpx.AsyncClient(timeout=120) as client:

        file_response = await client.get(
            storage_url,
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization":
                    f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            },
        )

    file_response.raise_for_status()

    filename = storage_path.split("/")[-1]

    # --------------------------------------------------------
    # Send document to Telegram
    # --------------------------------------------------------

    await telegram_app.bot.send_document(
        chat_id=int(telegram_user_id),
        document=file_response.content,
        filename=filename,
        caption=(
            "تم تأكيد الدفع بنجاح.\n"
            "إليك المنتج المطلوب."
        ),
    )

    print(
        f"DELIVERY SUCCESS "
        f"order={order_id} "
        f"telegram={telegram_user_id} "
        f"file={storage_path}"
    )


# ============================================================
# NOWPAYMENTS SIGNATURE VERIFICATION
# ============================================================

def verify_nowpayments_signature(
    raw_body: bytes,
    received_signature: str | None,
) -> bool:

    if not NOWPAYMENTS_IPN_SECRET:
        print("WARNING: NOWPAYMENTS_IPN_SECRET is not configured.")
        return False

    if not received_signature:
        return False

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
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

    return hmac.compare_digest(
        expected_signature,
        received_signature,
    )


# ============================================================
# NOWPAYMENTS WEBHOOK
# ============================================================

async def process_nowpayments_ipn(
    payload: dict[str, Any],
) -> None:

    status = str(
        payload.get("payment_status", "")
    ).lower()

    payment_id = (
        payload.get("payment_id")
        or payload.get("id")
    )

    print(
        "NOWPAYMENTS IPN:",
        json.dumps(payload, ensure_ascii=False)
    )

    if not payment_id:
        print("IPN ignored: no payment_id")
        return

    if status not in {
        "finished",
        "confirmed",
    }:
        print(
            f"IPN received but not deliverable: {status}"
        )
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
        print(
            f"No order found for payment_id={payment_id}"
        )
        return

    order = orders[0]

    if order.get("payment_status") == "CONFIRMED":
        print(
            f"Order {order.get('id')} already CONFIRMED."
        )
        return

    updated = await supabase_patch(
        "orders",
        {
            "id": f"eq.{order['id']}",
        },
        {
            "payment_status": "CONFIRMED",
        },
    )

    if not updated:
        raise RuntimeError(
            "Order confirmation update failed."
        )

    order = updated[0]

    await deliver_order(order)


# ============================================================
# FASTAPI LIFECYCLE
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    print("Starting Telegram application...")

    await telegram_app.initialize()
    await telegram_app.start()

    webhook_url = (
        f"{PUBLIC_BASE_URL}/webhook"
    )

    await telegram_app.bot.set_webhook(
        url=webhook_url,
        allowed_updates=Update.ALL_TYPES,
    )

    print(
        f"Telegram webhook configured: {webhook_url}"
    )

    yield

    print("Stopping Telegram application...")

    await telegram_app.bot.delete_webhook()

    await telegram_app.stop()
    await telegram_app.shutdown()


# ============================================================
# FASTAPI APP
# ============================================================

app = FastAPI(
    title="Telegram Digital Store",
    lifespan=lifespan,
)


# ============================================================
# HEALTH CHECK
# ============================================================

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


# ============================================================
# TELEGRAM WEBHOOK
# ============================================================

@app.post("/webhook")
async def telegram_webhook(request: Request):

    try:
        data = await request.json()

        update = Update.de_json(
            data,
            bot=telegram_app.bot,
        )

        await telegram_app.update_queue.put(update)

        return JSONResponse(
            {
                "ok": True,
            }
        )

    except Exception as exc:

        print(
            "TELEGRAM WEBHOOK ERROR:",
            repr(exc)
        )

        raise HTTPException(
            status_code=400,
            detail="Invalid Telegram update",
        )


# ============================================================
# NOWPAYMENTS WEBHOOK
# ============================================================

@app.post("/webhook/nowpayments")
async def nowpayments_webhook(
    request: Request,
):

    raw_body = await request.body()

    signature = request.headers.get(
        "x-nowpayments-sig"
    )

    if not verify_nowpayments_signature(
        raw_body,
        signature,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid NOWPayments signature",
        )

    try:
        payload = json.loads(
            raw_body.decode("utf-8")
        )

        await process_nowpayments_ipn(
            payload
        )

        return JSONResponse(
            {
                "ok": True,
            }
        )

    except HTTPException:
        raise

    except Exception as exc:

        print(
            "NOWPAYMENTS WEBHOOK ERROR:",
            repr(exc)
        )

        raise HTTPException(
            status_code=500,
            detail="Webhook processing failed",
        )


# ============================================================
# RAILWAY ENTRYPOINT
# ============================================================

if __name__ == "__main__":

    import uvicorn

    port = int(
        os.environ.get(
            "PORT",
            "8080",
        )
    )

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
    )
