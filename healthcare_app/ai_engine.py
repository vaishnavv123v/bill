


"""
AI Analysis Engine - FIXED & FINAL VERSION
"""

import re
import os
import joblib
import pandas as pd
import numpy as np
import cv2
from PIL import Image

import pytesseract
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

from pdf2image import convert_from_path
import pdfplumber
from fuzzywuzzy import process

# ─────────────────────────────
# ML MODEL
# ─────────────────────────────
MODEL_PATH = os.path.join(os.path.dirname(__file__), 'ml_models', 'fraud_model.pkl')

try:
    FRAUD_MODEL = joblib.load(MODEL_PATH)
except:
    FRAUD_MODEL = None


# ─────────────────────────────
# STANDARD PRICE DB
# ─────────────────────────────


STANDARD_PRICES = {
    "room": 1500,
    "nursing": 800,
    "nursing fees": 800,
    "ot charge": 25000,
    "major ot": 30000,
    "operation theatre": 25000,
    "injection": 150,
    "nebulization": 300,
    "blood transfusion": 1500,
    "professional fees": 2000,
    "doctor fees": 1500,
    "consultation": 500,
    "lab test": 400,
    "x ray": 800,
    "scan": 3000,
    "mri scan": 3000,
    "ct scan": 2500,
    "x-ray": 800,
    "blood test": 300,
    "complete blood count": 400,
    "paracetamol": 20,
    "consultation": 500,
    "injection": 150,
    "minor surgery": 5000,
    "major surgery": 30000,
    "ward charges": 1000,
    "room charges": 2000,
    "nursing charges": 500,
}



# ─────────────────────────────
# OCR
# ─────────────────────────────
def preprocess_image(file_path):
    img = np.array(Image.open(file_path))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
    return thresh


