#!/usr/bin/env python3

# pip install fastapi uvicorn

from fastapi import FastAPI, HTTPException
from typing import List, Dict

# pro make_operation_id
import re
from fastapi.routing import APIRoute

# varianta s podporou stránkování
from typing import Optional
from fastapi import Query

# pro mock tiketů z json pro user id:4
import json
from pathlib import Path
#BIG_TICKETS_PATH = Path("mockdata/customer4.json")
BIG_TICKETS_PATH = Path("mockdata/customer4_anonymized.json")


# =========================
# MOCK DATA
# =========================

customers = [
    {"id": 1, "first_name": "Jan", "last_name": "Novák"},
    {"id": 2, "first_name": "Petr", "last_name": "Svoboda"},
    {"id": 3, "first_name": "Eva", "last_name": "Králová"},
    {"id": 4, "first_name": "Petr", "last_name": "Baláž"},
]

tickets = {
    1: [
        {"ticket_id": 101, "issue": "Internet nefunguje"},
        {"ticket_id": 102, "issue": "Pomalé připojení"},
    ],
    2: [
        {"ticket_id": 201, "issue": "Výpadky signálu"},
    ],
    3: [
        {"ticket_id": 301, "issue": "Nejde televize"},
        {"ticket_id": 302, "issue": "Špatná kvalita obrazu"},
        {"ticket_id": 303, "issue": "Chybí kanály"},
    ],
}

payments = {
    1: [
        {"invoice_id": 1001, "amount": 500, "status": "paid"},
        {"invoice_id": 1002, "amount": 450, "status": "unpaid"},
    ],
    2: [
        {"invoice_id": 2001, "amount": 300, "status": "paid"},
    ],
    3: [
        {"invoice_id": 3001, "amount": 700, "status": "unpaid"},
        {"invoice_id": 3002, "amount": 700, "status": "unpaid"},
    ],
    4: [
        {"invoice_id": 4001, "amount": 349, "status": "paid"},
        {"invoice_id": 4002, "amount": 349, "status": "paid"},
        {"invoice_id": 4003, "amount": 349, "status": "canceled"},
        {"invoice_id": 4004, "amount": 349, "status": "unpaid"},
    ],
}


# =========================
# pomocná funkce pro lepší automatické generování operationId
# defaultně srstavuje operationId: {název funkce}_{path}_{metoda}, tedy např. get_customer_by_lastname_customer_by_lastname_get
# =========================

seen_operation_ids = set()  # jen pko kontrolu unik8tnosti/duplicit

def make_operation_id(route: APIRoute) -> str:
    # HTTP metoda (GET, POST…)
    method = list(route.methods)[0].lower()

    # rozpad path
    parts = route.path.strip("/").split("/")

    # odstranění {param} + normalizace
    clean_parts = []
    for p in parts:
        if p.startswith("{"):
            continue
        p = p.replace("-", "_")
        p = re.sub(r'[^a-zA-Z0-9_]', '', p)
        clean_parts.append(p)

    # fallback když je path prázdná
    base = "_".join(clean_parts) if clean_parts else route.name.lower()

    name = f"{method}_{base}"

    # ochrana proti kolizím
    original = name
    i = 1
    while name in seen_operation_ids:
        print(f"Duplicate operationId: {name}")
        i += 1
        name = f"{original}_{i}"

    seen_operation_ids.add(name)

    return name


# =========================
# FASTAPI APP
# =========================

# Používám vlastní generátor operationId, aby názvy endpointů byly krátké, konzistentní
# a vhodné pro LLM tool calling (místo defaultních FastAPI názvů).
# Případný override lze udělat přímo v @app.get(..., operation_id="...")

app = FastAPI(
    title="Customer Demo API",
    description="Simple demo API for MCS tool chaining",
    generate_unique_id_function=make_operation_id,  # override auto-gen operationId
    version="1.0.0"
)


# =========================
# ENDPOINTS
# =========================

@app.get("/customer/by-lastname")
def get_customer_by_lastname(last_name: str):
    """
    Find customer by last name.
    Returns customer_id.
    """
    for c in customers:
        if c["last_name"].lower() == last_name.lower():
            return {
                "customer_id": c["id"],
                "first_name": c["first_name"],
                "last_name": c["last_name"]
            }

    raise HTTPException(status_code=404, detail="Customer not found")


# varianta bez podpory stránkování (vrací vše do max. limitu)
#@app.get("/tickets")
#def get_tickets(customer_id: int):
#    """
#    Returns support tickets for given customer_id.
#    """
#
#    # special case: customer_id == 4 -> load large dataset
#    if customer_id == 4:
#        try:
#            with open(BIG_TICKETS_PATH, "r", encoding="utf-8") as f:
#                data = json.load(f)
#
#            all_tickets = data.get("allTickets", [])
#
#            total = len(all_tickets)
#            limit = int(total * 0.20) # 20% dat
#
#            return {
#                "customer_id": customer_id,
#                "total": total,
#                "returned": limit,
#                "tickets": all_tickets  #[:limit] -- ne chci vúplně všechny
#            }
#
#        except Exception as e:
#            raise HTTPException(status_code=500, detail=f"Failed to load big tickets: {e}")
#
#    return {
#        "customer_id": customer_id,
#        "tickets": tickets.get(customer_id, [])
#    }


# varianta s podporou stránkování (vrací vše do max. limitu) a vrácení počtu
@app.get("/tickets")
def get_tickets(
    customer_id: int,
    offset: Optional[int] = Query(None, ge=0),
    limit: Optional[int] = Query(None, ge=1),
    meta_only: bool = Query(False)
):
    """
    Returns support tickets for given customer_id.
    """

    # special case: customer_id == 4 -> load large dataset
    # 1) ZÍSKÁNÍ DAT (jediné místo, kde se liší)
    if customer_id == 4:
        try:
            with open(BIG_TICKETS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)

            all_tickets = data.get("allTickets", [])
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to load big tickets: {e}")
    else:
        all_tickets = tickets.get(customer_id, [])

    # 2) META (pro všechny stejně)
    total = len(all_tickets)
    tokens_estimation = len(json.dumps(all_tickets)) // 4

    if meta_only:
        return {
            "customer_id": customer_id,
            "data_path": "tickets",  # klíč, kde se nachází data pro stránkování (lze dot notation např. "items.tickets")
            "tokens_estimation": tokens_estimation,
            "total_items": total
        }

    # 3) PAGINATION (pro všechny stejně)
    if offset is not None and limit is not None:
        if offset >= total:
            tickets_out = []
        else:
            tickets_out = all_tickets[offset: offset + limit]
    else:
        tickets_out = all_tickets

    return {
        "customer_id": customer_id,
        "tickets": tickets_out
    }


@app.get("/payments")
def get_payments(customer_id: int):
    """
    Returns billing/payment history for given customer_id.
    """
    return {
        "customer_id": customer_id,
        "payments": payments.get(customer_id, [])
    }

