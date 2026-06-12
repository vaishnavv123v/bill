


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





def is_probable_ocr_garbage(word):
    w = word.lower()

    # Ignore short words
    if len(w) < 8:
        return False

    # Pure alphabetic suspicious tokens
    if re.fullmatch(r'[a-z]+', w):

        # Too many repeated chars overall
        repeated = sum(
            1 for i in range(1, len(w))
            if w[i] == w[i - 1]
        )

        # Low unique character diversity
        unique_ratio = len(set(w)) / len(w)

        # Weird consonant/vowel imbalance
        vowels = sum(c in 'aeiou' for c in w)
        vowel_ratio = vowels / len(w)

        # OCR garbage heuristics
        if (
            repeated >= len(w) * 0.25 or
            unique_ratio < 0.45 or
            vowel_ratio < 0.20 or
            vowel_ratio > 0.75
        ):
            return True

        # Detect repeating fragments
        if re.search(r'(..+?)\1{2,}', w):
            return True

    return False


def clean_junk_text(text):

    cleaned_lines = []

    for line in text.splitlines():

        words = []

        for word in line.split():

            # Remove long repeated punctuation
            word = re.sub(r'([^\w\s])\1{2,}', r'\1', word)

            # Compress excessive repeated letters
            word = re.sub(r'([a-zA-Z])\1{3,}', r'\1\1', word)

            # Remove OCR garbage words
            if is_probable_ocr_garbage(word):
                continue

            words.append(word)

        cleaned_line = ' '.join(words).strip()

        if cleaned_line:
            cleaned_lines.append(cleaned_line)

    return '\n'.join(cleaned_lines)
    """
    Safer OCR junk cleaner.
    Preserves real words while removing obvious OCR garbage.
    """

    cleaned_words = []

    for word in text.split():

        original = word

        # Remove long repeated punctuation/noise
        word = re.sub(r'([^\w\s])\1{2,}', r'\1', word)

        # Compress excessive repeated letters
        # coooooool -> cool
        word = re.sub(r'([a-zA-Z])\1{3,}', r'\1\1', word)

        lower = word.lower()

        # Remove suspicious OCR garbage tokens
        if re.fullmatch(r'[a-z]{8,}', lower):

            vowels = sum(c in 'aeiou' for c in lower)
            vowel_ratio = vowels / len(lower)

            # Likely OCR junk:
            # very low vowels + many unique/random chars
            if vowel_ratio < 0.25:
                continue

            # Remove highly repetitive nonsense
            if len(set(lower)) <= 3:
                continue

        cleaned_words.append(word)

    # Normalize spaces
    cleaned_text = ' '.join(cleaned_words)
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text)

    return cleaned_text.strip()


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
                    name = clean_junk_text(name)

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


