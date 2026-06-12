import re

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import Sum, Count

from .models import Bill, BillItem, AnalysisReport, InsuranceClaim, Complaint, UserProfile
from .forms import RegisterForm, BillUploadForm, InsuranceClaimForm, ComplaintForm
from .ai_engine import run_full_analysis, predict_insurance_claim, generate_ai_analysis, generate_complaint_email_draft
from .models import Notification


# ─── Auth Views ───────────────────────────────────────────────────────────────



def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = RegisterForm(request.POST)

        if form.is_valid():
            user = form.save()
            login(request, user)

            messages.success(request, f"Welcome, {user.first_name}! Account created successfully.")
            return redirect('dashboard')

        else:
            print(form.errors)  # 🔥 VERY IMPORTANT for debugging
            messages.error(request, "Form is invalid. Please check inputs.")

    else:
        form = RegisterForm()

    return render(request, 'healthcare_app/register.html', {'form': form})









def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f"Welcome back, {user.first_name or user.username}!")
            return redirect('dashboard')
        else:
            messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm()
    return render(request, 'healthcare_app/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('login')


# ─── Dashboard ────────────────────────────────────────────────────────────────

@login_required
def dashboard_view(request):
    if request.user.is_superuser:
        from django.contrib.auth.models import User
        users = User.objects.all().select_related('userprofile').order_by('-date_joined')
        all_bills_qs = Bill.objects.all().order_by('-uploaded_at')
        all_claims = InsuranceClaim.objects.all().order_by('-claim_date')
        all_complaints = Complaint.objects.all().order_by('-submitted_at')

        # Stats (always full counts for charts/cards)
        total_users = users.count()
        total_bills = all_bills_qs.count()
        total_claims = all_claims.count()
        total_complaints = all_complaints.count()

        total_billed = all_bills_qs.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        total_overcharge = AnalysisReport.objects.aggregate(Sum('total_overcharge'))['total_overcharge__sum'] or 0

        # Pending Actions (pending claims + unresolved complaints)
        pending_claims = all_claims.filter(status='pending').count()
        unresolved_complaints = all_complaints.exclude(status='resolved').count()
        pending_actions = pending_claims + unresolved_complaints

        # Risks Distribution
        high_risk = AnalysisReport.objects.filter(fraud_risk='high').count()
        medium_risk = AnalysisReport.objects.filter(fraud_risk='medium').count()
        low_risk = AnalysisReport.objects.filter(fraud_risk='low').count()
        un_analyzed = all_bills_qs.filter(is_analyzed=False).count()

        # Claims Distribution
        approved_claims = all_claims.filter(status='approved').count()
        rejected_claims = all_claims.filter(status='rejected').count()
        under_review_claims = all_claims.filter(status='review').count()

        # Only pass the 10 most recent bills for display in the Audit Stream tab
        recent_bills = list(all_bills_qs[:10])
        for b in recent_bills:
            report = getattr(b, 'report', None)
            if report:
                b.transparency_score = report.transparency_score
                b.fraud_risk = report.fraud_risk
                b.total_overcharge = report.total_overcharge
            else:
                b.transparency_score = None
                b.fraud_risk = 'pending'
                b.total_overcharge = 0

        context = {
            'users': users,
            'bills': recent_bills,
            'claims': all_claims,
            'complaints': all_complaints,
            'total_users': total_users,
            'total_bills': total_bills,
            'total_claims': total_claims,
            'total_complaints': total_complaints,
            'total_billed': total_billed,
            'total_overcharge': total_overcharge,
            'pending_actions': pending_actions,
            'high_risk': high_risk,
            'medium_risk': medium_risk,
            'low_risk': low_risk,
            'un_analyzed': un_analyzed,
            'approved_claims': approved_claims,
            'rejected_claims': rejected_claims,
            'under_review_claims': under_review_claims,
            'pending_claims_count': pending_claims,
        }
        return render(request, 'healthcare_app/admin_dashboard.html', context)

    bills = Bill.objects.filter(patient=request.user).order_by('-uploaded_at')
    claims = InsuranceClaim.objects.filter(patient=request.user)
    complaints = Complaint.objects.filter(patient=request.user)

    # Stats
    total_bills = bills.count()
    analyzed_bills = bills.filter(is_analyzed=True).count()
    total_claims = claims.count()
    total_complaints = complaints.count()

    recent_bills = []

    for bill in bills[:5]:
        items = BillItem.objects.filter(bill=bill)

        # ←←←← THIS IS THE FIX ←←←←
        if items.exists():
            charged_total = sum(i.charged_price * i.quantity for i in items)
            # Optional: Update bill model if it's still 0
            if bill.total_amount == 0:
                bill.total_amount = charged_total
                bill.save(update_fields=['total_amount'])
        else:
            charged_total = bill.total_amount or 0

        standard_total = sum(
            (i.standard_price or i.charged_price) * i.quantity for i in items
        )

        overpricing_amount = max(0, charged_total - standard_total)

        transparency_score = round((standard_total / charged_total * 100)) if charged_total > 0 else 100

        bill.charged_total = charged_total
        bill.standard_total = standard_total
        bill.overpricing_amount = overpricing_amount
        bill.transparency_score = transparency_score

        recent_bills.append(bill)

    # Fraud risk summary
    high_risk = AnalysisReport.objects.filter(
        bill__patient=request.user,
        fraud_risk='high'
    ).count()

    medium_risk = AnalysisReport.objects.filter(
        bill__patient=request.user,
        fraud_risk='medium'
    ).count()

    low_risk = AnalysisReport.objects.filter(
        bill__patient=request.user,
        fraud_risk='low'
    ).count()

    context = {
        'bills': recent_bills,
        'total_bills': total_bills,
        'analyzed_bills': analyzed_bills,
        'total_claims': total_claims,
        'total_complaints': total_complaints,
        'high_risk': high_risk,
        'medium_risk': medium_risk,
        'low_risk': low_risk,

        'complaints': complaints[:5],  # IMPORTANT
    }

    return render(request, 'healthcare_app/dashboard.html', context)






@login_required
def upload_bill_view(request):
    if request.method == 'POST':
        form = BillUploadForm(request.POST, request.FILES)

        if form.is_valid():
            bill = form.save(commit=False)
            bill.patient = request.user
            bill.save()

            messages.info(request, "⚙ Running AI analysis on your bill...")

            try:
                result = run_full_analysis(str(bill.bill_file.path))

                # Hospital Name
                hospital = result.get('hospital_name', '').strip()
                bill.hospital_name = hospital if hospital else "Unknown Hospital"

                # if result.get('bill_date'):
                #     bill.bill_date = result.get('bill_date')
                from datetime import datetime

                raw_date = result.get('bill_date')

                if raw_date:
                    try:
                        # Try DD/MM/YYYY
                        parsed_date = datetime.strptime(raw_date, "%d/%m/%Y").date()
                    except:
                        try:
                            # Try DD-MM-YYYY
                            parsed_date = datetime.strptime(raw_date, "%d-%m-%Y").date()
                        except:
                            try:
                                # Try YYYY-MM-DD (already correct)
                                parsed_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
                            except:
                                parsed_date = None

                    if parsed_date:
                        bill.bill_date = parsed_date

                # SAVE ITEMS
                for item in result.get('analyzed_items', []):
                    BillItem.objects.create(
                        bill=bill,
                        item_name=item.get('name'),
                        quantity=item.get('quantity'),
                        charged_price=item.get('charged_price'),
                        standard_price=item.get('standard_price'),
                        overcharge_percent=item.get('overcharge_pct'),
                        flag=item.get('flag'),
                    )

                # TOTAL (no extra DB query)
                calculated_total = sum(
                    i["charged_price"] * i["quantity"]
                    for i in result.get("analyzed_items", [])
                )

                extracted_total = float(result.get('extracted_total') or 0)

                if extracted_total > 100:
                    diff_ratio = abs(extracted_total - calculated_total) / extracted_total
                    final_total = extracted_total if diff_ratio <= 0.45 else calculated_total
                else:
                    final_total = calculated_total

                bill.total_amount = final_total
                bill.is_analyzed = True
                bill.save()

                # REPORT
                fraud = result.get('fraud_info', {})

                AnalysisReport.objects.create(
                    bill=bill,
                    transparency_score=result.get('transparency_score'),
                    fraud_risk=fraud.get('risk_level'),
                    total_overcharge=result.get('total_overcharge'),
                    extracted_total=extracted_total,
                    overcharge_percent=fraud.get('fraud_score'),
                    suspicious_items_count=fraud.get('suspicious_count'),
                    recommendations="\n".join(result.get('recommendations', [])),
                )

                messages.success(request, "✅ AI analysis complete!")
                return redirect('bill_detail', pk=bill.pk)

            except Exception as e:
                print("ERROR:", e)
                messages.error(request, f"Error: {str(e)}")
                return redirect('dashboard')

    else:
        form = BillUploadForm()

    return render(request, 'healthcare_app/upload_bill.html', {'form': form})




@login_required
def bill_list_view(request):
    bills = Bill.objects.filter(patient=request.user).order_by('-uploaded_at')
    return render(request, 'healthcare_app/bill_list.html', {'bills': bills})




@login_required
def bill_detail_view(request, pk):
    if request.user.is_superuser:
        bill = get_object_or_404(Bill, pk=pk)
    else:
        bill = get_object_or_404(Bill, pk=pk, patient=request.user)
    items = BillItem.objects.filter(bill=bill)

    # Safe total calculation
    charged_total = sum(i.charged_price * i.quantity for i in items)
    
    standard_total = sum(
        (i.standard_price or i.charged_price) * i.quantity for i in items
    )

    overpricing = max(0, charged_total - standard_total)

    # Update bill total if it's still 0
    if bill.total_amount == 0 and charged_total > 0:
        bill.total_amount = charged_total
        bill.save()

    report = getattr(bill, 'report', None)   # or bill.analysisreport_set.first()

    # Generate AI analysis for each item
    ai_analysis_map = generate_ai_analysis(items)
    for item in items:
        item.ai_analysis = ai_analysis_map.get(item.item_name, "Fair pricing verification.")

    context = {
        'bill': bill,
        'items': items,
        'report': report,
        'charged_total': charged_total,
        'standard_total': standard_total,
        'overpricing': overpricing,
    }

    return render(request, 'healthcare_app/bill_detail.html', context)


# ─── Insurance Views ──────────────────────────────────────────────────────────


@login_required
def submit_claim_view(request):
    bill_id = request.GET.get('bill_id')

    if not bill_id:
        messages.warning(request, "Please select a bill first.")
        return redirect('bill_list')

    try:
        bill = Bill.objects.get(id=bill_id, patient=request.user)
    except Bill.DoesNotExist:
        messages.error(request, "Bill not found.")
        return redirect('bill_list')

    report = getattr(bill, 'report', None) or bill.analysisreport_set.first()

    if request.method == 'POST':
        form = InsuranceClaimForm(
            user=request.user,
            selected_bill=bill,
            data=request.POST
        )


        if form.is_valid():
            claim = form.save(commit=False)
            claim.patient = request.user
            claim.bill = bill

            # AI Prediction
            prediction = predict_insurance_claim(
                claim_amount=float(claim.claim_amount),
                bill_total=float(bill.total_amount),
                fraud_risk=getattr(report, 'fraud_risk', 'low'),
                transparency_score=int(getattr(report, 'transparency_score', 75)),
            )

            claim.approval_probability = prediction.get("approval_probability", 75)
            claim.rejection_reason = " | ".join(prediction.get("rejection_reasons", []))
            claim.status = 'pending'
            claim.save()

            request.session['last_claim_id'] = claim.id
            messages.success(request, "Claim submitted successfully!")
            return redirect('claim_result')

    else:
        form = InsuranceClaimForm(user=request.user, selected_bill=bill)

    # Initial AI Prediction for GET
    pred = predict_insurance_claim(
        claim_amount=float(bill.total_amount),
        bill_total=float(bill.total_amount),
        fraud_risk=getattr(report, 'fraud_risk', 'low'),
        transparency_score=int(getattr(report, 'transparency_score', 75)),
    )

    return render(request, 'healthcare_app/submit_claim.html', {
        'form': form,
        'selected_bill': bill,
        'initial_probability': pred.get('approval_probability', 75),
        'initial_reasons': pred.get('rejection_reasons', []),
    })








@login_required
def claim_list_view(request):
    claims = InsuranceClaim.objects.filter(
        patient=request.user
    ).select_related('bill').order_by('-claim_date')
    
    context = {
        'claims': claims,
    }
    return render(request, 'healthcare_app/claim_list.html', context)



@login_required
def claim_result_view(request):
    claim_id = request.session.get('last_claim_id')

    if not claim_id:
        messages.warning(request, "No recent claim found.")
        return redirect('claim_list')

    try:
        claim = InsuranceClaim.objects.select_related('bill').get(
            id=claim_id, 
            patient=request.user
        )
    except InsuranceClaim.DoesNotExist:
        messages.error(request, "Claim not found.")
        return redirect('claim_list')

    # Split rejection reasons safely
    reasons = []
    if claim.rejection_reason:
        reasons = [r.strip() for r in claim.rejection_reason.split(" | ") if r.strip()]

    context = {
        'claim': claim,
        'probability': claim.approval_probability,
        'reasons': reasons,
    }
    
    return render(request, 'healthcare_app/claim_result.html', context)




# ─── Complaint Views ──────────────────────────────────────────────────────────


@login_required
def submit_complaint_view(request):
    complaints = Complaint.objects.filter(
        patient=request.user
    ).order_by('-submitted_at')

    if request.method == 'POST':
        form = ComplaintForm(request.user, request.POST)
        if form.is_valid():
            complaint = form.save(commit=False)
            complaint.patient = request.user
            complaint.save()

            # Generate AI email draft with detailed bill analysis
            hospital_name = None
            bill_amount = None
            bill_items = None
            transparency_score = None
            total_overcharge = None
            fraud_risk = None

            if complaint.bill:
                hospital_name = complaint.bill.hospital_name
                bill_amount = complaint.bill.total_amount

                # Get bill items with analysis
                items = BillItem.objects.filter(bill=complaint.bill)
                bill_items = [
                    {
                        'item_name': item.item_name,
                        'charged_price': float(item.charged_price),
                        'standard_price': float(item.standard_price) if item.standard_price else None,
                        'overcharge_percent': item.overcharge_percent,
                        'flag': item.flag
                    }
                    for item in items
                ]

                # Get analysis report
                report = getattr(complaint.bill, 'report', None)
                if report:
                    transparency_score = report.transparency_score
                    total_overcharge = float(report.total_overcharge) if report.total_overcharge else None
                    fraud_risk = report.fraud_risk

            try:
                email_draft = generate_complaint_email_draft(
                    complaint_type=complaint.get_complaint_type_display(),
                    description=complaint.description,
                    hospital_name=hospital_name,
                    bill_amount=bill_amount,
                    bill_items=bill_items,
                    transparency_score=transparency_score,
                    total_overcharge=total_overcharge,
                    fraud_risk=fraud_risk
                )
                complaint.email_draft = email_draft
                complaint.save()
            except Exception as e:
                print("Email draft generation error:", e)

            messages.success(request, "✅ Complaint filed successfully. Email draft generated.")

            return redirect('submit_complaint')  # reload same page

    else:
        form = ComplaintForm(request.user)

    return render(request, 'healthcare_app/submit_complaint.html', {
        'form': form,
        'complaints': complaints
    })







@login_required
def complaint_list_view(request):
    complaints = Complaint.objects.filter(
        patient=request.user
    ).order_by('-submitted_at')

    return render(request, 'healthcare_app/complaint_list.html', {
        'complaints': complaints
    })


@login_required
def download_email_draft(request, pk):
    if request.user.is_superuser:
        complaint = get_object_or_404(Complaint, pk=pk)
    else:
        complaint = get_object_or_404(Complaint, pk=pk, patient=request.user)

    if not complaint.email_draft:
        messages.error(request, "No email draft available for this complaint.")
        return redirect('complaint_list')

    response = HttpResponse(complaint.email_draft, content_type='text/plain')
    response['Content-Disposition'] = f'attachment; filename="complaint_{pk}_email_draft.txt"'
    return response



# ─── Notification Views ─────────────────────────────────────────────────────────────


@login_required
def notification_list(request):
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')
    # Mark all as read when viewing list (optional)
    # notifications.update(is_read=True)
    
    context = {
        'notifications': notifications,
        'unread_count': Notification.objects.filter(user=request.user, is_read=False).count()
    }
    return render(request, 'healthcare_app/notifications.html', context)


@login_required
def mark_notification_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.is_read = True
    notification.save()
    return redirect('notifications')


@login_required
def admin_update_claim_status(request, pk):
    if not request.user.is_superuser:
        messages.error(request, "Permission denied.")
        return redirect('dashboard')
    
    if request.method == 'POST':
        claim = get_object_or_404(InsuranceClaim, pk=pk)
        new_status = request.POST.get('status')
        if new_status in dict(InsuranceClaim.STATUS_CHOICES):
            claim.status = new_status
            claim.save()
            messages.success(request, f"Claim #{claim.id} status successfully updated to {claim.get_status_display()}.")
            
            # Create a notification for the patient
            Notification.objects.create(
                user=claim.patient,
                title="Insurance Claim Status Updated",
                message=f"Your insurance claim for '{claim.insurance_company}' (Claim #{claim.id}) has been updated to '{claim.get_status_display()}' by an administrator.",
                notification_type='claim_update',
                priority='medium',
                link=f"/claims/"
            )
        else:
            messages.error(request, "Invalid status choice.")
            
    return redirect('dashboard')


@login_required
def admin_update_complaint_status(request, pk):
    if not request.user.is_superuser:
        messages.error(request, "Permission denied.")
        return redirect('dashboard')
        
    if request.method == 'POST':
        complaint = get_object_or_404(Complaint, pk=pk)
        new_status = request.POST.get('status')
        if new_status in ['submitted', 'in_progress', 'resolved']:
            complaint.status = new_status
            complaint.save()
            messages.success(request, f"Complaint #{complaint.id} status updated to {new_status.replace('_', ' ').title()}.")
            
            # Create a notification for the patient
            Notification.objects.create(
                user=complaint.patient,
                title="Complaint Status Update",
                message=f"Your complaint regarding '{complaint.get_complaint_type_display()}' (Complaint #{complaint.id}) has been updated to '{new_status.replace('_', ' ').title()}' by an administrator.",
                notification_type='legal',
                priority='high',
                link=f"/complaints/"
            )
        else:
            messages.error(request, "Invalid status.")
            
    return redirect('dashboard')


# ─── Home ─────────────────────────────────────────────────────────────────────

def home_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'healthcare_app/home.html')