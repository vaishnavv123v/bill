from django.contrib import admin
from .models import UserProfile, Bill, BillItem, AnalysisReport, InsuranceClaim, Complaint

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'phone']

@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = ['id', 'patient', 'hospital_name', 'total_amount', 'is_analyzed', 'uploaded_at']
    list_filter = ['is_analyzed']

@admin.register(BillItem)
class BillItemAdmin(admin.ModelAdmin):
    list_display = ['bill', 'item_name', 'quantity', 'charged_price', 'standard_price', 'flag']
    list_filter = ['flag']

@admin.register(AnalysisReport)
class AnalysisReportAdmin(admin.ModelAdmin):
    list_display = ['bill', 'transparency_score', 'fraud_risk', 'total_overcharge']
    list_filter = ['fraud_risk']

@admin.register(InsuranceClaim)
class InsuranceClaimAdmin(admin.ModelAdmin):
    list_display = ['id', 'patient', 'insurance_company', 'claim_amount', 'status', 'approval_probability']

@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ['id', 'patient', 'complaint_type', 'status', 'submitted_at']