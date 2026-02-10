import os
import uuid
import time
import threading
from typing import Dict, Any

import requests
from flask import Flask, request, jsonify, redirect
import qrcode

# =========================
# CONFIG (set env vars)
# =========================
SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "").strip()
SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "").strip()

# Public base URL of THIS server (for return_url and webhook).
# Example with ngrok: https://abcd-12-34-56-78.ngrok-free.app
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").strip()

# YooKassa API base
API_BASE = "https://api.yookassa.ru/v3"

if not SHOP_ID or not SECRET_KEY:
    raise SystemExit(
        "Please set env vars: YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY (TEST store credentials)."
    )

app = Flask(__name__)

# In-memory order state (for testing).
# In production you’d store this in DB.
orders: Dict[str, Dict[str, Any]] = {}
events: Dict[str, threading.Event] = {}


def create_sbp_payment(amount_rub: str, description: str, order_id: str) -> Dict[str, Any]:
    """
    Creates an SBP payment in YooKassa.
    Returns YooKassa payment object (JSON).
    """
    idempotence_key = str(uuid.uuid4())

    payload = {
        "amount": {"value": amount_rub, "currency": "RUB"},
        "payment_method_data": {"type": "bank_card"},
        "confirmation": {
            "type": "redirect",
            "return_url": f"{PUBLIC_BASE_URL}/return/{order_id}",
        },
        "capture": True,
        "description": description,
        "metadata": {
            "order_id": order_id,
        },
    }

    r = requests.post(
        f"{API_BASE}/payments",
        auth=(SHOP_ID, SECRET_KEY),
        headers={
            "Idempotence-Key": idempotence_key,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    #r.raise_for_status()
    #return r.json()

    if not r.ok:
        return {
            "http_status": r.status_code,
            "error_text": r.text,
            "request_payload": payload,
        }
    return r.json()


def make_qr_png(url: str, out_path: str) -> None:
    img = qrcode.make(url)
    img.save(out_path)


@app.get("/create-test-payment")
def http_create_test_payment():
    """
    Create a test payment and return JSON with the link + where QR was saved.
    Visit:
      http://localhost:8000/create-test-payment?amount=2.00
    """
    amount = request.args.get("amount", "2.00")
    order_id = str(uuid.uuid4())

    orders[order_id] = {
        "status": "created",
        "yookassa_payment_id": None,
        "confirmation_url": None,
        "paid": False,
    }
    events[order_id] = threading.Event()

    payment = create_sbp_payment(
        amount_rub=amount,
        description=f"Test subscription order {order_id}",
        order_id=order_id,
    )

    if "http_status" in payment:
        return jsonify(payment), 400

    confirmation_url = payment.get("confirmation", {}).get("confirmation_url")
    payment_id = payment.get("id")

    orders[order_id].update(
        {
            "status": payment.get("status"),
            "yookassa_payment_id": payment_id,
            "confirmation_url": confirmation_url,
            "paid": payment.get("paid", False),
        }
    )

    qr_path = f"qr_{order_id}.png"
    if confirmation_url:
        make_qr_png(confirmation_url, qr_path)

    return jsonify(
        {
            "order_id": order_id,
            "payment_id": payment_id,
            "status": orders[order_id]["status"],
            "confirmation_url": confirmation_url,
            "qr_png": qr_path,
            "wait_url": f"{PUBLIC_BASE_URL}/wait/{order_id}",
            "status_url": f"{PUBLIC_BASE_URL}/status/{order_id}",
        }
    )


@app.post("/webhook")
def yookassa_webhook():
    """
    YooKassa will POST events here.
    For a test harness we keep it simple:
      - if event == payment.succeeded => mark paid
    """
    data = request.get_json(force=True, silent=False)

    event_type = data.get("event")
    obj = data.get("object", {})
    payment_id = obj.get("id")
    status = obj.get("status")
    metadata = obj.get("metadata", {})
    order_id = metadata.get("order_id")

    # Basic sanity checks
    if not order_id or order_id not in orders:
        return jsonify({"ok": True, "ignored": True}), 200

    # Update stored state
    orders[order_id]["status"] = status
    orders[order_id]["yookassa_payment_id"] = payment_id
    orders[order_id]["paid"] = bool(obj.get("paid", False))

    if event_type == "payment.succeeded" and status == "succeeded":
        orders[order_id]["paid"] = True
        if order_id in events:
            events[order_id].set()

    return jsonify({"ok": True}), 200


@app.get("/wait/<order_id>")
def wait_paid(order_id: str):
    """
    Blocks (long-poll) until payment is marked paid (webhook) or timeout.
    """
    if order_id not in orders:
        return jsonify({"error": "unknown order_id"}), 404

    # wait up to 5 minutes
    ok = events[order_id].wait(timeout=300)

    return jsonify(
        {
            "order_id": order_id,
            "paid": orders[order_id]["paid"],
            "status": orders[order_id]["status"],
            "webhook_received": ok,
        }
    )


@app.get("/status/<order_id>")
def get_status(order_id: str):
    if order_id not in orders:
        return jsonify({"error": "unknown order_id"}), 404
    return jsonify({"order_id": order_id, **orders[order_id]})


@app.get("/return/<order_id>")
def return_from_payment(order_id: str):
    """
    User returns here after payment.
    We don't trust this alone — it’s just UX.
    Real confirmation comes from webhook.
    """
    if order_id not in orders:
        return "Unknown order.", 404

    # Show simple message / redirect somewhere
    if orders[order_id]["paid"]:
        return "Payment successful ✅ (confirmed by webhook)."
    return (
        "Thanks! If you already paid, please wait a moment for confirmation and refresh this page."
    )


if __name__ == "__main__":
    # Run local server
    app.run(host="0.0.0.0", port=8000, debug=True)