def generate_ai_analysis(items):
    import os
    import json
    import urllib.request
    import urllib.error
    from django.conf import settings

    # -----------------------------
    # Load API Key
    # -----------------------------
    env_vars = {}

    try:
        env_path = os.path.join(settings.BASE_DIR, ".env")

        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()

                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env_vars[k.strip()] = v.strip().strip('"').strip("'")

    except Exception as e:
        print(f"Error reading .env: {e}")

    api_key = (
        os.environ.get("GROQ_API")
        or env_vars.get("GROQ_API")
        or os.environ.get("GROQ_API_KEY")
        or env_vars.get("GROQ_API_KEY")
        or getattr(settings, "GROQ_API", "")
        or getattr(settings, "GROQ_API_KEY", "")
    )

    # -----------------------------
    # RULES
    # -----------------------------
    NON_CLAIMABLE = ["admin", "registration", "tax", "gst", "surcharge"]

    ROOM_RELATED = ["room", "board", "bed", "ward", "icu", "suite", "stay", "accommodation"]

    SERVICE_RELATED = ["doctor", "consultation", "visit", "surgery", "operation", "procedure", "nursing"]

    def get_category(name):
        n = name.lower()
        if any(x in n for x in ROOM_RELATED):
            return "room"
        if any(x in n for x in SERVICE_RELATED):
            return "service"
        return "standard"

    def insurance_status(name):
        return "claimable" if not any(x in name.lower() for x in NON_CLAIMABLE) else "not claimable"

    # -----------------------------
    # BUILD ITEMS
    # -----------------------------
    items_list = []

    for item in items:
        name = item.item_name
        charged = float(item.charged_price)
        standard = float(item.standard_price) if item.standard_price else None
        qty = item.quantity

        category = get_category(name)
        ins = insurance_status(name)

        if standard is None or standard == 0:
            price_status = "Unknown"

        elif category in ["room", "service"]:
            price_status = "Hospital Dependent"

        else:
            ratio = charged / standard

            if ratio <= 1.10:
                price_status = "Fair"
            elif ratio <= 1.30:
                price_status = "Slightly High"
            else:
                price_status = "High"

        items_list.append({
            "name": name,
            "charged_price": charged,
            "standard_price": standard,
            "quantity": qty,
            "price_status": price_status,
            "insurance_status": ins
        })

    # -----------------------------
    # HUMAN READABLE FALLBACK (IMPORTANT)
    # -----------------------------
    def fallback_text(item):
        name = item["name"]
        status = item["price_status"]
        qty = item["quantity"]
        ins = item["insurance_status"]

        if status == "Unknown":
            return (
                f"{name} was billed {qty} time(s). "
                f"No standard reference price is available for comparison. "
                f"This item is generally {ins} under insurance policies."
            )

        if status == "Hospital Dependent":
            return (
                f"{name} was billed {qty} time(s). "
                f"This type of charge varies based on hospital policies, room type, "
                f"and treatment complexity. It is generally {ins}."
            )

        if status == "Fair":
            return (
                f"{name} was billed {qty} time(s). "
                f"The charge appears reasonable compared to standard reference pricing. "
                f"This item is generally {ins}."
            )

        if status == "Slightly High":
            return (
                f"{name} was billed {qty} time(s). "
                f"The charge is slightly higher than expected reference pricing. "
                f"This may be reviewed. It is generally {ins}."
            )

        return (
            f"{name} was billed {qty} time(s). "
            f"The charge appears significantly higher than reference pricing and should be reviewed. "
            f"It is generally {ins}."
        )

    # -----------------------------
    # NO API KEY → fallback
    # -----------------------------
    if not api_key:
        return {i["name"]: fallback_text(i) for i in items_list}

    # -----------------------------
    # AI PROMPT (ONLY FOR LANGUAGE)
    # -----------------------------
    prompt = f"""
You are a hospital billing explanation assistant.

IMPORTANT RULES:
- Do NOT calculate prices.
- Do NOT change meaning of price_status.
- Convert into simple patient-friendly sentences.
- 1–2 sentences max.
- No labels like Fair/High/Unknown.
- No "Qty", no codes, no bullet points.
- Must mention insurance when relevant.

SPECIAL RULE:
If price_status is "Hospital Dependent",
explain that charges vary by hospital and are not strictly overpriced.

Return ONLY valid JSON.

Items:
{json.dumps(items_list, indent=2)}
"""

    try:
        url = "https://api.groq.com/openai/v1/chat/completions"

        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": "Return only JSON."},
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=20) as response:
            if response.status == 200:

                result = json.loads(response.read().decode("utf-8"))
                content = result["choices"][0]["message"]["content"]
                ai_data = json.loads(content)

                cleaned = {
                    k.strip().lower(): v.strip()
                    for k, v in ai_data.items()
                }

                final = {}

                for item in items_list:
                    key = item["name"].lower()
                    final[item["name"]] = cleaned.get(key) or fallback_text(item)

                return final

    except Exception as e:
        print("AI error:", e)

    # -----------------------------
    # FINAL FALLBACK
    # -----------------------------
    return {i["name"]: fallback_text(i) for i in items_list}


