from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import UserProfile, Bill, InsuranceClaim, Complaint



class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = [
            'username',
            'first_name',
            'last_name',
            'email',
            'password1',
            'password2'
        ]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']

        if commit:
            user.save()

        return user



class BillUploadForm(forms.ModelForm):
    class Meta:
        model = Bill
        fields = ['bill_file']
        widgets = {
            'bill_date': forms.DateInput(attrs={'type': 'date'}),
        }





class InsuranceClaimForm(forms.ModelForm):
    class Meta:
        model = InsuranceClaim
        fields = ['bill', 'policy_number', 'insurance_company', 'claim_amount']
        
        widgets = {
            'bill': forms.HiddenInput(),
            'claim_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter claim amount in ₹',
                'step': '0.01'
            }),
            'policy_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. POL123456789'
            }),
            'insurance_company': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Star Health, HDFC Ergo, ICICI Lombard'
            }),
        }

    def __init__(self, user=None, selected_bill=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if user:
            self.fields['bill'].queryset = Bill.objects.filter(
                patient=user, 
                is_analyzed=True
            ).order_by('-uploaded_at')
        
        if selected_bill:
            self.initial['bill'] = selected_bill.pk
            self.initial['claim_amount'] = selected_bill.total_amount
            self.fields['bill'].widget = forms.HiddenInput()
        
        # Make fields required
        for field in ['policy_number', 'insurance_company', 'claim_amount']:
            self.fields[field].required = True




class ComplaintForm(forms.ModelForm):

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Show only user's bills
        self.fields['bill'].queryset = Bill.objects.filter(
            patient=user,
            is_analyzed=True
        )

    class Meta:
        model = Complaint
        fields = ['bill', 'complaint_type', 'description']
        widgets = {
            'description': forms.Textarea(attrs={
                'placeholder': 'Describe the issue clearly...'
            })
        }



