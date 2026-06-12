from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('bills/', views.bill_list_view, name='bill_list'),
    path('bills/upload/', views.upload_bill_view, name='upload_bill'),
    path('bills/<int:pk>/', views.bill_detail_view, name='bill_detail'),
    path('claims/', views.claim_list_view, name='claim_list'),
    path('claims/submit/', views.submit_claim_view, name='submit_claim'),
    path('complaints/', views.complaint_list_view, name='complaint_list'),
    path('complaints/new/', views.submit_complaint_view, name='submit_complaint'),
    path('complaints/submit/', views.submit_complaint_view, name='submit_complaint'),
    path('complaints/<int:pk>/download-email/', views.download_email_draft, name='download_email_draft'),
    path('claims/result/', views.claim_result_view, name='claim_result'),
    path('admin-dashboard/claims/<int:pk>/status/', views.admin_update_claim_status, name='admin_update_claim_status'),
    path('admin-dashboard/complaints/<int:pk>/status/', views.admin_update_complaint_status, name='admin_update_complaint_status'),
]