# ─────────────────────────────
# EMAIL DRAFT GENERATION
# ─────────────────────────────
def generate_complaint_email_draft(complaint_type, description, hospital_name=None, bill_amount=None, bill_items=None, transparency_score=None, total_overcharge=None, fraud_risk=None):
    """Generate AI-powered email draft for complaint with detailed bill analysis context"""
    import os
    import json
    import urllib.request
    from django.conf import settings

    # Load API Key
    env_vars = {}
    try:
        env_path = os.path.join(settings.BASE_DIR, ".env")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env_vars[k.strip()] = v.strip().strip('"').strip("'")
    except Exception as e:
        print(f"Error reading .env: {e}")

    api_key = (
        os.environ.get("GROQ_API")
        or env_vars.get("GROQ_API")
        or os.environ.get("GROQ_API_KEY")
        or env_vars.get("GROQ_API_KEY")
        or getattr(settings, "GROQ_API", "")
        or getattr(settings, "GROQ_API_KEY", "")
    )

    # Build context with detailed bill analysis
    context = f"""
Complaint Type: {complaint_type}
Description: {description}
"""
    if hospital_name:
        context += f"Hospital Name: {hospital_name}\n"
    if bill_amount:
        context += f"Total Bill Amount: ₹{bill_amount}\n"
    if transparency_score is not None:
        context += f"Transparency Score: {transparency_score}%\n"
    if total_overcharge is not None and total_overcharge > 0:
        context += f"Total Overcharge Amount: ₹{total_overcharge}\n"
    if fraud_risk:
        context += f"Fraud Risk Level: {fraud_risk}\n"

    if bill_items:
        context += "\nBill Items with Analysis:\n"
        overcharged_items = [item for item in bill_items if item.get('overcharge_percent', 0) > 20]
        if overcharged_items:
            context += "Overcharged Items:\n"
            for item in overcharged_items[:5]:  # Limit to top 5 overcharged items
                context += f"- {item.get('item_name', 'Unknown')}: Charged ₹{item.get('charged_price', 0)}, Standard ₹{item.get('standard_price', 0)}, Overcharge {item.get('overcharge_percent', 0):.1f}%\n"
        else:
            context += "All items appear to be reasonably priced.\n"

    # Fallback template with detailed context
    fallback_draft = f"""Subject: Formal Complaint Regarding {complaint_type.title()} - {hospital_name or 'Hospital'}

Dear Sir/Madam,

I am writing to formally file a complaint regarding {complaint_type}.

{description}

"""
    if bill_amount:
        fallback_draft += f"Total Bill Amount: ₹{bill_amount}\n\n"
    if transparency_score is not None:
        fallback_draft += f"Transparency Score: {transparency_score}%\n"
    if total_overcharge is not None and total_overcharge > 0:
        fallback_draft += f"Total Overcharge Detected: ₹{total_overcharge}\n"
    if fraud_risk:
        fallback_draft += f"Fraud Risk Assessment: {fraud_risk}\n"

    if bill_items and any(item.get('overcharge_percent', 0) > 20 for item in bill_items):
        fallback_draft += "\nSpecific Overcharged Items:\n"
        for item in [item for item in bill_items if item.get('overcharge_percent', 0) > 20][:5]:
            fallback_draft += f"- {item.get('item_name')}: Charged ₹{item.get('charged_price')} vs Standard ₹{item.get('standard_price')} ({item.get('overcharge_percent', 0):.1f}% overcharge)\n"

    fallback_draft += """
I request that this matter be investigated and appropriate action be taken. I am available for further discussion and can provide additional documentation if required.

Please acknowledge receipt of this complaint and inform me of the next steps.

Sincerely,
[Your Name]
[Your Contact Information]
[Patient ID/Admission Number]
"""

    if not api_key:
        return fallback_draft

    prompt = f"""
Generate a professional, formal email draft for a healthcare complaint. Use the following detailed analysis:

{context}

Requirements:
- Professional and formal tone
- Include specific details about overcharged items if present
- Mention transparency score and fraud risk if available
- Clear and concise but comprehensive
- Include appropriate subject line
- Include placeholders for sender's name, contact info, and patient ID
- Suitable for sending to hospital management or regulatory authorities
- Structure: Introduction → Issue Details → Specific Concerns → Request for Action → Closing

Return ONLY the email draft (no explanations, no JSON).
"""

    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": "You are a professional complaint letter writer. Return only the email draft, no explanations."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=20) as response:
            if response.status == 200:
                result = json.loads(response.read().decode("utf-8"))
                content = result["choices"][0]["message"]["content"]
                return content.strip()

    except Exception as e:
        print("AI email generation error:", e)

    return fallback_draft