def ocr_extract_text(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    text = ""

    try:
        if ext in [".png", ".jpg", ".jpeg"]:
            text = pytesseract.image_to_string(
                preprocess_image(file_path),
                config="--oem 3 --psm 6"
            )

        elif ext == ".pdf":
            try:
                with pdfplumber.open(file_path) as pdf:
                    text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            except:
                pass

            if not text.strip():
                images = convert_from_path(file_path)
                for img in images:
                    text += pytesseract.image_to_string(img)

    except Exception as e:
        print("OCR ERROR:", e)

    return text


# ─────────────────────────────
# METADATA EXTRACTION
# ─────────────────────────────
def extract_metadata(text):
    meta = {
        "hospital_name": "Unknown Hospital",
        "patient_name": "N/A",
        "invoice_number": "N/A",
        "admission_date": "N/A",
        "discharge_date": "N/A",
    }

    lines = text.split("\n")

    if lines:
        meta["hospital_name"] = lines[0].strip()

    return meta


# ─────────────────────────────
# ITEM EXTRACTION
# ─────────────────────────────



def extract_data(text):
    items = []
    hospital_name = "Unknown Hospital"
    bill_date = None

    lines = [line.strip() for line in text.split('\n') if line.strip()]

    skip_list = [
        'subtotal', 'total', 'balance', 'payable', 'paid',
        'address', 'patient', 'date', 'phone',
        'admission', 'discharge', 'due', 'bill'
    ]

    for line in lines:
        lower = line.lower()

        # HOSPITAL NAME
        if hospital_name == "Unknown Hospital":
            if any(kw in lower for kw in ['hospital', 'clinic', 'medical']):
                cleaned = re.sub(r'[^A-Za-z\s]', ' ', line)
                cleaned = " ".join(cleaned.split())
                cleaned = re.sub(r'\d+', '', cleaned)

                if 5 < len(cleaned) < 60:
                    hospital_name = cleaned.strip()

        # DATE
        if not bill_date:
            date_match = re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', line)
            if date_match:
                bill_date = date_match.group(0)

        # ITEM
        clean_line = re.sub(r'[₹$,]', '', line)
        numbers = re.findall(r'\d+(?:\.\d+)?', clean_line)

        # if numbers:
        if numbers and any(c.isalpha() for c in line):
            try:
                price = sorted([float(n) for n in numbers if 10 <= float(n) <= 50000])[-1]


                if 100 <= price <= 500000:
                    name_part = clean_line
                    for n in numbers:
                        name_part = name_part.replace(n, '', 1)

                    name = re.sub(r'[^A-Za-z\s]', ' ', name_part)
                    name = " ".join(name.split())

                    if len(name) > 5 and not any(w in name.lower() for w in skip_list):
                    
                        # Handle discount
                        if "discount" in name.lower():
                            price = -abs(price)

                        items.append({
                            "name": name,
                            "quantity": 1,
                            "charged_price": price
                        })

            except:
                continue

    return {
        "analyzed_items": items,
        "hospital_name": hospital_name,
        "bill_date": bill_date,
    }




# ─────────────────────────────
# STANDARD PRICE
# ─────────────────────────────
def get_standard_price(name):
    name = name.lower()
    match = process.extractOne(name, list(STANDARD_PRICES.keys()))

    if match and match[1] > 70:
        return STANDARD_PRICES[match[0]]

    return None


# ─────────────────────────────
# ANALYSIS
# ─────────────────────────────





def analyze_items(items):
    analyzed = []

    for item in items:
        name = item.get("name", "Unknown")
        qty = item.get("quantity", 1)
        price = item.get("charged_price", 0)

        std = get_standard_price(name)

        if std is not None and std > 0:
            diff = price - std
            pct = (diff / std) * 100
            flag = "overcharged" if pct > 50 else "suspicious" if pct > 20 else "normal"
        else:
            pct = 0
            flag = "unknown"

        analyzed.append({
            "name": name,
            "quantity": qty,
            "charged_price": price,
            "standard_price": std,
            "overcharge_pct": round(pct, 2),
            "flag": flag
        })

    return analyzed




# ─────────────────────────────
# TOTAL EXTRACTION
# ─────────────────────────────

def extract_total_from_text(text):
    if not text:
        return None

    clean = text.replace(',', '').replace('₹', '').replace('¥', '').replace('$', '').upper()
    lines = clean.split('\n')

    total_keywords = ["TOTAL BL AT", "TOTAL BILL", "AMOUNT PAYABLE", "AOT PAYABLE", 
                      "NET AMOUNT", "BALANCE", "SUBTOTAL", "AMOUNT DUE", "PAYABLE", "DUE"]

    for line in lines:
        if any(kw in line for kw in total_keywords):
            nums = re.findall(r'\d+\.?\d*', line)
            if nums:
                total = float(nums[-1])
                if total > 100:
                    print(f"✅ STRONG TOTAL FOUND: ₹{total}")
                    return total

    # Fallback - largest reasonable number
    all_nums = re.findall(r'\d{4,}', clean)
    if all_nums:
        candidates = [float(n) for n in all_nums if 500 < float(n) < 2000000]
        if candidates:
            best_total = max(candidates)
            print(f"✅ FALLBACK TOTAL: ₹{best_total}")
            return best_total

    print("⚠ No reliable total found in text")
    return None




# ─────────────────────────────
# FRAUD DETECTION
# ─────────────────────────────
def detect_fraud(analyzed_items, total_amount, hospital_name):
    score = sum(1 for i in analyzed_items if i["flag"] == "overcharged") * 20

    risk = "high" if score >= 60 else "medium" if score >= 30 else "low"

    return {
        "fraud_score": score,
        "risk_level": risk,
        "suspicious_count": sum(1 for i in analyzed_items if i["flag"] != "normal")
    }


# ─────────────────────────────
# MAIN PIPELINE (FIXED)
# ─────────────────────────────



def run_full_analysis(file_path, hospital_name=""):

    text = ocr_extract_text(file_path)

    # SINGLE SOURCE OF TRUTH
    extracted = extract_data(text)

    raw_items = extracted.get("analyzed_items", [])
    hospital_name = extracted.get("hospital_name", hospital_name)
    bill_date = extracted.get("bill_date")

    analyzed = analyze_items(raw_items)

    # ── TOTAL
    extracted_total = extract_total_from_text(text)

    if not extracted_total or extracted_total < 100:
        extracted_total = sum(
            i["charged_price"] * i["quantity"] for i in analyzed
        )

    # ── STANDARD TOTAL
    total_standard_amount = sum(
        (i.get("standard_price") or i["charged_price"]) * i["quantity"]
        for i in analyzed
    )

    # ── TRANSPARENCY SCORE
    if extracted_total > 0:
        transparency_score = round((total_standard_amount / extracted_total) * 100)
        transparency_score = max(0, min(100, transparency_score))
    else:
        transparency_score = 100

    # ── FRAUD
    fraud = detect_fraud(analyzed, extracted_total, hospital_name)

    # ── OVERCHARGE
    total_overcharge = sum(
        max(0, i["charged_price"] - (i.get("standard_price") or i["charged_price"]))
        for i in analyzed
    )

    return {
        "analyzed_items": analyzed,
        "fraud_info": fraud,
        "transparency_score": transparency_score,
        "total_overcharge": round(total_overcharge, 2),
        "total_standard_amount": round(total_standard_amount, 2),
        "extracted_total": extracted_total,
        "hospital_name": hospital_name,
        "bill_date": bill_date,
        "recommendations": (
            ["Check flagged items"]
            if fraud.get("fraud_score", 0) > 20
            else ["Bill appears fair"]
        ),
    }



# ─────────────────────────────
# INSURANCE MODEL
# ─────────────────────────────
def predict_insurance_claim(claim_amount, bill_total, fraud_risk, transparency_score):

    prob = 85

    if fraud_risk == "high":
        prob -= 40
    elif fraud_risk == "medium":
        prob -= 20

    if transparency_score < 50:
        prob -= 20

    if claim_amount > bill_total:
        prob -= 30

    prob = max(5, min(95, prob))

    reasons = []

    if fraud_risk != "low":
        reasons.append("Fraud risk detected")

    if transparency_score < 60:
        reasons.append("Low transparency")

    if claim_amount > bill_total:
        reasons.append("Claim exceeds bill")

    return {
        "approval_probability": round(prob, 1),
        "rejection_reasons": reasons or ["No major issues"]
    }




