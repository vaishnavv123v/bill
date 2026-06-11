from django.db import models
from django.contrib.auth.models import User

ROLE_CHOICES = [
    ('patient', 'Patient'),
    ('hospital', 'Hospital'),
    ('insurance', 'Insurance Agent'),
]

RISK_CHOICES = [
    ('low', 'Low Risk'),
    ('medium', 'Medium Risk'),
    ('high', 'High Risk'),
]


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='patient')
    phone = models.CharField(max_length=15, blank=True)
    address = models.TextField(blank=True)

    def __str__(self):
        return f"{self.user.username} ({self.role})"



class Bill(models.Model):
    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bills')
    hospital_name = models.CharField(max_length=200, null=True, blank=True)
    patient_name_on_bill = models.CharField(max_length=200, null=True, blank=True)
    patient_address = models.TextField(null=True, blank=True)
    patient_age = models.CharField(max_length=10, null=True, blank=True)
    admission_number = models.CharField(max_length=50, null=True, blank=True)
    
    # admission_date, discharge_date, etc.
    admission_date = models.DateField(null=True, blank=True)
    discharge_date = models.DateField(null=True, blank=True)
    invoice_number = models.CharField(max_length=100, null=True, blank=True)
    payment_due_date = models.DateField(null=True, blank=True)
    bill_date = models.DateField(null=True, blank=True)

    # Main fields
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, default=0.00)
    
    # Temporarily comment this line
    # extracted_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    bill_file = models.FileField(upload_to='bills/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_analyzed = models.BooleanField(default=False)

    def __str__(self):
        hospital = (self.hospital_name or "Unknown Hospital").strip()
        if len(hospital) > 50:
            hospital = hospital[:47] + "..."

        amount = f"₹{float(self.total_amount or 0):,.0f}"

        # Show bill date if available
        bill_date_str = ""
        if self.bill_date:
            bill_date_str = f" - {self.bill_date.strftime('%d %b %Y')}"

        return f"Bill #{self.pk} | {hospital} | {amount}{bill_date_str}"







class BillItem(models.Model):
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name='items')
    item_name = models.CharField(max_length=200)
    quantity = models.IntegerField(default=1)
    charged_price = models.DecimalField(max_digits=15, decimal_places=2)
    standard_price = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    overcharge_percent = models.FloatField(default=0.0)
    flag = models.CharField(max_length=20, default='normal')  # normal, suspicious, overcharged

    def __str__(self):
        return f"{self.item_name} - ₹{self.charged_price}"


class AnalysisReport(models.Model):
    bill = models.OneToOneField(Bill, on_delete=models.CASCADE, related_name='report')
    transparency_score = models.IntegerField(default=0)
    fraud_risk = models.CharField(max_length=10, choices=RISK_CHOICES, default='low')
    total_overcharge = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    extracted_total = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    overcharge_percent = models.FloatField(default=0.0)
    suspicious_items_count = models.IntegerField(default=0)
    recommendations = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Report for Bill #{self.bill.id} | Score: {self.transparency_score}"


class InsuranceClaim(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('review', 'Under Review'),
    ]

    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='claims')
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name='claims')
    policy_number = models.CharField(max_length=100)
    insurance_company = models.CharField(max_length=200)
    claim_amount = models.DecimalField(max_digits=12, decimal_places=2)
    claim_date = models.DateField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    approval_probability = models.FloatField(default=0.0)
    rejection_reason = models.TextField(blank=True)

    def __str__(self):
        return f"Claim #{self.id} - {self.insurance_company}"


class Complaint(models.Model):
    COMPLAINT_TYPE = [
        ('overcharging', 'Overcharging'),
        ('fraud', 'Fraud'),
        ('insurance', 'Insurance Dispute'),
        ('other', 'Other'),
    ]

    patient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='complaints')
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, null=True, blank=True)
    complaint_type = models.CharField(max_length=30, choices=COMPLAINT_TYPE)
    description = models.TextField()
    submitted_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default='submitted')

    def __str__(self):
        return f"Complaint #{self.id} by {self.patient.username}"
    





class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('suspicious', 'Suspicious Activity'),
        ('claim_update', 'Claim Status Update'),
        ('recommendation', 'Recommendation'),
        ('legal', 'Legal Guidance'),
        ('bill_analysis', 'Bill Analysis Alert'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    link = models.URLField(blank=True, null=True)  # Link to relevant page (claim, bill, etc.)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.user.username}"